"""
Email Service for SDK Gateway
Handles email delivery with templates
"""
import asyncio
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from app.core.config import settings

MAX_RETRIES = 3

# Template engine setup
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "email"
_jinja_env: Optional[Environment] = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


class EmailService:
    """Async SMTP email delivery service"""

    def __init__(self):
        self._configured = bool(settings.SMTP_HOST and settings.SMTP_USERNAME)

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def send_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        template_vars: dict,
    ) -> bool:
        """
        Send an email using a Jinja2 HTML template.
        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured:
            print(f"⚠️ Email not configured — skipping send to {to_email}: {subject}")
            return False

        # Render template
        try:
            env = _get_jinja_env()
            template = env.get_template(f"{template_name}.html")
            html_body = template.render(**template_vars)
        except Exception as e:
            print(f"❌ Email template render failed ({template_name}): {e}")
            return False

        # Build message
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        # Retry sending (max 3 attempts)
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                smtp = aiosmtplib.SMTP(
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    use_tls=True,  # Direct SSL/TLS for port 465
                    timeout=30,
                )

                await smtp.connect()
                await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                await smtp.send_message(msg)
                await smtp.quit()

                print(f"✅ Email sent to {to_email}: {subject}")
                return True
            except (aiosmtplib.SMTPException, ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                print(f"⚠️ Email send attempt {attempt}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                last_error = e
                print(f"⚠️ Email send attempt {attempt}/{MAX_RETRIES} failed (unexpected): {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)

        print(f"❌ Email send failed after {MAX_RETRIES} attempts to {to_email}: {last_error}")
        return False


# Singleton
email_service = EmailService()
