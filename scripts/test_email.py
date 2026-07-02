import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from dotenv import load_dotenv


def get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "y", "on")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main():
    load_dotenv()

    smtp_host = require_env("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = require_env("SMTP_USER")
    smtp_password = require_env("SMTP_PASSWORD")

    email_from = os.getenv("EMAIL_FROM", smtp_user)
    default_from_email = os.getenv(
        "DEFAULT_FROM_EMAIL",
        f"Future Smart Support <{email_from}>",
    )

    reply_to_email = os.getenv("REPLY_TO_EMAIL", email_from)

    use_tls = get_bool_env("EMAIL_USE_TLS", True)
    use_ssl = get_bool_env("EMAIL_USE_SSL", False)

    test_to_email = os.getenv("TEST_EMAIL_TO", smtp_user)

    subject = "PF Email Configuration Test"

    body = f"""
Hello,

This is a test email from the Personal Finance SaaS project.

Configuration used:

SMTP_HOST={smtp_host}
SMTP_PORT={smtp_port}
SMTP_USER={smtp_user}
EMAIL_FROM={email_from}
DEFAULT_FROM_EMAIL={default_from_email}
REPLY_TO_EMAIL={reply_to_email}
EMAIL_USE_TLS={use_tls}
EMAIL_USE_SSL={use_ssl}

If you received this email, the SMTP configuration is working.

Regards,
Personal Finance SaaS
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = default_from_email
    msg["To"] = test_to_email
    msg["Reply-To"] = reply_to_email
    msg.set_content(body)

    print("Testing email configuration...")
    print(f"SMTP server: {smtp_host}:{smtp_port}")
    print(f"SMTP user: {smtp_user}")
    print(f"From: {default_from_email}")
    print(f"To: {test_to_email}")
    print(f"Reply-To: {reply_to_email}")

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()

                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()

                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        print("")
        print("SUCCESS: Test email sent successfully.")

    except smtplib.SMTPAuthenticationError as e:
        print("")
        print("FAILED: SMTP authentication failed.")
        print("Check SMTP_USER and SMTP_PASSWORD.")
        print("For Google Workspace, use a Google App Password, not the normal password.")
        print(f"Details: {e}")

    except smtplib.SMTPRecipientsRefused as e:
        print("")
        print("FAILED: Recipient was refused.")
        print("Check TEST_EMAIL_TO or the recipient address.")
        print(f"Details: {e}")

    except smtplib.SMTPSenderRefused as e:
        print("")
        print("FAILED: Sender address was refused.")
        print("Check EMAIL_FROM / DEFAULT_FROM_EMAIL.")
        print("If using noreply@futuresmartsupport.com, make sure it is added as an alias in Google Workspace.")
        print(f"Details: {e}")

    except Exception as e:
        print("")
        print("FAILED: Could not send test email.")
        print(f"Error type: {type(e).__name__}")
        print(f"Details: {e}")


if __name__ == "__main__":
    main()