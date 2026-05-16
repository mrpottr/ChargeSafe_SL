import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailService:
    # Outbound email flows stay in one place so auth routes only need to decide
    # which message to send and not how SMTP should be negotiated.
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.smtp_host and settings.smtp_from_email)

    @staticmethod
    def _ensure_configured() -> None:
        # Failing fast here produces a clear application error before the code
        # gets deep into message construction or network calls.
        if not EmailService.is_configured():
            raise ValueError("SMTP settings are not configured")

    @staticmethod
    def send_password_reset_email(recipient_email: str, reset_link: str) -> None:
        EmailService._ensure_configured()

        message = EmailMessage()
        message["Subject"] = "ChargeSafe SL Password Reset"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient_email
        message.set_content(
            "We received a request to reset your ChargeSafe SL password.\n\n"
            f"Open this link to continue:\n{reset_link}\n\n"
            "This link will expire in 1 hour.\n"
            "If you did not request a reset, you can safely ignore this email."
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

    @staticmethod
    def send_email_verification_email(recipient_email: str, verification_link: str) -> None:
        EmailService._ensure_configured()

        message = EmailMessage()
        message["Subject"] = "Verify your ChargeSafe SL account"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient_email
        message.set_content(
            "Welcome to ChargeSafe SL.\n\n"
            "Please verify your email address to continue creating your account:\n"
            f"{verification_link}\n\n"
            "After verification, you will be asked to set up Microsoft Authenticator before first access.\n"
            "If you did not create this account, you can safely ignore this email."
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

    @staticmethod
    def send_account_lockout_email(recipient_email: str, locked_until) -> None:
        EmailService._ensure_configured()

        unlock_at = locked_until.strftime("%Y-%m-%d %H:%M:%S %Z") if locked_until else "in 30 minutes"

        message = EmailMessage()
        message["Subject"] = "ChargeSafe SL Account Temporarily Locked"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient_email
        message.set_content(
            "Your ChargeSafe SL account has been temporarily locked after 5 failed login attempts.\n\n"
            f"You can try again after: {unlock_at}\n\n"
            "If this was not you, we recommend changing your password once access is restored."
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
