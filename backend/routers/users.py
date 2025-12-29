from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
import imaplib

from database.database import get_db
from database.models import EmailAccount
from config import get_settings
from utils.crypto import encrypt_password, decrypt_password, mask_email
from utils.rate_limit import login_limiter, get_client_ip

router = APIRouter(prefix="/api/users", tags=["users"])
settings = get_settings()


# RateLimiter 类和 login_limiter 已移至 utils/rate_limit.py

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login", auto_error=False)

# 允许登录的邮箱域名
ALLOWED_DOMAINS = ["jingzhicheng.com.cn"]

# 邮箱服务器配置
EMAIL_SERVERS = {
    "jingzhicheng.com.cn": {
        "imap": "imap-ent.21cn.com",  # 21cn 企业邮箱
        "smtp": "smtp-ent.21cn.com",
        "imap_port": 993,
        "smtp_port": 465
    },
}


# ============ Schemas ============
class EmailLoginRequest(BaseModel):
    email: str
    password: str  # 邮箱密码


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    email: str
    account_id: int


class AccountResponse(BaseModel):
    id: int
    email: str
    imap_server: str
    smtp_server: str
    is_active: bool
    last_sync_at: Optional[datetime]
    default_approver_id: Optional[int] = None

    class Config:
        from_attributes = True


class ApproverResponse(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True


class SetDefaultApproverRequest(BaseModel):
    approver_id: int


# ============ Helper Functions ============
def get_email_domain(email: str) -> str:
    """提取邮箱域名"""
    return email.split("@")[-1].lower() if "@" in email else ""


def verify_email_credentials(email: str, password: str, imap_server: str, imap_port: int = 993) -> tuple[bool, str]:
    """验证邮箱账号密码是否正确

    返回: (success, error_message)
    """
    import socket

    # 设置超时
    socket.setdefaulttimeout(30)

    try:
        print(f"[IMAP] Connecting to {imap_server}:{imap_port}...")
        imap = imaplib.IMAP4_SSL(imap_server, imap_port)
        print(f"[IMAP] Connected, attempting login for {mask_email(email)}...")

        # 尝试登录
        imap.login(email, password)
        print(f"[IMAP] Login successful!")

        # 验证能够选择收件箱
        imap.select("INBOX")
        print(f"[IMAP] INBOX selected successfully")

        imap.logout()
        return True, ""

    except imaplib.IMAP4.error as e:
        error_msg = str(e)
        print(f"[IMAP] Login failed: {error_msg}")

        # 解析常见错误
        if "password" in error_msg.lower() or "incorrect" in error_msg.lower():
            return False, "邮箱密码错误，请检查密码是否正确"
        elif "abnormal" in error_msg.lower() or "not open" in error_msg.lower():
            return False, "IMAP服务未开启，请在企业邮箱设置中开启IMAP/SMTP服务"
        elif "frequency" in error_msg.lower() or "limited" in error_msg.lower():
            return False, "登录频率受限，请稍后再试"
        elif "busy" in error_msg.lower():
            return False, "邮箱服务器繁忙，请稍后再试"
        else:
            return False, f"登录失败: {error_msg}"

    except socket.timeout:
        print(f"[IMAP] Connection timeout")
        return False, "连接邮箱服务器超时，请检查网络连接"

    except socket.gaierror as e:
        print(f"[IMAP] DNS error: {e}")
        return False, "无法解析邮箱服务器地址，请检查网络连接"

    except ConnectionRefusedError:
        print(f"[IMAP] Connection refused")
        return False, "邮箱服务器拒绝连接，请检查服务器配置"

    except Exception as e:
        print(f"[IMAP] Unexpected error: {type(e).__name__}: {e}")
        return False, f"连接错误: {str(e)}"
    finally:
        socket.setdefaulttimeout(None)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# get_client_ip 已移至 utils/rate_limit.py


# ============ Routes ============
@router.post("/login", response_model=LoginResponse)
async def login_with_email(
    request: EmailLoginRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """用公司邮箱登录"""
    # 速率限制检查
    client_ip = get_client_ip(req)
    allowed, retry_after = login_limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请在 {retry_after} 秒后重试",
            headers={"Retry-After": str(retry_after)}
        )

    email = request.email.strip().lower()
    password = request.password
    domain = get_email_domain(email)

    # 检查邮箱域名是否允许
    if domain not in ALLOWED_DOMAINS:
        raise HTTPException(
            status_code=403,
            detail="只允许使用公司邮箱 (@jingzhicheng.com.cn) 登录"
        )

    # 获取服务器配置
    config = EMAIL_SERVERS.get(domain)
    if not config:
        raise HTTPException(status_code=400, detail="无法识别邮箱服务器配置")

    imap_server = config["imap"]
    smtp_server = config["smtp"]
    imap_port = config["imap_port"]
    smtp_port = config["smtp_port"]

    # 验证邮箱登录
    success, error_msg = verify_email_credentials(email, password, imap_server, imap_port)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg or "邮箱账号或密码错误"
        )

    # 查找或创建邮箱账户
    result = await db.execute(select(EmailAccount).where(EmailAccount.email == email))
    account = result.scalar_one_or_none()

    if account:
        # 更新密码（加密存储）
        account.password = encrypt_password(password)
        account.is_active = True
    else:
        # 创建新账户（密码加密存储）
        account = EmailAccount(
            email=email,
            password=encrypt_password(password),
            imap_server=imap_server,
            smtp_server=smtp_server,
            imap_port=imap_port,
            smtp_port=smtp_port,
            is_active=True
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)

    # 生成 JWT
    access_token = create_access_token(
        data={"sub": email, "account_id": account.id},
        expires_delta=timedelta(days=7)
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        email=email,
        account_id=account.id
    )


async def get_current_account(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> EmailAccount:
    """从 JWT 获取当前登录的邮箱账户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        account_id: int = payload.get("account_id")
        if email is None or account_id is None:
            raise credentials_exception

        result = await db.execute(select(EmailAccount).where(EmailAccount.id == account_id))
        account = result.scalar_one_or_none()

        if account is None or not account.is_active:
            raise credentials_exception

        return account

    except JWTError:
        raise credentials_exception


@router.get("/me", response_model=AccountResponse)
async def get_current_account_info(account: EmailAccount = Depends(get_current_account)):
    """获取当前登录账户信息"""
    return account


@router.post("/logout")
async def logout():
    """退出登录（前端清除token即可）"""
    return {"message": "已退出登录"}


# ============ 审批人相关 API ============
from typing import List


@router.get("/approvers", response_model=List[ApproverResponse])
async def get_approvers(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取可选审批人列表（排除自己）"""
    result = await db.execute(
        select(EmailAccount)
        .where(
            EmailAccount.is_active == True,
            EmailAccount.id != account.id  # 排除自己
        )
        .order_by(EmailAccount.email)
    )
    return result.scalars().all()


@router.put("/me/default-approver")
async def set_default_approver(
    request: SetDefaultApproverRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """设置默认审批人"""
    # 验证审批人存在
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.id == request.approver_id)
    )
    approver = result.scalar_one_or_none()

    if not approver:
        raise HTTPException(status_code=404, detail="审批人不存在")

    if approver.id == account.id:
        raise HTTPException(status_code=400, detail="不能将自己设为默认审批人")

    account.default_approver_id = request.approver_id
    await db.commit()

    return {"message": "默认审批人设置成功", "approver": approver.email}
