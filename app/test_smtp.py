import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")

def test_smtp_connection():
    print(f"Testing SMTP connection to {SMTP_HOST}:{SMTP_PORT}...")
    print(f" Server: {SMTP_HOST}:{SMTP_PORT}")
    print(f" User: {SMTP_USER}")
    print(f" Destination: {ALERT_EMAIL_TO}")

    msg = EmailMessage()
    msg['Subject'] = "SMTP Test Email"
    msg['From'] = SMTP_USER
    msg['To'] = ALERT_EMAIL_TO
    msg.set_content("This is a test email to verify SMTP configuration.")

    try:
        print("Connecting to SMTP server...")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            print("Starting TLS...")
            server.starttls()

            print("Logging in...")
            server.login(SMTP_USER, SMTP_PASS)

            print("Sending test email...")
            server.send_message(msg)
        print("Test email sent successfully!")

    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP Authentication Error: {e}")
        print("Please check your SMTP username and password.")
        print(f"Server response: {e}")
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("Please check your SMTP server and port.")
        print(f"Server response: {e}")
    except Exception as e:
        print(f"An error occurred while sending the test email: {e}")
if __name__ == "__main__":
    test_smtp_connection()