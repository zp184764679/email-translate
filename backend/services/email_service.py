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
from langdetect import detect, detect_langs, LangDetectException


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
        """Extract attachments from email"""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header(filename)
                        # Save attachment
                        file_path = self._save_attachment(part, message_id, filename)
                        attachments.append({
                            "filename": filename,
                            "file_path": file_path,
                            "file_size": len(part.get_payload(decode=True) or b""),
                            "mime_type": part.get_content_type()
                        })

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
        """Detect language of text with improved accuracy"""
        if not text or len(text.strip()) < 10:
            return "unknown"

        # 清理文本：移除邮件签名、HTML标签等噪音
        clean_text = self._clean_text_for_detection(text)
        if len(clean_text.strip()) < 20:
            return "unknown"

        try:
            # 使用 detect_langs 获取概率
            langs = detect_langs(clean_text)
            if not langs:
                return "unknown"

            top_lang = langs[0]
            lang_code = top_lang.lang
            confidence = top_lang.prob

            # 如果置信度低于 0.5，认为不确定
            if confidence < 0.5:
                return "unknown"

            # 语言映射
            lang_map = {
                "zh-cn": "zh", "zh-tw": "zh", "zh": "zh",
                "en": "en",
                "ja": "ja",
                "ko": "ko",
                "de": "de",  # 德语
                "fr": "fr",  # 法语
                "es": "es",  # 西班牙语
                "it": "it",  # 意大利语
                "pt": "pt",  # 葡萄牙语
                "nl": "nl",  # 荷兰语
                "ru": "ru",  # 俄语
            }

            detected = lang_map.get(lang_code, lang_code)

            # 对于西方语言，如果置信度不够高且第二选项是英语，倾向于英语
            # 这是因为 langdetect 对于英德、英法等容易混淆
            if detected in ["de", "fr", "nl", "es", "it", "pt"] and confidence < 0.8:
                if len(langs) > 1 and langs[1].lang == "en" and langs[1].prob > 0.2:
                    detected = "en"

            return detected

        except LangDetectException:
            return "unknown"

    def _clean_text_for_detection(self, text: str) -> str:
        """Clean text for better language detection"""
        import re
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 移除 URL
        text = re.sub(r'http[s]?://\S+', ' ', text)
        # 移除邮箱地址
        text = re.sub(r'\S+@\S+\.\S+', ' ', text)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 取前 500 字符进行检测（避免签名等噪音影响）
        return text[:500].strip()

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
