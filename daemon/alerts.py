"""AlertManager: persistent alerts for the dashboard.

Alerts are stored as JSON in data/alerts.json. They represent notable events
(task failures, circuit breaker trips, heartbeat findings) that the user
should be aware of.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_ALERTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "alerts.json")


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Alert:
    id: int
    level: str
    source: str        # e.g. "heartbeat", "daemon", "circuit_breaker"
    message: str
    timestamp: float
    read: bool = False
    metadata: dict | None = None


class AlertManager:
    """File-backed alert store."""

    def __init__(self, path: str | None = None, max_alerts: int = 200):
        self.path = path or DEFAULT_ALERTS_PATH
        self.max_alerts = max_alerts
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._next_id = self._load_next_id()

    def _load_alerts(self) -> list[dict]:
        if not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_alerts(self, alerts: list[dict]):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("Failed to save alerts: %s", e)

    def _load_next_id(self) -> int:
        alerts = self._load_alerts()
        if alerts:
            return max(a.get("id", 0) for a in alerts) + 1
        return 1

    def add(
        self,
        level: str,
        source: str,
        message: str,
        metadata: dict | None = None,
    ) -> int:
        """Add a new alert. Returns the alert ID."""
        alert_id = self._next_id
        self._next_id += 1

        alert = Alert(
            id=alert_id,
            level=level,
            source=source,
            message=message,
            timestamp=time.time(),
            metadata=metadata,
        )

        alerts = self._load_alerts()
        alerts.append(asdict(alert))

        # Trim oldest if over limit
        if len(alerts) > self.max_alerts:
            alerts = alerts[-self.max_alerts:]

        self._save_alerts(alerts)
        logger.info("Alert [%s] %s: %s", level, source, message[:80])
        return alert_id

    def list_alerts(
        self,
        unread_only: bool = False,
        level: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List alerts, newest first."""
        alerts = self._load_alerts()

        if unread_only:
            alerts = [a for a in alerts if not a.get("read")]
        if level:
            alerts = [a for a in alerts if a.get("level") == level]

        return list(reversed(alerts[-limit:]))

    def mark_read(self, alert_id: int) -> bool:
        """Mark a single alert as read."""
        alerts = self._load_alerts()
        for a in alerts:
            if a.get("id") == alert_id:
                a["read"] = True
                self._save_alerts(alerts)
                return True
        return False

    def mark_all_read(self) -> int:
        """Mark all alerts as read. Returns count marked."""
        alerts = self._load_alerts()
        count = 0
        for a in alerts:
            if not a.get("read"):
                a["read"] = True
                count += 1
        if count:
            self._save_alerts(alerts)
        return count

    def delete(self, alert_id: int) -> bool:
        """Delete a single alert."""
        alerts = self._load_alerts()
        new = [a for a in alerts if a.get("id") != alert_id]
        if len(new) < len(alerts):
            self._save_alerts(new)
            return True
        return False

    def clear(self) -> int:
        """Delete all alerts. Returns count deleted."""
        alerts = self._load_alerts()
        count = len(alerts)
        self._save_alerts([])
        return count

    def unread_count(self) -> int:
        alerts = self._load_alerts()
        return sum(1 for a in alerts if not a.get("read"))

    def stats(self) -> dict:
        alerts = self._load_alerts()
        return {
            "total": len(alerts),
            "unread": sum(1 for a in alerts if not a.get("read")),
            "by_level": {
                "info": sum(1 for a in alerts if a.get("level") == "info"),
                "warning": sum(1 for a in alerts if a.get("level") == "warning"),
                "error": sum(1 for a in alerts if a.get("level") == "error"),
            },
        }
