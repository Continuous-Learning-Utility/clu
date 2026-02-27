"""Tests for daemon/webhooks.py and daemon/notifiers.py."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from daemon.webhooks import WebhookHandler, WebhookResult
from daemon.notifiers import (
    NotificationManager, DesktopNotifier, DiscordNotifier, SlackNotifier,
)
from daemon.task_queue import TaskQueue


# ---- WebhookHandler ----

class TestWebhookHandler(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "tasks.db")
        self.queue = TaskQueue(db_path=self.db_path)
        self.handler = WebhookHandler(queue=self.queue, project_path="/fake/project")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- Generic webhook --

    def test_generic_enqueue(self):
        result = self.handler.handle_generic({
            "task": "Fix the login bug",
            "priority": 5,
        })
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.task_id)

        task = self.queue.get(result.task_id)
        self.assertEqual(task.payload["task"], "Fix the login bug")
        self.assertEqual(task.priority, 5)
        self.assertEqual(task.task_type, "webhook")

    def test_generic_with_role(self):
        result = self.handler.handle_generic({
            "task": "Review auth module",
            "role": "reviewer",
        })
        self.assertTrue(result.ok)
        task = self.queue.get(result.task_id)
        self.assertEqual(task.metadata.get("role"), "reviewer")

    def test_generic_missing_task(self):
        result = self.handler.handle_generic({"priority": 5})
        self.assertFalse(result.ok)
        self.assertIn("Missing", result.message)

    def test_generic_no_project(self):
        handler = WebhookHandler(queue=self.queue, project_path=None)
        result = handler.handle_generic({"task": "Do something"})
        self.assertFalse(result.ok)
        self.assertIn("project path", result.message)

    # -- GitHub webhook: issues --

    def test_github_issue_opened(self):
        payload = {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "NullRef in PlayerController",
                "body": "Getting null reference on line 50",
                "labels": [{"name": "bug"}],
            },
        }
        result = self.handler.handle_github("issues", payload)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.task_id)

        task = self.queue.get(result.task_id)
        self.assertIn("Issue #42", task.payload["task"])
        self.assertIn("NullRef", task.payload["task"])
        self.assertEqual(task.metadata.get("issue_number"), 42)

    def test_github_issue_labeled_ai_agent(self):
        payload = {
            "action": "labeled",
            "label": {"name": "ai-agent"},
            "issue": {
                "number": 7,
                "title": "Refactor movement",
                "body": "Extract input handling",
                "labels": [{"name": "ai-agent"}],
            },
        }
        result = self.handler.handle_github("issues", payload)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.task_id)

    def test_github_issue_labeled_other(self):
        payload = {
            "action": "labeled",
            "label": {"name": "documentation"},
            "issue": {"number": 8, "title": "x", "body": "", "labels": []},
        }
        result = self.handler.handle_github("issues", payload)
        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)

    def test_github_issue_closed_ignored(self):
        payload = {
            "action": "closed",
            "issue": {"number": 1, "title": "x", "body": "", "labels": []},
        }
        result = self.handler.handle_github("issues", payload)
        self.assertTrue(result.skipped)

    # -- GitHub webhook: push --

    def test_github_push_with_cs_files(self):
        payload = {
            "ref": "refs/heads/main",
            "commits": [
                {
                    "added": ["Assets/Scripts/New.cs"],
                    "modified": ["Assets/Scripts/Player.cs"],
                    "removed": [],
                },
            ],
        }
        result = self.handler.handle_github("push", payload)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.task_id)

        task = self.queue.get(result.task_id)
        self.assertIn("Push", task.payload["task"])
        self.assertIn("New.cs", task.payload["task"])
        self.assertEqual(task.metadata.get("role"), "reviewer")

    def test_github_push_no_cs_files(self):
        payload = {
            "ref": "refs/heads/main",
            "commits": [{"added": ["README.md"], "modified": [], "removed": []}],
        }
        result = self.handler.handle_github("push", payload)
        self.assertTrue(result.skipped)

    def test_github_push_empty_commits(self):
        payload = {"ref": "refs/heads/main", "commits": []}
        result = self.handler.handle_github("push", payload)
        self.assertTrue(result.skipped)

    # -- GitHub webhook: unknown event --

    def test_github_unknown_event(self):
        result = self.handler.handle_github("star", {"action": "created"})
        self.assertTrue(result.skipped)

    # -- Signature verification --

    def test_verify_signature_no_secret(self):
        # Without secret, should always pass
        self.assertTrue(self.handler.verify_github_signature(b"data", "sha256=abc"))

    def test_verify_signature_valid(self):
        import hashlib, hmac
        secret = "test-secret"
        self.handler.set_github_secret(secret)
        payload = b'{"test": true}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        self.assertTrue(self.handler.verify_github_signature(payload, sig))

    def test_verify_signature_invalid(self):
        self.handler.set_github_secret("secret")
        self.assertFalse(self.handler.verify_github_signature(b"data", "sha256=wrong"))

    def test_verify_signature_missing(self):
        self.handler.set_github_secret("secret")
        self.assertFalse(self.handler.verify_github_signature(b"data", ""))


# ---- NotificationManager ----

class TestNotificationManager(unittest.TestCase):

    def test_empty_manager(self):
        mgr = NotificationManager()
        self.assertEqual(mgr.channels, [])
        results = mgr.notify("Test", "Hello")
        self.assertEqual(results, {})

    def test_add_and_remove_channel(self):
        mgr = NotificationManager()
        mock = MagicMock()
        mgr.add_channel("test", mock)
        self.assertEqual(mgr.channels, ["test"])
        mgr.remove_channel("test")
        self.assertEqual(mgr.channels, [])

    def test_notify_calls_all_channels(self):
        mgr = NotificationManager()
        mock1 = MagicMock()
        mock1.send.return_value = True
        mock2 = MagicMock()
        mock2.send.return_value = True

        mgr.add_channel("ch1", mock1)
        mgr.add_channel("ch2", mock2)

        results = mgr.notify("Title", "Message", "warning")
        self.assertEqual(results, {"ch1": True, "ch2": True})
        mock1.send.assert_called_once_with("Title", "Message", "warning")
        mock2.send.assert_called_once_with("Title", "Message", "warning")

    def test_notify_handles_channel_error(self):
        mgr = NotificationManager()
        mock = MagicMock()
        mock.send.side_effect = Exception("Network error")
        mgr.add_channel("broken", mock)

        results = mgr.notify("Title", "Msg")
        self.assertFalse(results["broken"])

    def test_from_config_empty(self):
        mgr = NotificationManager.from_config({})
        self.assertEqual(mgr.channels, [])

    def test_from_config_desktop(self):
        mgr = NotificationManager.from_config({"desktop": True})
        self.assertEqual(mgr.channels, ["desktop"])

    def test_from_config_discord(self):
        mgr = NotificationManager.from_config({
            "discord_webhook": "https://discord.com/api/webhooks/123/abc",
        })
        self.assertEqual(mgr.channels, ["discord"])

    def test_from_config_slack(self):
        mgr = NotificationManager.from_config({
            "slack_webhook": "https://hooks.slack.com/services/T/B/x",
        })
        self.assertEqual(mgr.channels, ["slack"])

    def test_from_config_all(self):
        mgr = NotificationManager.from_config({
            "desktop": True,
            "discord_webhook": "https://discord.com/api/webhooks/123/abc",
            "slack_webhook": "https://hooks.slack.com/services/T/B/x",
        })
        self.assertEqual(len(mgr.channels), 3)


class TestDiscordNotifier(unittest.TestCase):

    @patch("daemon.notifiers.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock()
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test")
        self.assertTrue(notifier.send("Title", "Message", "error"))
        mock_urlopen.assert_called_once()

    @patch("daemon.notifiers.urllib.request.urlopen")
    def test_send_failure(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("fail")
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test")
        self.assertFalse(notifier.send("Title", "Message"))


class TestSlackNotifier(unittest.TestCase):

    @patch("daemon.notifiers.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock()
        notifier = SlackNotifier("https://hooks.slack.com/services/test")
        self.assertTrue(notifier.send("Title", "Message", "warning"))
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
