from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship
from .database import Base


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

    emails = relationship("Email", back_populates="account")


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

    received_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("EmailAccount", back_populates="emails")
    supplier = relationship("Supplier", back_populates="emails")
    attachments = relationship("Attachment", back_populates="email")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    filename = Column(String(255))
    file_path = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
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

    body_chinese = Column(Text)
    body_translated = Column(Text)
    target_language = Column(String(10))

    status = Column(String(20), default="draft")  # draft, sent
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reply_to_email = relationship("Email")


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
    __tablename__ = "translation_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(255), unique=True, index=True)
    status = Column(String(20), default="processing")
    total_requests = Column(Integer, default=0)
    completed_requests = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


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
    """邮件翻译共享表 - 基于 message_id 跨用户共享翻译结果"""
    __tablename__ = "shared_email_translations"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), unique=True, index=True)  # 邮件的 RFC Message-ID
    subject_original = Column(Text)
    subject_translated = Column(Text)
    body_original = Column(Text)
    body_translated = Column(Text)
    source_lang = Column(String(10))
    target_lang = Column(String(10), default="zh")
    translated_by = Column(Integer, ForeignKey("email_accounts.id"))  # 谁触发的翻译
    translated_at = Column(DateTime, default=datetime.utcnow)
