"""Notification channels: send alerts to external services.

Supported channels:
- Desktop (Windows toast / Linux notify-send / macOS osascript)
- Discord (webhook)
- Slack (webhook)
"""

import json
import logging
import os
import platform
import subprocess
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    pass


class Notifier:
    """Base class for notification channels."""

    def send(self, title: str, message: str, level: str = "info") -> bool:
        """Send a notification. Returns True on success."""
        raise NotImplementedError


class DesktopNotifier(Notifier):
    """Cross-platform desktop notifications."""

    def send(self, title: str, message: str, level: str = "info") -> bool:
        system = platform.system()
        try:
            if system == "Windows":
                return self._windows_toast(title, message)
            elif system == "Darwin":
                return self._macos_notify(title, message)
            elif system == "Linux":
                return self._linux_notify(title, message)
            else:
                logger.warning("Desktop notifications not supported on %s", system)
                return False
        except Exception as e:
            logger.warning("Desktop notification failed: %s", e)
            return False

    def _windows_toast(self, title: str, message: str) -> bool:
        # Try win10toast first, fallback to PowerShell
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=5, threaded=True)
            return True
        except ImportError:
            pass

        # PowerShell fallback (no extra deps)
        ps_script = (
            f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
            f'ContentType = WindowsRuntime] > $null; '
            f'$template = [Windows.UI.Notifications.ToastNotificationManager]::'
            f'GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); '
            f'$textNodes = $template.GetElementsByTagName("text"); '
            f'$textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null; '
            f'$textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null; '
            f'$toast = [Windows.UI.Notifications.ToastNotification]::new($template); '
            f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("CLU")'
            f'.Show($toast)'
        )
        try:
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True, timeout=10,
            )
            return True
        except Exception:
            return False

    def _macos_notify(self, title: str, message: str) -> bool:
        safe_title = title.replace('"', '\\"')
        safe_msg = message.replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_msg}" with title "{safe_title}"'],
            capture_output=True, timeout=5,
        )
        return True

    def _linux_notify(self, title: str, message: str) -> bool:
        subprocess.run(
            ["notify-send", title, message, "-t", "5000"],
            capture_output=True, timeout=5,
        )
        return True


class DiscordNotifier(Notifier):
    """Send notifications to a Discord channel via webhook."""

    LEVEL_COLORS = {
        "info": 3447003,     # blue
        "warning": 16776960, # yellow
        "error": 15158332,   # red
    }

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title: str, message: str, level: str = "info") -> bool:
        color = self.LEVEL_COLORS.get(level, 3447003)
        payload = {
            "embeds": [{
                "title": title,
                "description": message[:2000],
                "color": color,
                "footer": {"text": "CLU"},
            }]
        }
        return self._post(payload)

    def _post(self, payload: dict) -> bool:
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except urllib.error.URLError as e:
            logger.warning("Discord notification failed: %s", e)
            return False


class SlackNotifier(Notifier):
    """Send notifications to a Slack channel via webhook."""

    LEVEL_EMOJI = {
        "info": ":information_source:",
        "warning": ":warning:",
        "error": ":x:",
    }

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, title: str, message: str, level: str = "info") -> bool:
        emoji = self.LEVEL_EMOJI.get(level, "")
        payload = {
            "text": f"{emoji} *{title}*\n{message[:2000]}",
        }
        return self._post(payload)

    def _post(self, payload: dict) -> bool:
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except urllib.error.URLError as e:
            logger.warning("Slack notification failed: %s", e)
            return False


class NotificationManager:
    """Manages multiple notification channels and dispatches alerts."""

    def __init__(self):
        self._channels: list[tuple[str, Notifier]] = []

    def add_channel(self, name: str, notifier: Notifier):
        self._channels.append((name, notifier))
        logger.info("Notification channel added: %s", name)

    def remove_channel(self, name: str) -> bool:
        before = len(self._channels)
        self._channels = [(n, c) for n, c in self._channels if n != name]
        return len(self._channels) < before

    @property
    def channels(self) -> list[str]:
        return [name for name, _ in self._channels]

    def notify(self, title: str, message: str, level: str = "info") -> dict:
        """Send notification to all channels. Returns per-channel results."""
        results = {}
        for name, channel in self._channels:
            try:
                results[name] = channel.send(title, message, level)
            except Exception as e:
                logger.error("Notification to %s failed: %s", name, e)
                results[name] = False
        return results

    @classmethod
    def from_config(cls, config: dict) -> "NotificationManager":
        """Create NotificationManager from config dict.

        Expected config format:
        notifications:
          desktop: true
          discord_webhook: "https://discord.com/api/webhooks/..."
          slack_webhook: "https://hooks.slack.com/services/..."
        """
        mgr = cls()

        if config.get("desktop", False):
            mgr.add_channel("desktop", DesktopNotifier())

        discord_url = config.get("discord_webhook", "")
        if discord_url:
            mgr.add_channel("discord", DiscordNotifier(discord_url))

        slack_url = config.get("slack_webhook", "")
        if slack_url:
            mgr.add_channel("slack", SlackNotifier(slack_url))

        return mgr
