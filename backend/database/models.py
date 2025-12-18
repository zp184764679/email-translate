from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float, Table
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship
from .database import Base


# 邮件-标签 多对多关联表
email_label_mappings = Table(
    'email_label_mappings',
    Base.metadata,
    Column('email_id', Integer, ForeignKey('emails.id', ondelete='CASCADE'), primary_key=True),
    Column('label_id', Integer, ForeignKey('email_labels.id', ondelete='CASCADE'), primary_key=True)
)

# 邮件-文件夹 多对多关联表
email_folder_mappings = Table(
    'email_folder_mappings',
    Base.metadata,
    Column('email_id', Integer, ForeignKey('emails.id', ondelete='CASCADE'), primary_key=True),
    Column('folder_id', Integer, ForeignKey('email_folders.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime, default=datetime.utcnow)
)


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    imap_server = Column(String(255))
    imap_port = Column(Integer, default=993)
    smtp_server = Column(String(255))
    smtp_port = Column(Integer, default=465)
    use_ssl = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 审批相关
    default_approver_id = Column(Integer, ForeignKey("email_accounts.id"))  # 默认审批人

    emails = relationship("Email", back_populates="account")
    default_approver = relationship("EmailAccount", remote_side="EmailAccount.id", foreign_keys=[default_approver_id])


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email_domain = Column(String(255))
    contact_email = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    emails = relationship("Email", back_populates="supplier")
    glossary = relationship("Glossary", back_populates="supplier")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), unique=True, index=True)
    thread_id = Column(String(255), index=True)
    in_reply_to = Column(String(255))
    references = Column(Text)

    account_id = Column(Integer, ForeignKey("email_accounts.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))

    from_email = Column(String(255))
    from_name = Column(String(255))
    to_email = Column(Text)        # 完整收件人列表 (RFC 5322)
    cc_email = Column(Text)        # 抄送列表
    bcc_email = Column(Text)       # 密送列表
    reply_to = Column(String(255)) # 回复地址

    subject_original = Column(Text)
    subject_translated = Column(Text)

    body_original = Column(MEDIUMTEXT)
    body_translated = Column(MEDIUMTEXT)
    body_html = Column(MEDIUMTEXT)

    language_detected = Column(String(10))
    direction = Column(String(20))  # inbound, outbound
    is_translated = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    # 翻译状态：none(未翻译), translating(翻译中), completed(已完成), failed(失败)
    translation_status = Column(String(20), default="none", index=True)

    received_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("EmailAccount", back_populates="emails")
    supplier = relationship("Supplier", back_populates="emails")
    attachments = relationship("Attachment", back_populates="email")
    labels = relationship("EmailLabel", secondary=email_label_mappings, back_populates="emails")
    folders = relationship("EmailFolder", secondary=email_folder_mappings, back_populates="emails")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    filename = Column(String(255))
    file_path = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    content_hash = Column(String(64), index=True)  # SHA256 hash，用于检测重复内容
    created_at = Column(DateTime, default=datetime.utcnow)

    email = relationship("Email", back_populates="attachments")


class EmailReadStatus(Base):
    __tablename__ = "email_read_status"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    user_id = Column(Integer, ForeignKey("email_accounts.id"))  # 数据库实际用 user_id
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime)


class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, index=True)
    reply_to_email_id = Column(Integer, ForeignKey("emails.id"))
    author_id = Column(Integer, ForeignKey("email_accounts.id"))

    # 收件人信息（可自定义）
    to_address = Column(String(500))  # 收件人
    cc_address = Column(String(500))  # 抄送
    subject = Column(String(500))     # 主题

    body_chinese = Column(Text)
    body_translated = Column(Text)
    target_language = Column(String(10))

    status = Column(String(20), default="draft")  # draft, pending, sent, rejected
    sent_at = Column(DateTime)
    sent_message_id = Column(String(255), index=True)  # 发送后的 Message-ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 审批相关字段
    approver_id = Column(Integer, ForeignKey("email_accounts.id"))  # 审批人（单人模式）
    approver_group_id = Column(Integer, ForeignKey("approver_groups.id"))  # 审批人组（组模式）
    submitted_at = Column(DateTime)  # 提交审批时间
    reject_reason = Column(Text)  # 驳回原因

    reply_to_email = relationship("Email")
    approver = relationship("EmailAccount", foreign_keys=[approver_id])
    approver_group = relationship("ApproverGroup")


class ApprovalRule(Base):
    __tablename__ = "approval_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    keywords = Column(JSON)
    amount_threshold = Column(Float)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"))
    triggered_rule_id = Column(Integer, ForeignKey("approval_rules.id"))
    operator_id = Column(Integer, ForeignKey("email_accounts.id"))

    action = Column(String(20))
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Glossary(Base):
    __tablename__ = "glossary"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    term_source = Column(String(255), nullable=False)
    term_target = Column(String(255), nullable=False)
    source_lang = Column(String(10))
    target_lang = Column(String(10))
    context = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship("Supplier", back_populates="glossary")


class TranslationBatch(Base):
    """Claude Batch API 批次管理表

    状态流转：
    pending -> submitted -> in_progress -> ended/failed

    价格优势：Batch API 价格是实时 API 的 50%
    """
    __tablename__ = "translation_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(255), unique=True, index=True)  # Claude 返回的批次 ID
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=True)  # 提交者账户（用于通知）

    # 状态: pending(待提交), submitted(已提交), in_progress(处理中), ended(完成), failed(失败), expired(过期), canceled(取消)
    status = Column(String(20), default="pending")

    # 统计
    total_requests = Column(Integer, default=0)      # 总请求数
    completed_requests = Column(Integer, default=0)  # 已完成数
    failed_requests = Column(Integer, default=0)     # 失败数

    # 时间
    created_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime)    # 提交到 Claude 的时间
    completed_at = Column(DateTime)    # 处理完成时间
    expires_at = Column(DateTime)      # 过期时间（Claude Batch 24小时内有效）

    # 关联
    account = relationship("EmailAccount")
    items = relationship("TranslationBatchItem", back_populates="batch")


class TranslationBatchItem(Base):
    """批次翻译项 - 记录每封邮件的翻译状态"""
    __tablename__ = "translation_batch_items"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("translation_batches.id"), index=True)
    custom_id = Column(String(255), index=True)  # 自定义 ID（用于匹配结果）

    # 关联邮件
    email_id = Column(Integer, ForeignKey("emails.id"), index=True)

    # 翻译内容
    source_text = Column(Text)          # 原文
    translated_text = Column(Text)       # 译文
    source_lang = Column(String(10))
    target_lang = Column(String(10), default="zh")

    # 状态
    status = Column(String(20), default="pending")  # pending, succeeded, failed, expired
    error_message = Column(Text)         # 错误信息

    # Token 统计
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    batch = relationship("TranslationBatch", back_populates="items")


class TranslationCache(Base):
    """翻译缓存表 - 相同文本只翻译一次"""
    __tablename__ = "translation_cache"

    id = Column(Integer, primary_key=True, index=True)
    text_hash = Column(String(64), unique=True, index=True)  # SHA256 of source_text + langs
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_lang = Column(String(10))
    target_lang = Column(String(10), nullable=False)
    hit_count = Column(Integer, default=1)  # 缓存命中次数
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SharedEmailTranslation(Base):
    """邮件翻译共享表 - 基于 message_id 跨用户共享翻译结果

    注意：只存储翻译结果，不存储原文（原文已在各用户的 emails 表中）
    匹配逻辑：相同 message_id = 相同邮件内容，直接复用翻译结果
    """
    __tablename__ = "shared_email_translations"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), unique=True, index=True)  # 邮件的 RFC Message-ID
    subject_translated = Column(Text)
    body_translated = Column(Text)
    source_lang = Column(String(10))
    target_lang = Column(String(10), default="zh")
    translated_by = Column(Integer, ForeignKey("email_accounts.id"))  # 谁触发的翻译
    translated_at = Column(DateTime, default=datetime.utcnow)


class EmailSignature(Base):
    """邮件签名表 - 用户自定义签名模板"""
    __tablename__ = "email_signatures"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    name = Column(String(100), nullable=False)  # 签名名称
    category = Column(String(50), default="default")  # 模板类别：default/formal/informal/holiday/auto-reply
    content_chinese = Column(Text)  # 中文签名内容
    content_translated = Column(Text)  # 翻译后的签名（可选）
    target_language = Column(String(10), default="en")  # 目标语言
    is_default = Column(Boolean, default=False)  # 是否为默认签名
    sort_order = Column(Integer, default=0)  # 排序顺序
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TranslationUsage(Base):
    """翻译 API 用量统计表 - 按月统计各翻译引擎用量"""
    __tablename__ = "translation_usage"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False)  # tencent, deepl, claude, ollama
    year_month = Column(String(7), nullable=False)  # 格式: 2024-12

    # 用量统计
    total_chars = Column(Integer, default=0)       # 总字符数
    total_requests = Column(Integer, default=0)    # 请求次数

    # 腾讯翻译免费额度配置
    free_quota = Column(Integer, default=5000000)  # 免费额度（默认500万字符/月）
    is_disabled = Column(Boolean, default=False)   # 是否已禁用（超额时自动禁用）

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 复合唯一索引
    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class EmailLabel(Base):
    """邮件标签表 - 用户自定义标签"""
    __tablename__ = "email_labels"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    name = Column(String(50), nullable=False)
    color = Column(String(20), default="#409EFF")  # 标签颜色
    description = Column(String(200))
    sort_order = Column(Integer, default=0, index=True)  # 排序顺序（支持拖拽排序）
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    emails = relationship("Email", secondary=email_label_mappings, back_populates="labels")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class EmailFolder(Base):
    """邮件文件夹表 - 用户自定义文件夹"""
    __tablename__ = "email_folders"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("email_folders.id"), nullable=True)  # 支持嵌套文件夹
    color = Column(String(20), default="#409EFF")
    icon = Column(String(50), default="folder")
    sort_order = Column(Integer, default=0)
    is_system = Column(Boolean, default=False)  # 系统文件夹不可删除
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    emails = relationship("Email", secondary=email_folder_mappings, back_populates="folders")
    children = relationship("EmailFolder", backref="parent", remote_side=[id], foreign_keys=[parent_id])

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class CalendarEvent(Base):
    """日历事件表 - 支持从邮件创建日程，支持重复事件"""
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=True)  # 关联的邮件（可选）

    title = Column(String(200), nullable=False)
    description = Column(Text)
    location = Column(String(200))

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)

    color = Column(String(20), default="#409EFF")
    reminder_minutes = Column(Integer, default=15)  # 提前提醒分钟数
    reminded_at = Column(DateTime, nullable=True)   # 已提醒时间（防止重复提醒）

    # 重复事件字段
    recurrence_rule = Column(String(255), nullable=True)  # RRULE 格式，如 FREQ=WEEKLY;BYDAY=MO,WE,FR
    recurrence_end = Column(DateTime, nullable=True)      # 重复结束日期
    parent_event_id = Column(Integer, ForeignKey("calendar_events.id"), nullable=True)  # 父事件ID（重复实例）

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    email = relationship("Email")
    parent_event = relationship("CalendarEvent", remote_side=[id], backref="instances")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class EmailExtraction(Base):
    """AI 邮件信息提取表 - 存储 Ollama 提取的结构化信息"""
    __tablename__ = "email_extractions"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), unique=True, nullable=False)

    summary = Column(Text)  # AI 生成的摘要
    dates = Column(JSON)  # 提取的日期列表 [{"date": "2024-12-15", "context": "交货日期"}]
    amounts = Column(JSON)  # 提取的金额列表 [{"amount": 1000, "currency": "USD", "context": "订单总额"}]
    contacts = Column(JSON)  # 提取的联系人 [{"name": "张三", "email": "...", "phone": "..."}]
    action_items = Column(JSON)  # 待办事项 [{"task": "确认订单", "priority": "high"}]
    key_points = Column(JSON)  # 关键信息点

    extracted_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    email = relationship("Email")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class TranslationFeedback(Base):
    """翻译质量反馈表 - 用户标记翻译问题"""
    __tablename__ = "translation_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=True)  # 关联的邮件

    # 反馈内容
    feedback_type = Column(String(50), nullable=False)  # inaccurate, missing, wrong_term, other
    original_text = Column(Text)  # 原文片段
    translated_text = Column(Text)  # 翻译结果
    suggested_text = Column(Text)  # 用户建议的翻译
    comment = Column(Text)  # 用户说明

    # 翻译上下文
    provider = Column(String(20))  # 使用的翻译引擎
    source_lang = Column(String(10))
    target_lang = Column(String(10))

    # 状态
    status = Column(String(20), default="pending")  # pending, reviewed, applied, dismissed
    reviewed_by = Column(Integer, ForeignKey("email_accounts.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_comment = Column(Text)  # 审核意见

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    account = relationship("EmailAccount", foreign_keys=[account_id])
    email = relationship("Email")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class ApproverGroup(Base):
    """审批人组表 - 单选组模式"""
    __tablename__ = "approver_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 组名
    description = Column(String(500))  # 描述
    owner_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)  # 创建者
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    owner = relationship("EmailAccount", foreign_keys=[owner_id])
    members = relationship("ApproverGroupMember", back_populates="group", cascade="all, delete-orphan")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class ApproverGroupMember(Base):
    """审批人组成员表"""
    __tablename__ = "approver_group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("approver_groups.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    group = relationship("ApproverGroup", back_populates="members")
    member = relationship("EmailAccount")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class EmailRule(Base):
    """邮件规则表 - 自动分类规则"""
    __tablename__ = "email_rules"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    name = Column(String(100), nullable=False)  # 规则名称
    description = Column(String(255))  # 规则描述
    is_active = Column(Boolean, default=True)  # 是否启用
    priority = Column(Integer, default=0)  # 优先级（数字越小越先执行）
    stop_processing = Column(Boolean, default=False)  # 命中后是否停止后续规则

    # 条件（JSON格式，支持多条件组合）
    # 格式: {"logic": "AND", "rules": [{"field": "from_email", "operator": "contains", "value": "@supplier.com"}]}
    conditions = Column(JSON, nullable=False)

    # 动作（JSON格式，支持多动作）
    # 格式: [{"type": "move_to_folder", "folder_id": 5}, {"type": "add_label", "label_id": 3}]
    actions = Column(JSON, nullable=False)

    # 统计
    match_count = Column(Integer, default=0)  # 匹配次数
    last_match_at = Column(DateTime)  # 最后匹配时间

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class RuleExecution(Base):
    """规则执行日志表 - 记录每次规则匹配和执行情况"""
    __tablename__ = "rule_executions"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("email_rules.id", ondelete="CASCADE"), nullable=False)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)

    # 执行结果
    matched = Column(Boolean, default=True)  # 是否匹配
    actions_applied = Column(JSON)  # 执行的动作列表 ["move_to_folder:5", "add_label:3"]
    actions_success = Column(Boolean, default=True)  # 所有动作是否成功
    error_message = Column(Text, nullable=True)  # 错误信息

    # 匹配详情（用于调试）
    matched_conditions = Column(JSON, nullable=True)  # 匹配的条件详情

    executed_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关系
    rule = relationship("EmailRule")
    email = relationship("Email")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )


class SentEmailMapping(Base):
    """发送邮件映射表 - 保存发送邮件的 Message-ID 与原文的关联

    用途：收到回复时，通过 In-Reply-To 查找用户发送的原文
    场景A：用户写中文 → 翻译成英文发送 → 收到回复时还原中文原文
    场景B：用户直接写英文发送 → 收到回复时标记为"您的原文"
    """
    __tablename__ = "sent_email_mappings"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), unique=True, index=True)  # 发送邮件的 Message-ID

    draft_id = Column(Integer, ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)

    # 内容字段（支持两种场景）
    subject_original = Column(Text)         # 用户写的主题（可能是中文或英文）
    subject_sent = Column(Text)             # 实际发送的主题
    body_original = Column(MEDIUMTEXT)      # 用户写的正文（可能是中文或英文）
    body_sent = Column(MEDIUMTEXT)          # 实际发送的正文

    # 标记是否经过翻译
    was_translated = Column(Boolean, default=False)  # True=中文翻译后发送，False=直接发送

    to_email = Column(String(500))
    sent_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    draft = relationship("Draft")
    account = relationship("EmailAccount")

    __table_args__ = (
        {'mysql_engine': 'InnoDB'},
    )
