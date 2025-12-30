"""
邮件模板 API 路由

端点：
- GET    /api/templates                      获取模板列表（个人+共享）
- GET    /api/templates/categories           获取模板分类列表
- GET    /api/templates/variables            获取可用变量列表
- GET    /api/templates/languages            获取支持的翻译语言
- GET    /api/templates/{id}                 获取模板详情（含所有语言版本）
- POST   /api/templates                      创建模板
- PUT    /api/templates/{id}                 更新模板
- DELETE /api/templates/{id}                 删除模板
- POST   /api/templates/{id}/translate       生成/更新翻译版本
- POST   /api/templates/{id}/share           共享模板
- POST   /api/templates/{id}/unshare         取消共享模板
- POST   /api/templates/{id}/use             使用模板（增加计数+替换变量）
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from database.models import EmailAccount
from routers.users import get_current_account
from services.template_service import (
    TemplateService,
    TEMPLATE_CATEGORIES,
    AVAILABLE_VARIABLES,
    SUPPORTED_LANGUAGES
)


router = APIRouter(prefix="/api/templates", tags=["templates"])


# ============ Pydantic 模型 ============

class TemplateCreate(BaseModel):
    """创建模板请求"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    body_cn: str = Field(..., min_length=1, description="中文正文")
    subject_cn: Optional[str] = Field(None, max_length=255, description="中文主题")
    description: Optional[str] = Field(None, max_length=255, description="模板描述")
    category: Optional[str] = Field(None, description="分类代码")
    variables: Optional[List[str]] = Field(None, description="使用的变量列表")
    is_shared: bool = Field(False, description="是否共享")


class TemplateUpdate(BaseModel):
    """更新模板请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    body_cn: Optional[str] = Field(None, min_length=1)
    subject_cn: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = None
    variables: Optional[List[str]] = None
    is_shared: Optional[bool] = None


class TranslateRequest(BaseModel):
    """翻译模板请求"""
    target_lang: str = Field(..., description="目标语言代码，如 en/ja/ko")
    force_retranslate: bool = Field(False, description="是否强制重新翻译")


class UseTemplateRequest(BaseModel):
    """使用模板请求"""
    target_lang: Optional[str] = Field(None, description="目标语言（如果需要翻译版本）")
    variables: Optional[Dict[str, str]] = Field(None, description="变量值映射")


class TemplateResponse(BaseModel):
    """模板响应"""
    id: int
    account_id: int
    name: str
    description: Optional[str]
    category: Optional[str]
    category_name: Optional[str]
    subject_cn: Optional[str]
    body_cn: str
    variables: List[str]
    is_shared: bool
    is_mine: bool
    use_count: int
    translated_langs: List[str] = []
    author: Optional[Dict[str, Any]] = None
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class TranslationResponse(BaseModel):
    """翻译响应"""
    id: int
    target_lang: str
    target_lang_name: str
    subject_translated: Optional[str]
    body_translated: Optional[str]
    translated_at: Optional[str]


class TemplateDetailResponse(TemplateResponse):
    """模板详情响应（含翻译）"""
    translations: List[TranslationResponse] = []


class CategoryResponse(BaseModel):
    """分类响应"""
    code: str
    name_cn: str
    name_en: str
    icon: str


class VariableResponse(BaseModel):
    """变量响应"""
    name: str
    description: str
    example: str


class LanguageResponse(BaseModel):
    """语言响应"""
    code: str
    name: str


class UseTemplateResponse(BaseModel):
    """使用模板响应"""
    subject: Optional[str]
    body: str
    is_translated: bool
    target_lang: Optional[str]


# ============ API 端点 ============

@router.get("/categories", response_model=List[CategoryResponse])
async def get_categories():
    """获取模板分类列表"""
    return [
        {"code": code, **info}
        for code, info in TEMPLATE_CATEGORIES.items()
    ]


@router.get("/variables", response_model=List[VariableResponse])
async def get_variables():
    """获取可用变量列表"""
    return [
        {"name": name, **info}
        for name, info in AVAILABLE_VARIABLES.items()
    ]


@router.get("/languages", response_model=List[LanguageResponse])
async def get_languages():
    """获取支持的翻译语言列表"""
    return [
        {"code": code, "name": name}
        for code, name in SUPPORTED_LANGUAGES.items()
    ]


@router.get("", response_model=Dict[str, Any])
async def get_templates(
    category: Optional[str] = Query(None, description="分类筛选"),
    include_shared: bool = Query(True, description="是否包含共享模板"),
    search: Optional[str] = Query(None, max_length=100, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    获取模板列表

    - 默认返回个人模板 + 共享模板
    - 支持按分类筛选
    - 支持搜索名称、描述、内容
    - 按使用次数和更新时间排序
    """
    service = TemplateService(db)
    return await service.get_templates(
        account_id=current_account.id,
        category=category,
        include_shared=include_shared,
        search=search,
        page=page,
        page_size=page_size
    )


@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    获取模板详情

    - 返回模板基本信息
    - 包含所有已翻译的语言版本
    """
    service = TemplateService(db)
    template = await service.get_template(template_id, current_account.id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")

    return template


@router.post("", response_model=TemplateResponse)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    创建模板

    - 自动检测正文中使用的变量
    - 可选择是否共享给全公司
    """
    # 验证分类
    if data.category and data.category not in TEMPLATE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效的分类代码: {data.category}")

    service = TemplateService(db)
    return await service.create_template(
        account_id=current_account.id,
        **data.model_dump()
    )


@router.put("/{template_id}", response_model=TemplateDetailResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    更新模板

    - 只能修改自己创建的模板
    - 更新正文/主题后会重新检测变量
    """
    # 验证分类
    if data.category and data.category not in TEMPLATE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效的分类代码: {data.category}")

    service = TemplateService(db)
    template = await service.update_template(
        template_id=template_id,
        account_id=current_account.id,
        **data.model_dump(exclude_unset=True)
    )

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权修改")

    return template


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    删除模板

    - 只能删除自己创建的模板
    - 删除模板会同时删除所有翻译版本
    """
    service = TemplateService(db)
    success = await service.delete_template(template_id, current_account.id)

    if not success:
        raise HTTPException(status_code=404, detail="模板不存在或无权删除")

    return {"message": "模板已删除", "id": template_id}


@router.post("/{template_id}/translate")
async def translate_template(
    template_id: int,
    data: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    翻译模板为指定语言

    - 使用 vLLM 翻译引擎
    - 翻译结果会缓存，下次直接返回
    - 可强制重新翻译覆盖缓存
    """
    if data.target_lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的语言: {data.target_lang}，支持的语言: {list(SUPPORTED_LANGUAGES.keys())}"
        )

    service = TemplateService(db)

    try:
        result = await service.translate_template(
            template_id=template_id,
            account_id=current_account.id,
            target_lang=data.target_lang,
            force_retranslate=data.force_retranslate
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")

    return result


@router.post("/{template_id}/share")
async def share_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    共享模板

    - 共享后其他用户可以看到和使用此模板
    - 只有模板创建者可以共享
    """
    service = TemplateService(db)
    template = await service.share_template(template_id, current_account.id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权操作")

    return {"message": "模板已共享", "template": template}


@router.post("/{template_id}/unshare")
async def unshare_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    取消共享模板

    - 取消共享后只有创建者可以看到此模板
    """
    service = TemplateService(db)
    template = await service.unshare_template(template_id, current_account.id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权操作")

    return {"message": "已取消共享", "template": template}


@router.post("/{template_id}/use", response_model=UseTemplateResponse)
async def use_template(
    template_id: int,
    data: UseTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    使用模板

    - 增加使用次数统计
    - 替换变量占位符
    - 可选择返回翻译版本
    """
    service = TemplateService(db)
    template = await service.get_template(template_id, current_account.id)

    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权访问")

    # 增加使用次数
    await service.increment_use_count(template_id)

    # 确定使用哪个版本
    subject = template.get("subject_cn")
    body = template.get("body_cn")
    is_translated = False

    if data.target_lang:
        # 查找翻译版本
        translations = template.get("translations", [])
        for t in translations:
            if t["target_lang"] == data.target_lang:
                subject = t.get("subject_translated") or subject
                body = t.get("body_translated") or body
                is_translated = True
                break

        if not is_translated and data.target_lang in SUPPORTED_LANGUAGES:
            # 尝试实时翻译
            try:
                result = await service.translate_template(
                    template_id=template_id,
                    account_id=current_account.id,
                    target_lang=data.target_lang
                )
                if result:
                    subject = result.get("subject_translated") or subject
                    body = result.get("body_translated") or body
                    is_translated = True
            except Exception:
                pass  # 翻译失败则使用中文版本

    # 替换变量
    if data.variables:
        subject = service.replace_variables(subject, data.variables) if subject else None
        body = service.replace_variables(body, data.variables)

    return {
        "subject": subject,
        "body": body,
        "is_translated": is_translated,
        "target_lang": data.target_lang if is_translated else None
    }
