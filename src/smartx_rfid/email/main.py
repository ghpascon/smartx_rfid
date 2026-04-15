import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import List, Optional
import mimetypes
import os


class EmailManager:
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        use_tls: bool = True,
        default_from: Optional[str] = None,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.default_from = default_from or username

    def _build_message(
        self,
        subject: str,
        body: str,
        to_addresses: List[str],
        from_address: Optional[str] = None,
        cc: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        subtype: str = "plain",
    ) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_address or self.default_from
        msg["To"] = ", ".join(to_addresses)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg.set_content(body, subtype=subtype)

        # Add attachments
        if attachments:
            for file_path in attachments:
                if not os.path.isfile(file_path):
                    logging.warning(f"Attachment file not found: {file_path}")
                    continue
                ctype, encoding = mimetypes.guess_type(file_path)
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, attachment_subtype = ctype.split("/", 1)
                with open(file_path, "rb") as f:
                    file_data = f.read()
                msg.add_attachment(
                    file_data,
                    maintype=maintype,
                    subtype=attachment_subtype,
                    filename=os.path.basename(file_path),
                )

        return msg

    def _send_email_sync(
        self,
        subject: str,
        body: str,
        to_addresses: List[str],
        from_address: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        subtype: str = "plain",
    ) -> bool:
        msg = self._build_message(
            subject=subject,
            body=body,
            to_addresses=to_addresses,
            from_address=from_address,
            cc=cc,
            attachments=attachments,
            subtype=subtype,
        )

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=20) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                all_recipients = to_addresses + (cc or []) + (bcc or [])
                server.send_message(msg, from_addr=msg["From"], to_addrs=all_recipients)
            logging.info(f"Email sent to: {all_recipients}")
            return True
        except Exception as e:
            logging.error(f"Error sending email: {e}")
            return False

    async def send_email(
        self,
        subject: str,
        body: str,
        to_addresses: List[str],
        from_address: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        subtype: str = "plain",
    ) -> bool:
        return await asyncio.to_thread(
            self._send_email_sync,
            subject,
            body,
            to_addresses,
            from_address,
            cc,
            bcc,
            attachments,
            subtype,
        )

    def _test_connection_sync(self) -> bool:
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
            logging.info("SMTP connection successful.")
            return True
        except Exception as e:
            logging.error(f"SMTP connection failed: {e}")
            return False

    async def test_connection(self) -> bool:
        return await asyncio.to_thread(self._test_connection_sync)
