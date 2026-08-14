from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RateWindow:
    used_percent: int
    duration_minutes: int | None
    resets_at: int | None

    @property
    def remaining_percent(self) -> int:
        return max(0, min(100, 100 - self.used_percent))


@dataclass(frozen=True)
class CodexUsage:
    available: bool
    plan_type: str | None = None
    primary: RateWindow | None = None
    secondary: RateWindow | None = None
    credit_balance: str | None = None
    unlimited_credits: bool = False
    reset_credits: int = 0
    fetched_at: float = 0.0
    error: str | None = None


class CodexUsageClient:
    """Reads the same local app-server snapshot used by Codex Settings > Usage."""

    def __init__(self, binary: Path, timeout: float = 20.0) -> None:
        self.binary = binary
        self.timeout = timeout

    @staticmethod
    def _window(raw: dict[str, Any] | None) -> RateWindow | None:
        if not raw:
            return None
        return RateWindow(
            used_percent=int(raw.get("usedPercent", 0)),
            duration_minutes=raw.get("windowDurationMins"),
            resets_at=raw.get("resetsAt"),
        )

    def read(self) -> CodexUsage:
        if not self.binary.exists():
            return CodexUsage(False, error=f"Codex binary not found: {self.binary}")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(self.binary), "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )
        lines: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=pump, name="codex-stdout", daemon=True).start()

        def send(message: dict[str, Any]) -> None:
            assert process.stdin is not None
            process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            process.stdin.flush()

        deadline = time.monotonic() + self.timeout
        try:
            send(
                {
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "clientInfo": {"name": "kindle-monitor", "version": "0.1.0"},
                        "capabilities": {"experimentalApi": True},
                    },
                }
            )

            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                line = lines.get(timeout=remaining)
                if line is None:
                    raise RuntimeError("Codex app-server exited during initialization")
                message = json.loads(line)
                if message.get("id") == 1:
                    break
            else:
                raise TimeoutError("Codex app-server initialization timed out")

            send({"method": "initialized"})
            send({"method": "account/rateLimits/read", "id": 2, "params": None})

            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                line = lines.get(timeout=remaining)
                if line is None:
                    raise RuntimeError("Codex app-server exited before returning usage")
                message = json.loads(line)
                if message.get("id") != 2:
                    continue
                if "error" in message:
                    raise RuntimeError(str(message["error"]))

                result = message.get("result") or {}
                snapshot = result.get("rateLimitsByLimitId", {}).get("codex") or result.get("rateLimits") or {}
                credits = snapshot.get("credits") or {}
                reset_credits = result.get("rateLimitResetCredits") or {}
                return CodexUsage(
                    available=True,
                    plan_type=snapshot.get("planType"),
                    primary=self._window(snapshot.get("primary")),
                    secondary=self._window(snapshot.get("secondary")),
                    credit_balance=credits.get("balance"),
                    unlimited_credits=bool(credits.get("unlimited", False)),
                    reset_credits=int(reset_credits.get("availableCount", 0)),
                    fetched_at=time.time(),
                )
            raise TimeoutError("Codex usage request timed out")
        except Exception as exception:
            return CodexUsage(False, fetched_at=time.time(), error=str(exception))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
