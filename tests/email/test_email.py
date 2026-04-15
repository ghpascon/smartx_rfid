import pytest

from smartx_rfid.email.main import EmailManager


def test_email_manager_init():
    manager = EmailManager(
        smtp_server="smtp.example.com",
        smtp_port=587,
        username="user@example.com",
        password="password123",
        use_tls=True,
        default_from="noreply@example.com",
    )
    assert manager.smtp_server == "smtp.example.com"
    assert manager.smtp_port == 587
    assert manager.username == "user@example.com"
    assert manager.password == "password123"
    assert manager.use_tls is True
    assert manager.default_from == "noreply@example.com"


@pytest.mark.asyncio
async def test_email_manager_test_connection_fail():
    manager = EmailManager(
        smtp_server="invalid.smtp.server", smtp_port=587, username="user@example.com", password="wrongpassword"
    )
    assert await manager.test_connection() is False


@pytest.mark.asyncio
async def test_send_email_fail():
    manager = EmailManager(
        smtp_server="invalid.smtp.server", smtp_port=587, username="user@example.com", password="wrongpassword"
    )
    result = await manager.send_email(
        subject="Test Email", body="This is a test email.", to_addresses=["recipient@example.com"]
    )
    assert result is False
