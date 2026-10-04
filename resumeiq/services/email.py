"""Outbound email (password reset). Uses SMTP when configured.

In development without SMTP, the reset link is written to the log so the flow
can be tested locally. In production without SMTP nothing sensitive is logged.
"""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def send_password_reset(user, raw_token):
    cfg = current_app.config
    link = f"{cfg['APP_BASE_URL'].rstrip('/')}/reset-password?token={raw_token}"
    if not cfg.get("SMTP_HOST"):
        if cfg.get("ENV_NAME") == "development":
            log.warning("DEV ONLY - password reset link for user %s: %s", user.id, link)
        else:
            log.error("password_reset_email_not_sent: SMTP is not configured")
        return False
    msg = EmailMessage()
    msg["Subject"] = "Reset your ResumeIQ password"
    msg["From"] = cfg["SMTP_FROM"]
    msg["To"] = user.email
    msg.set_content(
        f"Hi {user.full_name},\n\nSomeone requested a password reset for your ResumeIQ account. "
        f"This link is valid for {cfg['PASSWORD_RESET_MINUTES']} minutes:\n\n{link}\n\n"
        "If you didn't request this, you can ignore this email.\n")
    try:
        with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as smtp:
            smtp.starttls()
            if cfg.get("SMTP_USER"):
                smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception("password_reset_email_failed")
        return False
