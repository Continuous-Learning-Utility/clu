"""Backup manager: creates timestamped backups before file modifications."""

import os
import shutil
from datetime import datetime


class BackupManager:
    """
    Manages file backups for rollback capability.

    Before any write, copies the original file to a timestamped backup directory.
    Supports full rollback or per-file rollback.
    """

    def __init__(self, backup_dir: str):
        self.backup_base = backup_dir
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = os.path.join(backup_dir, self._session_id)
        self.modified_files: list[dict] = []

    def backup(self, file_path: str, project_root: str):
        """
        Create a backup of a file before modification.

        Args:
            file_path: Absolute path to the file to back up.
            project_root: Absolute path to the project root (for relative path calculation).
        """
        if not os.path.isfile(file_path):
            return

        rel = os.path.relpath(file_path, project_root)
        backup_path = os.path.join(self._session_dir, rel)

        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(file_path, backup_path)

        self.modified_files.append({
            "original": file_path,
            "backup": backup_path,
            "relative": rel.replace("\\", "/"),
            "timestamp": datetime.now().isoformat(),
        })

    def rollback(self) -> int:
        """
        Restore all files from backup (reverse order).

        Returns:
            Number of files restored.
        """
        count = 0
        for entry in reversed(self.modified_files):
            src = entry["backup"]
            dst = entry["original"]
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                count += 1
        return count

    def rollback_file(self, file_path: str) -> bool:
        """
        Restore a specific file from the most recent backup.

        Returns:
            True if the file was restored, False if no backup found.
        """
        normalized = os.path.normpath(file_path)
        for entry in reversed(self.modified_files):
            if os.path.normpath(entry["original"]) == normalized:
                shutil.copy2(entry["backup"], entry["original"])
                return True
        return False

    @property
    def session_dir(self) -> str:
        return self._session_dir
