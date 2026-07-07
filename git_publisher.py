from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Iterable


LOGGER = logging.getLogger(__name__)


class GitPublisher:
    def __init__(
        self,
        repo_path: str,
        remote: str = "origin",
        branch: str = "main",
        push_retry_times: int = 3,
    ) -> None:
        self.repo_path = Path(repo_path)
        self.remote = remote
        self.branch = branch
        self.push_retry_times = push_retry_times

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            args,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"命令执行失败: {' '.join(args)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def _ensure_repo(self) -> None:
        self._run("git", "rev-parse", "--is-inside-work-tree")

    def get_remote_url(self) -> str:
        return self._run("git", "remote", "get-url", self.remote).stdout.strip()

    def get_remote_owner(self) -> str | None:
        remote_url = self.get_remote_url()
        if not remote_url:
            return None

        patterns = [
            r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
            r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
            r"ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, remote_url, flags=re.IGNORECASE)
            if match:
                owner = match.group("owner").strip()
                return owner or None
        return None

    def _has_staged_changes(self) -> bool:
        result = self._run("git", "diff", "--cached", "--quiet", check=False)
        return result.returncode != 0

    def get_head_commit(self) -> str:
        return self._run("git", "rev-parse", "HEAD").stdout.strip()

    def add_commit_push(self, file_paths: Iterable[str], commit_message: str) -> dict:
        self._ensure_repo()

        normalized_paths = [p.replace("\\", "/") for p in file_paths if p]
        if not normalized_paths:
            raise ValueError("没有需要提交的文件路径")

        self._run("git", "add", "--", *normalized_paths)

        if not self._has_staged_changes():
            LOGGER.info("没有检测到暂存区变化，跳过 commit/push")
            return {
                "pushed": False,
                "commit": self.get_head_commit(),
                "message": "no staged changes",
            }

        self._run("git", "commit", "-m", commit_message)
        commit_hash = self.get_head_commit()
        self._push_with_retry()

        return {
            "pushed": True,
            "commit": commit_hash,
            "message": commit_message,
        }

    def _push_with_retry(self) -> None:
        last_error = ""

        for attempt in range(1, self.push_retry_times + 1):
            result = self._run("git", "push", self.remote, self.branch, check=False)
            if result.returncode == 0:
                return

            last_error = (
                f"第 {attempt} 次 git push 失败\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
            LOGGER.warning(last_error)

            if attempt < self.push_retry_times:
                self._run("git", "pull", "--rebase", self.remote, self.branch, check=False)
                time.sleep(min(attempt * 2, 10))

        raise RuntimeError(f"git push 最终失败:\n{last_error}")
