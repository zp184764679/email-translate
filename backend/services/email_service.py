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

    def connect_imap(self) -> bool:
        """Connect to IMAP server"""
        try:
            if self.use_ssl:
                self.imap_conn = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            else:
                self.imap_conn = imaplib.IMAP4(self.imap_server, self.imap_port)
            self.imap_conn.login(self.email_address, self.password)
            return True
        except Exception as e:
            print(f"IMAP connection error: {e}")
            return False

    def disconnect_imap(self):
        """Disconnect from IMAP server"""
        if self.imap_conn:
            try:
                self.imap_conn.logout()
            except Exception:
                pass
            self.imap_conn = None

    def fetch_emails(self, folder: str = "INBOX", since_date: datetime = None,
                     limit: int = 500) -> List[Dict]:
        """Fetch emails from mailbox"""
        if not self.imap_conn:
            if not self.connect_imap():
                return []

        emails = []
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

            for num in message_list:
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

    # IMAP文件夹映射（21cn企业邮箱）
    IMAP_FOLDER_MAP = {
        "inbox": "INBOX",
        "sent": "Sent Messages",      # 已发送
        "drafts": "Drafts",           # 草稿
        "trash": "Deleted Messages",  # 已删除
        "spam": "Junk",               # 垃圾邮件
    }

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

    def fetch_emails_multi_folder(
        self,
        folders: List[str] = None,
        since_date: datetime = None,
        limit_per_folder: int = 200
    ) -> Dict[str, List[Dict]]:
        """
        从多个IMAP文件夹拉取邮件

        Args:
            folders: 要拉取的文件夹列表，如 ["inbox", "sent"]
            since_date: 起始日期
            limit_per_folder: 每个文件夹的邮件数量限制

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
            # 获取IMAP文件夹名称
            imap_folder = self.IMAP_FOLDER_MAP.get(folder_key, folder_key)

            print(f"[EmailService] Fetching from folder: {folder_key} ({imap_folder})")

            try:
                emails = self.fetch_emails(
                    folder=imap_folder,
                    since_date=since_date,
                    limit=limit_per_folder
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

        # Get Message-ID
        message_id = msg.get("Message-ID", "")

        # Get thread info
        in_reply_to = msg.get("In-Reply-To", "")
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

        # Parse date
        date_str = msg.get("Date", "")
        try:
            received_at = parsedate_to_datetime(date_str)
        except Exception:
            received_at = datetime.utcnow()

        # Parse body
        body_text, body_html = self._get_body(msg)

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
                    # 避免重复附件
                    if filename in seen_filenames:
                        continue
                    seen_filenames.add(filename)

                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            file_path = self._save_attachment(part, message_id, filename)
                            attachments.append({
                                "filename": filename,
                                "file_path": file_path,
                                "file_size": len(payload),
                                "mime_type": content_type
                            })
                            print(f"[Attachment] Found: {filename} ({content_type}, {len(payload)} bytes)")
                    except Exception as e:
                        print(f"[Attachment] Error saving {filename}: {e}")

        return attachments

    def _save_attachment(self, part, message_id: str, filename: str) -> str:
        """Save attachment to disk"""
        # Create directory for this email
        safe_id = re.sub(r'[<>:"/\\|?*]', "_", message_id)
        dir_path = os.path.join(self.attachment_dir, safe_id)
        os.makedirs(dir_path, exist_ok=True)

        file_path = os.path.join(dir_path, filename)
        with open(file_path, "wb") as f:
            f.write(part.get_payload(decode=True))

        return file_path

    def _get_thread_id(self, message_id: str, in_reply_to: str, references: str) -> str:
        """Determine thread ID for email"""
        if references:
            # First reference is usually the original email
            refs = references.split()
            return refs[0] if refs else message_id
        elif in_reply_to:
            return in_reply_to
        return message_id

    def _detect_language(self, text: str) -> str:
        """
        使用 Ollama 检测文本语言

        替代原有的 langdetect 库，提高准确率
        特别是对于英德混淆等问题
        """
        language_service = get_language_service()
        return language_service.detect_language(text)

    def send_email(self, to: str, subject: str, body: str, cc: str = None,
                   attachments: List[str] = None, is_html: bool = False) -> bool:
        """Send email via SMTP"""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = cc

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

            # Send
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                    server.login(self.email_address, self.password)
                    server.sendmail(self.email_address, recipients, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.email_address, self.password)
                    server.sendmail(self.email_address, recipients, msg.as_string())

            return True

        except Exception as e:
            print(f"Error sending email: {e}")
            return False
