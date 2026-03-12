from smartx_rfid.utils.alerts import AlertsManager


def test_add_and_get_alert():
    am = AlertsManager()
    am.add_alert("Test message", "info")
    alerts = am.get_alerts()
    assert len(alerts) == 1
    assert alerts[0]["message"] == "Test message"
    assert alerts[0]["level"] == "info"
    # After get_alerts, alerts should be cleared
    assert am.get_alerts() == []


def test_add_info():
    am = AlertsManager()
    am.add_info("Info message")
    alerts = am.get_alerts()
    assert len(am.alerts) == 0
    assert alerts[0]["level"] == "info"
    assert alerts[0]["message"] == "Info message"


def test_add_warning():
    am = AlertsManager()
    am.add_warning("Warning message")
    alerts = am.get_alerts()
    assert len(am.alerts) == 0
    assert alerts[0]["level"] == "warning"
    assert alerts[0]["message"] == "Warning message"


def test_add_error():
    am = AlertsManager()
    am.add_error("Error message")
    alerts = am.get_alerts()
    assert alerts[0]["level"] == "error"
    assert alerts[0]["message"] == "Error message"


def test_add_success():
    am = AlertsManager()
    am.add_success("Success message")
    alerts = am.get_alerts()
    assert alerts[0]["level"] == "success"
    assert alerts[0]["message"] == "Success message"


def test_multiple_alerts():
    am = AlertsManager()
    am.add_info("Info")
    am.add_warning("Warn")
    am.add_error("Err")
    am.add_success("Ok")
    alerts = am.get_alerts()
    assert len(alerts) == 4
    levels = [a["level"] for a in alerts]
    assert levels == ["info", "warning", "error", "success"]
    messages = [a["message"] for a in alerts]
    assert messages == ["Info", "Warn", "Err", "Ok"]
