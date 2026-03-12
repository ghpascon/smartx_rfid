class AlertsManager:
    def __init__(self):
        self.alerts = []

    def get_alerts(self):
        alerts = self.alerts.copy()
        self.alerts.clear()  # Clear after fetching
        return alerts

    def add_alert(self, message: str, level: str = "info"):
        alert = {"message": message, "level": level}
        self.alerts.append(alert)

    def add_info(self, message: str):
        self.add_alert(message, "info")

    def add_warning(self, message: str):
        self.add_alert(message, "warning")

    def add_error(self, message: str):
        self.add_alert(message, "error")

    def add_success(self, message: str):
        self.add_alert(message, "success")
