"""
密码加密工具模块

使用 Fernet 对称加密保护邮箱密码存储。
由于需要用密码进行 IMAP 登录，无法使用单向哈希（如 bcrypt），
因此使用可逆的对称加密。

安全说明：
- 加密密钥从 SECRET_KEY 派生
- SECRET_KEY 必须保密，不能提交到版本控制
- 生产环境应使用强随机密钥
"""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 用于密钥派生的固定盐（不需要保密，但需要固定）
# 生产环境也可以从环境变量读取
_SALT = b'email-translate-salt-v1'


def _get_fernet() -> Fernet:
    """
    获取 Fernet 加密器实例

    从 SECRET_KEY 环境变量派生加密密钥
    """
    secret_key = os.environ.get("SECRET_KEY", "email-translate-secret-key-change-in-production")

    # 使用 PBKDF2 从 SECRET_KEY 派生 Fernet 兼容的密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
    return Fernet(key)


def encrypt_password(password: str) -> str:
    """
    加密密码

    Args:
        password: 明文密码

    Returns:
        加密后的密码（base64编码的字符串）
    """
    if not password:
        return ""

    fernet = _get_fernet()
    encrypted = fernet.encrypt(password.encode('utf-8'))
    return encrypted.decode('utf-8')


def decrypt_password(encrypted_password: str) -> str:
    """
    解密密码

    Args:
        encrypted_password: 加密后的密码

    Returns:
        明文密码

    Raises:
        如果解密失败会抛出异常
    """
    if not encrypted_password:
        return ""

    # 兼容旧数据：如果不是加密格式，直接返回（假设是明文）
    # Fernet 加密的数据以 'gAAAAA' 开头
    if not encrypted_password.startswith('gAAAAA'):
        return encrypted_password

    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_password.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception:
        # 解密失败，可能是旧的明文密码
        return encrypted_password


def is_encrypted(password: str) -> bool:
    """
    检查密码是否已加密

    Fernet 加密的数据以 'gAAAAA' 开头
    """
    return password.startswith('gAAAAA') if password else False


def mask_email(email: str) -> str:
    """
    脱敏邮箱地址，保留首尾字符

    例如：john.doe@example.com -> j*****e@e****e.com
    """
    if not email or '@' not in email:
        return email

    local, domain = email.rsplit('@', 1)

    # 脱敏本地部分
    if len(local) <= 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]

    # 脱敏域名部分（保留扩展名）
    domain_parts = domain.split('.')
    if len(domain_parts) >= 2:
        main_domain = domain_parts[0]
        if len(main_domain) <= 2:
            masked_domain = main_domain[0] + '*'
        else:
            masked_domain = main_domain[0] + '*' * (len(main_domain) - 2) + main_domain[-1]
        domain_parts[0] = masked_domain
        masked_domain_full = '.'.join(domain_parts)
    else:
        masked_domain_full = domain

    return f"{masked_local}@{masked_domain_full}"
