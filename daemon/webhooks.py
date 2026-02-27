"""Webhook handlers: receive external triggers and enqueue tasks.

Supported sources:
- GitHub (issues, push events)
- Generic JSON webhook (any source)
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass

from daemon.task_queue import TaskQueue, TaskType

logger = logging.getLogger(__name__)


@dataclass
class WebhookResult:
    """Result of processing a webhook."""
    ok: bool
    task_id: int | None = None
    message: str = ""
    skipped: bool = False


class WebhookHandler:
    """Processes incoming webhooks and enqueues tasks."""

    def __init__(
        self,
        queue: TaskQueue,
        project_path: str | None = None,
        file_extensions: list[str] | None = None,
    ):
        self.queue = queue
        self.project_path = project_path
        self.file_extensions = file_extensions or [".cs"]
        self._github_secret: str | None = None

    def set_github_secret(self, secret: str):
        """Set the secret for GitHub webhook signature verification."""
        self._github_secret = secret

    def verify_github_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not self._github_secret:
            return True  # No secret configured, skip verification

        if not signature or not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            self._github_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected}", signature)

    def handle_github(self, event_type: str, payload: dict) -> WebhookResult:
        """Process a GitHub webhook event.

        Supported events:
        - issues (opened) → enqueue task from issue body
        - push → enqueue code review of changed files
        """
        if not self.project_path:
            return WebhookResult(ok=False, message="No project path configured")

        if event_type == "issues":
            return self._handle_github_issue(payload)
        elif event_type == "push":
            return self._handle_github_push(payload)
        else:
            return WebhookResult(ok=True, skipped=True,
                                 message=f"Ignoring event type: {event_type}")

    def _handle_github_issue(self, payload: dict) -> WebhookResult:
        action = payload.get("action", "")
        if action not in ("opened", "labeled"):
            return WebhookResult(ok=True, skipped=True,
                                 message=f"Ignoring issue action: {action}")

        issue = payload.get("issue", {})
        title = issue.get("title", "Untitled")
        body = issue.get("body", "")
        number = issue.get("number", 0)
        labels = [l.get("name", "") for l in issue.get("labels", [])]

        # Only process issues with 'ai-agent' label (if labeled event)
        if action == "labeled":
            label = payload.get("label", {}).get("name", "")
            if label != "ai-agent":
                return WebhookResult(ok=True, skipped=True,
                                     message=f"Ignoring label: {label}")

        task_text = (
            f"[GitHub Issue #{number}] {title}\n\n"
            f"{body}\n\n"
            f"Labels: {', '.join(labels)}"
        )

        task_id = self.queue.enqueue(
            task_text=task_text,
            project_path=self.project_path,
            priority=5,
            task_type=TaskType.WEBHOOK,
            metadata={
                "source": "github",
                "event": "issues",
                "issue_number": number,
                "issue_title": title,
            },
        )

        logger.info("GitHub issue #%d → task #%d", number, task_id)
        return WebhookResult(ok=True, task_id=task_id,
                             message=f"Issue #{number} enqueued as task #{task_id}")

    def _handle_github_push(self, payload: dict) -> WebhookResult:
        commits = payload.get("commits", [])
        if not commits:
            return WebhookResult(ok=True, skipped=True, message="No commits in push")

        ref = payload.get("ref", "")
        changed_files = set()
        for commit in commits:
            changed_files.update(commit.get("added", []))
            changed_files.update(commit.get("modified", []))

        # Filter to configured file extensions
        source_files = [
            f for f in changed_files
            if any(f.endswith(ext) for ext in self.file_extensions)
        ]
        if not source_files:
            ext_label = "/".join(self.file_extensions)
            return WebhookResult(ok=True, skipped=True,
                                 message=f"No {ext_label} files changed in push")

        task_text = (
            f"[GitHub Push to {ref}] Review recently pushed changes.\n\n"
            f"Changed files:\n" +
            "\n".join(f"- {f}" for f in sorted(source_files)[:20]) +
            f"\n\nTotal: {len(source_files)} file(s) changed across {len(commits)} commit(s).\n"
            "Review these files for potential issues, build errors, or code quality problems."
        )

        task_id = self.queue.enqueue(
            task_text=task_text,
            project_path=self.project_path,
            priority=3,
            task_type=TaskType.WEBHOOK,
            metadata={
                "source": "github",
                "event": "push",
                "ref": ref,
                "files_changed": len(source_files),
                "role": "reviewer",
            },
        )

        logger.info("GitHub push (%d files) → task #%d", len(source_files), task_id)
        return WebhookResult(ok=True, task_id=task_id,
                             message=f"Push review enqueued as task #{task_id}")

    def handle_generic(self, payload: dict) -> WebhookResult:
        """Process a generic webhook with a task payload.

        Expected format:
        {
            "task": "Description of what to do",
            "priority": 0,        // optional
            "role": "coder",      // optional
            "metadata": {}        // optional
        }
        """
        if not self.project_path:
            return WebhookResult(ok=False, message="No project path configured")

        task_text = payload.get("task", "")
        if not task_text:
            return WebhookResult(ok=False, message="Missing 'task' field in payload")

        role = payload.get("role")
        meta = payload.get("metadata", {})
        meta["source"] = "webhook"
        if role:
            meta["role"] = role

        task_id = self.queue.enqueue(
            task_text=task_text,
            project_path=self.project_path,
            priority=payload.get("priority", 0),
            task_type=TaskType.WEBHOOK,
            metadata=meta,
        )

        logger.info("Generic webhook → task #%d", task_id)
        return WebhookResult(ok=True, task_id=task_id,
                             message=f"Task #{task_id} enqueued")
