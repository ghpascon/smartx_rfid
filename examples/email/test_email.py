import os
from smartx_rfid.email.main import EmailManager
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    # Example usage
    smtp_email = os.getenv("SMTP_EMAIL", "user@example.com")
    smtp_password = os.getenv("SMTP_PASSWORD", "password123")
    manager = EmailManager(
        smtp_server="smtp.gmail.com",
        smtp_port=587,
        username=smtp_email,
        password=smtp_password,
        use_tls=True,
        default_from=smtp_email,
    )

    # Test connection
    if manager.test_connection():
        print("SMTP connection successful.")
    else:
        print("SMTP connection failed.")

    # Send a test email (edit the addresses and credentials for real use)
    result = manager.send_email(
        subject="Test Email",
        body="This is a test email sent from EmailManager.",
        to_addresses=["ghpascon.dev@gmail.com"],
        attachments=None,
    )
    if result:
        print("Email sent successfully.")
    else:
        print("Failed to send email.")
