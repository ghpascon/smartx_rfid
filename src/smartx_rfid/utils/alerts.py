class AlertsManager:
    def __init__(self):
        self.alerts = []

    def get_alerts(self):
        alerts = self.alerts.copy()
        self.alerts.clear()  # Clear after fetching
        return alerts

    def add_alert(self, message: str, level: str = "info", style: str = "toast"):
        if style not in ["toast", "modal"]:
            style = "toast"
        alert = {"message": message, "level": level, "style": style}
        self.alerts.append(alert)

    def add_info(self, message: str, style: str = "toast"):
        self.add_alert(message, "info", style)

    def add_warning(self, message: str, style: str = "toast"):
        self.add_alert(message, "warning", style)

    def add_error(self, message: str, style: str = "toast"):
        self.add_alert(message, "error", style)

    def add_success(self, message: str, style: str = "toast"):
        self.add_alert(message, "success", style)
