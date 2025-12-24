import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import decode_header
from email.utils import parsedate_to_datetime, getaddresses
from typing import List, Dict, Optional, Tuple
import os
import re
from datetime import datetime
from services.language_service import get_language_service


def normalize_message_id(message_id: str) -> str:
    """
    统一归一化 message_id 格式

    - 去除首尾空白
    - 去除尖括号 < >
    - 确保格式一致，便于数据库查询和去重

    Args:
        message_id: 原始 message_id（可能带尖括号）

    Returns:
        归一化后的 message_id
    """
    if not message_id:
        return ""
    # 统一处理：去除所有空白字符和尖括号
    return message_id.strip().strip('<>').strip()


class EmailService:
    """Service for receiving and sending emails via IMAP/SMTP"""

    def __init__(self, imap_server: str, smtp_server: str, email_address: str, password: str,
                 imap_port: int = 993, smtp_port: int = 465, use_ssl: bool = True):
        self.imap_server = imap_server
        self.smtp_server = smtp_server
        self.email_address = email_address
        self.password = password
        self.imap_port = imap_port
        self.smtp_port = smtp_port
        self.use_ssl = use_ssl
        self.imap_conn = None
        self.attachment_dir = "data/attachments"

    def connect_imap(self, timeout: int = 30) -> bool:
        """Connect to IMAP server

        Args:
            timeout: 连接超时时间（秒），默认30秒

        Features:
            - 带超时的连接
            - 连接失败自动重试（最多3次）
        """
        import socket
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # 设置默认 socket 超时
                socket.setdefaulttimeout(timeout)

                if self.use_ssl:
                    self.imap_conn = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
                else:
                    self.imap_conn = imaplib.IMAP4(self.imap_server, self.imap_port)

                self.imap_conn.login(self.email_address, self.password)
                print(f"[IMAP] 连接成功: {self.imap_server}:{self.imap_port}")
                return True

            except (socket.timeout, socket.gaierror, ConnectionError, OSError) as e:
                # 网络错误，可重试
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"[IMAP] 连接失败（尝试 {attempt + 1}/{max_retries}），{wait_time}s 后重试: {e}")
                    import time
                    time.sleep(wait_time)
                else:
                    print(f"[IMAP] 连接失败，已达最大重试次数: {e}")
                    return False

            except imaplib.IMAP4.error as e:
                # IMAP 协议错误（如认证失败），不重试
                print(f"[IMAP] 认证失败: {e}")
                return False

            except Exception as e:
                print(f"[IMAP] 连接错误: {e}")
                return False

        return False

    def _ensure_connection(self) -> bool:
        """确保 IMAP 连接有效，必要时自动重连"""
        if self.imap_conn is None:
            return self.connect_imap()

        try:
            # 发送 NOOP 命令检查连接是否存活
            self.imap_conn.noop()
            return True
        except Exception:
            # 连接已断开，尝试重连
            print("[IMAP] 连接已断开，尝试重连...")
            self.imap_conn = None
            return self.connect_imap()

    def disconnect_imap(self):
        """Disconnect from IMAP server"""
        if self.imap_conn:
            try:
                self.imap_conn.logout()
            except Exception:
                pass
            self.imap_conn = None

    def fetch_emails(self, folder: str = "INBOX", since_date: datetime = None,
                     limit: int = 500, existing_message_ids: set = None) -> List[Dict]:
        """
        Fetch emails from mailbox

        Args:
            folder: IMAP folder to fetch from
            since_date: Only fetch emails since this date
            limit: Maximum number of emails to fetch
            existing_message_ids: Set of message IDs already in database (for dedup)
        """
        # 确保连接有效（必要时自动重连）
        if not self._ensure_connection():
            return []

        emails = []
        if existing_message_ids is None:
            existing_message_ids = set()

        try:
            self.imap_conn.select(folder)

            # Build search criteria
            search_criteria = "ALL"
            if since_date:
                date_str = since_date.strftime("%d-%b-%Y")
                search_criteria = f'(SINCE {date_str})'

            _, message_numbers = self.imap_conn.search(None, search_criteria)
            message_list = message_numbers[0].split()

            # Get latest emails first
            message_list = message_list[-limit:] if len(message_list) > limit else message_list
            message_list.reverse()

            print(f"[IMAP] Found {len(message_list)} emails matching criteria")

            # 优化：先获取所有邮件的 MESSAGE-ID，过滤掉已存在的
            new_emails_uids = []
            if existing_message_ids:
                # 归一化已存在的 message_ids（使用统一函数）
                normalized_existing = set(
                    normalize_message_id(mid) for mid in existing_message_ids if mid
                )

                print(f"[IMAP] Pre-filtering against {len(normalized_existing)} existing emails...")
                # 调试：检查最新几封邮件（message_list[0] 是最新的，因为已 reverse）
                print(f"[IMAP DEBUG] First 3 UIDs (newest): {message_list[:3]}, Last 3 UIDs (oldest): {message_list[-3:]}")
                for num in message_list[:3]:  # 前3个是最新的
                    try:
                        _, header_data = self.imap_conn.fetch(num, "(BODY[HEADER.FIELDS (MESSAGE-ID DATE SUBJECT)])")
                        if header_data[0]:
                            header_text = header_data[0][1].decode('utf-8', errors='ignore')
                            print(f"[IMAP DEBUG] Newest email {num}: {header_text[:300]}")
                    except Exception as e:
                        print(f"[IMAP DEBUG] Error: {e}")

                for num in message_list:
                    try:
                        # 只获取 MESSAGE-ID 头，非常快
                        _, header_data = self.imap_conn.fetch(num, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
                        if header_data[0]:
                            header_text = header_data[0][1].decode('utf-8', errors='ignore')
                            # 提取 MESSAGE-ID
                            match = re.search(r'Message-ID:\s*(<[^>]+>|[^\s]+)', header_text, re.IGNORECASE)
                            if match:
                                raw_msg_id = match.group(1)
                                # 使用统一的归一化函数
                                normalized_msg_id = normalize_message_id(raw_msg_id)
                                if normalized_msg_id not in normalized_existing:
                                    new_emails_uids.append(num)
                            else:
                                # 没有 MESSAGE-ID，需要获取
                                new_emails_uids.append(num)
                    except Exception as e:
                        # 出错则保留该邮件进行完整获取
                        new_emails_uids.append(num)

                print(f"[IMAP] After pre-filter: {len(new_emails_uids)} new emails to fetch")
            else:
                new_emails_uids = message_list

            # 只获取新邮件的完整内容
            for num in new_emails_uids:
                try:
                    _, msg_data = self.imap_conn.fetch(num, "(RFC822)")
                    email_body = msg_data[0][1]
                    parsed_email = self._parse_email(email_body)
                    if parsed_email:
                        emails.append(parsed_email)
                except Exception as e:
                    print(f"Error parsing email {num}: {e}")
                    continue

        except Exception as e:
            print(f"Error fetching emails: {e}")

        return emails

    # IMAP文件夹映射（支持多种邮件服务商）
    # 格式：{标准名: [可能的IMAP名称列表]}
    IMAP_FOLDER_ALIASES = {
        "inbox": ["INBOX", "收件箱"],
        "sent": ["Sent Messages", "Sent", "已发送", "Sent Items", "INBOX.Sent"],
        "drafts": ["Drafts", "草稿箱", "草稿", "INBOX.Drafts"],
        "trash": ["Deleted Messages", "Trash", "已删除", "Deleted Items", "INBOX.Trash", "垃圾箱"],
        "spam": ["Junk", "Spam", "垃圾邮件", "INBOX.Junk", "Junk E-mail"],
    }

    # 缓存实际可用的文件夹映射
    _folder_cache: Dict[str, str] = None

    def _build_folder_map(self) -> Dict[str, str]:
        """
        动态构建文件夹映射

        根据实际可用的IMAP文件夹，匹配标准名称
        """
        if self._folder_cache is not None:
            return self._folder_cache

        available_folders = self.list_folders()
        if not available_folders:
            # 使用默认映射（21cn格式）
            self._folder_cache = {
                "inbox": "INBOX",
                "sent": "Sent Messages",
                "drafts": "Drafts",
                "trash": "Deleted Messages",
                "spam": "Junk",
            }
            return self._folder_cache

        # 构建实际映射
        folder_map = {}
        available_lower = {f.lower(): f for f in available_folders}

        for standard_name, aliases in self.IMAP_FOLDER_ALIASES.items():
            for alias in aliases:
                # 精确匹配（不区分大小写）
                if alias.lower() in available_lower:
                    folder_map[standard_name] = available_lower[alias.lower()]
                    print(f"[IMAP] Mapped '{standard_name}' -> '{folder_map[standard_name]}'")
                    break
            else:
                # 如果没有找到，使用第一个别名作为默认值
                folder_map[standard_name] = aliases[0]
                print(f"[IMAP] No match for '{standard_name}', using default '{aliases[0]}'")

        self._folder_cache = folder_map
        return folder_map

    def get_imap_folder(self, standard_name: str) -> str:
        """
        获取标准文件夹名对应的IMAP文件夹名

        Args:
            standard_name: 标准名称（inbox, sent, drafts, trash, spam）

        Returns:
            实际的IMAP文件夹名
        """
        folder_map = self._build_folder_map()
        return folder_map.get(standard_name, standard_name)

    def list_folders(self) -> List[str]:
        """列出所有可用的IMAP文件夹"""
        if not self.imap_conn:
            if not self.connect_imap():
                return []

        folders = []
        try:
            status, folder_list = self.imap_conn.list()
            if status == "OK":
                for folder_data in folder_list:
                    # 解析文件夹名称
                    if isinstance(folder_data, bytes):
                        folder_str = folder_data.decode('utf-8', errors='ignore')
                        # 提取文件夹名称（格式：(flags) "/" "folder_name"）
                        match = re.search(r'"([^"]+)"$', folder_str)
                        if match:
                            folders.append(match.group(1))
            print(f"[EmailService] Available folders: {folders}")
        except Exception as e:
            print(f"[EmailService] Error listing folders: {e}")

        return folders

    def reset_folder_cache(self):
        """重置文件夹缓存，强制重新发现"""
        self._folder_cache = None

    def fetch_emails_multi_folder(
        self,
        folders: List[str] = None,
        since_date: datetime = None,
        limit_per_folder: int = 200,
        existing_message_ids: set = None
    ) -> Dict[str, List[Dict]]:
        """
        从多个IMAP文件夹拉取邮件

        Args:
            folders: 要拉取的文件夹列表，如 ["inbox", "sent"]
            since_date: 起始日期
            limit_per_folder: 每个文件夹的邮件数量限制
            existing_message_ids: 已存在的邮件ID集合（用于去重）

        Returns:
            {
                "inbox": [email1, email2, ...],
                "sent": [email3, email4, ...]
            }
        """
        if folders is None:
            folders = ["inbox", "sent"]  # 默认拉取收件箱和已发送

        results = {}

        for folder_key in folders:
            # 使用动态文件夹映射
            imap_folder = self.get_imap_folder(folder_key)

            print(f"[EmailService] Fetching from folder: {folder_key} ({imap_folder})")

            try:
                emails = self.fetch_emails(
                    folder=imap_folder,
                    since_date=since_date,
                    limit=limit_per_folder,
                    existing_message_ids=existing_message_ids
                )

                # 根据文件夹设置direction
                for email_item in emails:
                    if folder_key == "sent":
                        email_item["direction"] = "outbound"
                    else:
                        email_item["direction"] = "inbound"

                results[folder_key] = emails
                print(f"[EmailService] Fetched {len(emails)} emails from {folder_key}")

            except Exception as e:
                print(f"[EmailService] Error fetching from {folder_key}: {e}")
                results[folder_key] = []

        return results

    def _parse_email(self, raw_email: bytes) -> Optional[Dict]:
        """Parse raw email data"""
        msg = email.message_from_bytes(raw_email)

        # Get Message-ID（归一化处理）
        message_id = normalize_message_id(msg.get("Message-ID", ""))

        # Get thread info（归一化 in_reply_to，references 保留原格式用于线程识别）
        in_reply_to = normalize_message_id(msg.get("In-Reply-To", ""))
        references = msg.get("References", "")

        # Parse from
        from_header = msg.get("From", "")
        from_name, from_email = self._parse_email_address(from_header)

        # Parse to (保留完整的收件人列表，按RFC 5322标准)
        to_header = msg.get("To", "")
        to_email_full = self._decode_header(to_header)  # 保留所有收件人

        # Parse CC
        cc_header = msg.get("Cc", "")
        cc_email_full = self._decode_header(cc_header)  # 解码抄送列表

        # Parse BCC (密送，通常收件人看不到，但发送时需要)
        bcc_header = msg.get("Bcc", "")
        bcc_email_full = self._decode_header(bcc_header)

        # Parse Reply-To (回复地址，可能与发件人不同)
        reply_to_header = msg.get("Reply-To", "")
        reply_to_email = self._decode_header(reply_to_header)

        # Parse subject
        subject = self._decode_header(msg.get("Subject", ""))

        # Parse date（多格式支持）
        date_str = msg.get("Date", "")
        received_at = self._parse_email_date(date_str)

        # Parse body
        body_text, body_html = self._get_body(msg)

        # 关键修复：如果纯文本为空但 HTML 有内容，从 HTML 提取文本
        # 这确保 body_original 不会为 NULL（某些邮件只有 HTML 格式）
        if not body_text and body_html:
            body_text = self._clean_text_for_detection(body_html)


        # Detect language - 优先使用纯文本，其次使用 HTML 内容，最后使用主题
        detection_text = body_text
        if not detection_text and body_html:
            # 从 HTML 提取文本用于语言检测
            detection_text = self._clean_text_for_detection(body_html)
        if not detection_text:
            detection_text = subject
        language = self._detect_language(detection_text)

        # Get attachments
        attachments = self._get_attachments(msg, message_id)

        return {
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references": references,
            "thread_id": self._get_thread_id(message_id, in_reply_to, references),
            "from_email": from_email,
            "from_name": from_name,
            "to_email": to_email_full,      # 完整收件人列表
            "cc_email": cc_email_full,      # 完整抄送列表
            "bcc_email": bcc_email_full,    # 密送列表
            "reply_to": reply_to_email,     # 回复地址
            "subject_original": subject,
            "body_original": body_text,
            "body_html": body_html,
            "language_detected": language,
            "direction": "inbound",
            "received_at": received_at,
            "attachments": attachments
        }

    def _decode_header(self, header: str) -> str:
        """Decode email header"""
        if not header:
            return ""
        decoded_parts = decode_header(header)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(encoding or "utf-8", errors="replace"))
                except Exception:
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)

    def _parse_email_address(self, header: str) -> Tuple[str, str]:
        """Parse email address from header"""
        header = self._decode_header(header)
        match = re.search(r'([^<]*)<([^>]+)>', header)
        if match:
            name = match.group(1).strip().strip('"')
            email_addr = match.group(2).strip()
            return name, email_addr
        return "", header.strip()

    def _extract_email_address(self, header: str) -> str:
        """Extract email address from header"""
        header = self._decode_header(header)
        match = re.search(r'<([^>]+)>', header)
        if match:
            return match.group(1)
        return header.strip()

    # 日期解析失败计数（用于统计）
    _date_parse_failures = []

    def _parse_email_date(self, date_str: str) -> datetime:
        """解析邮件日期，支持多种格式

        Args:
            date_str: 日期字符串

        Returns:
            datetime 对象，解析失败时返回当前时间并记录详细日志
        """
        if not date_str:
            print("[Date] 日期字符串为空，使用当前时间")
            return datetime.utcnow()

        original_date_str = date_str  # 保留原始字符串用于日志

        # 1. 首先尝试标准 RFC 2822 解析
        try:
            result = parsedate_to_datetime(date_str)
            return result
        except Exception as e:
            # 记录但继续尝试其他方式
            pass

        # 2. 尝试 dateutil 解析（更宽松）
        from dateutil import parser as dateutil_parser

        # 清理日期字符串
        cleaned = re.sub(r'\([^)]*\)', '', date_str).strip()  # 移除括号内容如 (CST)
        cleaned = re.sub(r'\s+', ' ', cleaned)  # 合并多余空格

        try:
            result = dateutil_parser.parse(cleaned)
            print(f"[Date] dateutil 解析成功: '{original_date_str}' -> {result}")
            return result
        except Exception:
            pass

        # 3. 尝试已知的特殊格式
        special_formats = [
            ("%Y-%m-%d %H:%M:%S", "ISO 基础格式"),
            ("%d %b %Y %H:%M:%S", "RFC 风格"),
            ("%Y/%m/%d %H:%M:%S", "斜杠分隔"),
            ("%d/%m/%Y %H:%M:%S", "欧洲格式"),
            ("%Y-%m-%dT%H:%M:%S", "ISO 8601"),
            ("%a %b %d %H:%M:%S %Y", "Unix 风格"),
            ("%Y年%m月%d日 %H:%M:%S", "中文格式"),
            ("%Y年%m月%d日", "中文日期"),
            ("%m/%d/%Y %H:%M:%S", "美国格式"),
            ("%d-%m-%Y %H:%M:%S", "欧洲短横线"),
        ]

        for fmt, fmt_name in special_formats:
            try:
                result = datetime.strptime(cleaned, fmt)
                print(f"[Date] {fmt_name} 解析成功: '{original_date_str}' -> {result}")
                return result
            except ValueError:
                continue

        # 4. 解析完全失败，记录详细日志
        failure_info = {
            "original": original_date_str,
            "cleaned": cleaned,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._date_parse_failures.append(failure_info)

        # 限制失败记录数量
        if len(self._date_parse_failures) > 100:
            self._date_parse_failures = self._date_parse_failures[-50:]

        print(f"[Date] ⚠️ 无法解析日期格式:")
        print(f"  原始: '{original_date_str}'")
        print(f"  清理后: '{cleaned}'")
        print(f"  已累计 {len(self._date_parse_failures)} 次解析失败")

        return datetime.utcnow()

    def get_date_parse_failures(self) -> List[Dict]:
        """获取日期解析失败记录（用于调试）"""
        return self._date_parse_failures.copy()

    def _get_body(self, msg) -> Tuple[Optional[str], Optional[str]]:
        """Extract text and HTML body from email"""
        text_body = None
        html_body = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text_body = payload.decode(charset, errors="replace")
                    except Exception:
                        text_body = payload.decode("utf-8", errors="replace")

                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_body = payload.decode(charset, errors="replace")
                    except Exception:
                        html_body = payload.decode("utf-8", errors="replace")
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"

            try:
                content = payload.decode(charset, errors="replace")
            except Exception:
                content = payload.decode("utf-8", errors="replace")

            if content_type == "text/plain":
                text_body = content
            elif content_type == "text/html":
                html_body = content

        return text_body, html_body

    def _get_attachments(self, msg, message_id: str) -> List[Dict]:
        """Extract attachments from email

        检测以下类型的附件：
        1. Content-Disposition: attachment
        2. Content-Disposition: inline 但有文件名（非文本/HTML）
        3. 没有 Content-Disposition 但有文件名的非文本部分
        """
        attachments = []
        seen_filenames = set()  # 避免重复

        if msg.is_multipart():
            for part in msg.walk():
                # 跳过 multipart 容器本身
                if part.get_content_maintype() == 'multipart':
                    continue

                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                filename = part.get_filename()

                # 解码文件名
                if filename:
                    filename = self._decode_header(filename)

                # 判断是否为附件
                is_attachment = False

                # 1. 明确的 attachment 类型
                if "attachment" in content_disposition.lower():
                    is_attachment = True

                # 2. inline 但有文件名，且不是纯文本/HTML（可能是图片等）
                elif "inline" in content_disposition.lower() and filename:
                    # 跳过纯文本和 HTML（这些通常是邮件正文）
                    if content_type not in ("text/plain", "text/html"):
                        is_attachment = True

                # 3. 没有 Content-Disposition 但有文件名
                elif filename and content_type not in ("text/plain", "text/html"):
                    is_attachment = True

                # 4. 检查 Content-Type 中的 name 参数（某些邮件客户端用这个）
                if not filename and not is_attachment:
                    content_type_header = part.get("Content-Type", "")
                    if "name=" in content_type_header:
                        import re
                        name_match = re.search(r'name="?([^";]+)"?', content_type_header)
                        if name_match:
                            filename = self._decode_header(name_match.group(1))
                            if content_type not in ("text/plain", "text/html"):
                                is_attachment = True

                if is_attachment and filename:
                    # 避免重复附件（使用清理后的文件名）
                    safe_filename = self._sanitize_filename(filename)
                    if safe_filename in seen_filenames:
                        continue
                    seen_filenames.add(safe_filename)

                    try:
                        # _save_attachment 内部会获取 payload 并进行安全检查
                        file_path = self._save_attachment(part, message_id, filename)
                        payload = part.get_payload(decode=True)
                        file_size = len(payload) if payload else 0

                        # 计算文件内容 hash（用于检测重复内容）
                        import hashlib
                        content_hash = hashlib.sha256(payload).hexdigest() if payload else ""

                        attachments.append({
                            "filename": safe_filename,
                            "file_path": file_path,
                            "file_size": file_size,
                            "mime_type": content_type,
                            "content_hash": content_hash  # 用于未来去重和完整性校验
                        })
                        print(f"[Attachment] Saved: {safe_filename} ({content_type}, {file_size} bytes, hash={content_hash[:16]}...)")
                    except ValueError as e:
                        # 大小限制或空内容
                        print(f"[Attachment] Skipped {filename}: {e}")
                    except IOError as e:
                        # 磁盘空间或权限问题
                        print(f"[Attachment] Error saving {filename}: {e}")
                    except Exception as e:
                        print(f"[Attachment] Unexpected error for {filename}: {e}")

        return attachments

    # 附件大小限制：100MB
    MAX_ATTACHMENT_SIZE = 100 * 1024 * 1024

    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，防止路径遍历攻击

        - 移除路径分隔符
        - 移除危险字符
        - 处理空文件名
        """
        if not filename:
            return "attachment"

        # 获取基名，移除任何路径
        filename = os.path.basename(filename)

        # 移除危险字符
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)

        # 移除开头的点（防止隐藏文件）
        filename = filename.lstrip('.')

        # 如果文件名为空，使用默认名
        if not filename or filename.isspace():
            return "attachment"

        # 限制文件名长度
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext

        return filename

    def _save_attachment(self, part, message_id: str, filename: str) -> str:
        """
        Save attachment to disk

        安全措施：
        - 文件名清理（防止路径遍历）
        - 大小限制（100MB）
        - 磁盘空间检查
        """
        import shutil

        # 1. 清理文件名
        safe_filename = self._sanitize_filename(filename)

        # 2. 获取附件内容
        payload = part.get_payload(decode=True)
        if not payload:
            raise ValueError(f"附件 {safe_filename} 内容为空")

        # 3. 检查大小限制
        if len(payload) > self.MAX_ATTACHMENT_SIZE:
            raise ValueError(
                f"附件 {safe_filename} 超过大小限制 "
                f"({len(payload) / 1024 / 1024:.1f}MB > 100MB)"
            )

        # 4. 创建目录
        safe_id = re.sub(r'[<>:"/\\|?*]', "_", message_id)
        dir_path = os.path.join(self.attachment_dir, safe_id)

        try:
            os.makedirs(dir_path, exist_ok=True)
        except (OSError, PermissionError) as e:
            raise IOError(f"无法创建附件目录: {e}")

        # 5. 检查磁盘空间（需要至少 2 倍文件大小的空间）
        try:
            stat = shutil.disk_usage(self.attachment_dir)
            if stat.free < len(payload) * 2:
                raise IOError(
                    f"磁盘空间不足，无法保存附件 {safe_filename} "
                    f"(需要 {len(payload) * 2 / 1024 / 1024:.1f}MB)"
                )
        except (OSError, AttributeError):
            # 某些系统可能不支持 disk_usage，忽略检查
            pass

        # 6. 保存文件
        file_path = os.path.join(dir_path, safe_filename)

        # 验证最终路径在目标目录内（双重检查）
        abs_dir = os.path.abspath(dir_path)
        abs_file = os.path.abspath(file_path)
        if not abs_file.startswith(abs_dir):
            raise ValueError(f"非法文件路径: {safe_filename}")

        try:
            with open(file_path, "wb") as f:
                f.write(payload)
        except (IOError, OSError) as e:
            raise IOError(f"无法保存附件 {safe_filename}: {e}")

        return file_path

    def _get_thread_id(self, message_id: str, in_reply_to: str, references: str) -> str:
        """Determine thread ID for email

        使用 References 头的第一个有效 Message-ID 作为线程 ID
        Message-ID 格式: <xxx@yyy>
        """
        if references:
            # 使用正则提取所有有效的 Message-ID（格式：<xxx@yyy>）
            # 比简单 split() 更健壮，能处理各种分隔符和格式异常
            message_id_pattern = r'<[^<>\s]+@[^<>\s]+>'
            refs = re.findall(message_id_pattern, references)
            if refs:
                # 第一个 reference 通常是原始邮件（线程起点）
                return refs[0].strip('<>')
        if in_reply_to:
            # 归一化 in_reply_to（移除尖括号）
            return in_reply_to.strip('<>')
        # 没有回复/引用信息，使用自身 message_id 作为线程 ID
        return message_id.strip('<>') if message_id else ""

    def _clean_text_for_detection(self, html: str) -> str:
        """
        从 HTML 中提取纯文本用于语言检测

        移除 HTML 标签、脚本、样式等，只保留文本内容
        """
        if not html:
            return ""

        # 移除 script 和 style 标签及其内容
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # 移除 HTML 注释
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

        # 移除所有 HTML 标签
        html = re.sub(r'<[^>]+>', ' ', html)

        # 解码 HTML 实体
        html = html.replace('&nbsp;', ' ')
        html = html.replace('&lt;', '<')
        html = html.replace('&gt;', '>')
        html = html.replace('&amp;', '&')
        html = html.replace('&quot;', '"')
        html = html.replace('&#39;', "'")

        # 清理多余空白
        html = re.sub(r'\s+', ' ', html)

        return html.strip()

    def _detect_language(self, text: str) -> str:
        """
        使用 Ollama 检测文本语言

        替代原有的 langdetect 库，提高准确率
        特别是对于英德混淆等问题
        """
        language_service = get_language_service()
        return language_service.detect_language(text)

    def send_email(self, to: str, subject: str, body: str, cc: str = None,
                   attachments: List[str] = None, is_html: bool = False,
                   in_reply_to: str = None, references: str = None) -> tuple:
        """
        Send email via SMTP

        Args:
            to: 收件人地址
            subject: 邮件主题
            body: 邮件正文
            cc: 抄送地址
            attachments: 附件路径列表
            is_html: 是否为 HTML 格式
            in_reply_to: 回复邮件的 Message-ID（用于邮件线程）
            references: 引用的 Message-ID 列表

        Returns:
            (success: bool, message_id: str or None)
        """
        from email.utils import make_msgid

        try:
            msg = MIMEMultipart()

            # 生成唯一的 Message-ID
            domain = self.email_address.split('@')[1] if '@' in self.email_address else 'local'
            message_id = make_msgid(domain=domain)
            msg["Message-ID"] = message_id

            msg["From"] = self.email_address
            msg["To"] = to
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = cc

            # 添加回复线程头信息
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                msg["References"] = references or in_reply_to

            # Add body
            if is_html:
                msg.attach(MIMEText(body, "html", "utf-8"))
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            # Add attachments
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                "Content-Disposition",
                                f"attachment; filename={os.path.basename(file_path)}"
                            )
                            msg.attach(part)

            # 构建收件人列表（使用 getaddresses 正确解析包含 <> 格式的邮箱）
            recipients = [to]
            if cc:
                # 正确解析 "Name <email>, Another <email2>" 格式
                cc_addrs = getaddresses([cc])
                recipients.extend([addr for name, addr in cc_addrs if addr])

            # Send（带重试机制）
            import time
            max_retries = 3
            retry_delay = 2  # 初始延迟秒数

            for attempt in range(max_retries):
                try:
                    if self.use_ssl:
                        with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30) as server:
                            server.login(self.email_address, self.password)
                            server.sendmail(self.email_address, recipients, msg.as_string())
                    else:
                        with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                            server.starttls()
                            server.login(self.email_address, self.password)
                            server.sendmail(self.email_address, recipients, msg.as_string())

                    return True, message_id

                except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                        ConnectionError, TimeoutError, OSError) as e:
                    # 临时网络错误，可重试
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # 指数退避：2s, 4s, 8s
                        print(f"[SMTP] 发送失败（尝试 {attempt + 1}/{max_retries}），{wait_time}s 后重试: {e}")
                        time.sleep(wait_time)
                    else:
                        print(f"[SMTP] 发送失败，已达最大重试次数: {e}")
                        return False, None

                except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as e:
                    # 认证或收件人错误，不重试
                    print(f"[SMTP] 发送失败（不可重试）: {e}")
                    return False, None

            return False, None

        except Exception as e:
            print(f"[SMTP] 邮件构建失败: {e}")
            return False, None
