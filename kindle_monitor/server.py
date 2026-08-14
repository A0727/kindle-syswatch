from __future__ import annotations

import argparse
import hmac
import json
import os
import socket
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .codex_usage import CodexUsage, CodexUsageClient
from .config import Settings, load_settings
from .render import DashboardRenderer
from .sensors import SensorSampler


class MonitorState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sensors = SensorSampler(
            settings.sensor_bridge,
            settings.sample_interval_seconds,
            settings.ryzen_master_cli,
            settings.amd_sample_interval_seconds,
        )
        self.codex_client = CodexUsageClient(settings.codex_binary)
        self.renderer = DashboardRenderer(settings)
        self._codex = CodexUsage(False, error="not fetched yet")
        self._codex_lock = threading.Lock()
        self._stop = threading.Event()
        self._codex_thread = threading.Thread(target=self._codex_loop, name="codex-usage", daemon=True)

    def start(self) -> None:
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.sensors.start()
        self._codex_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.sensors.stop()

    def _codex_loop(self) -> None:
        while not self._stop.is_set():
            usage = self.codex_client.read()
            for _ in range(2):
                if usage.available or self._stop.wait(5):
                    break
                usage = self.codex_client.read()

            with self._codex_lock:
                current = self._codex
                if usage.available:
                    self._codex = usage
                elif current.available and time.time() - current.fetched_at < 300:
                    # Keep the last successful quota snapshot through brief
                    # network failures instead of flashing OFFLINE on Kindle.
                    self._codex = replace(current, error=usage.error)
                else:
                    self._codex = usage
            self._stop.wait(self.settings.codex_interval_seconds)

    def codex(self) -> CodexUsage:
        with self._codex_lock:
            return self._codex

    def dashboard(self) -> bytes:
        content, preview = self.renderer.render(self.sensors.snapshot(), self.codex())
        preview.save(self.settings.runtime_dir / "dashboard-preview.png")
        return content

    def status(self) -> dict[str, Any]:
        snapshot = self.sensors.snapshot()
        codex = self.codex()
        metrics = self.renderer.metrics(snapshot)
        cpu_sensor_clock = snapshot.find(
            "Cpu",
            "Clock",
            ("cores (average effective)", "windows average effective", "cores (average)"),
            positive=True,
        )
        return {
            "ok": not snapshot.error,
            "generated_at": int(time.time()),
            "sensors": {
                "cpu_load": metrics.cpu_load,
                "cpu_temp": metrics.cpu_temp,
                "cpu_power": metrics.cpu_power,
                "cpu_clock": metrics.cpu_clock,
                "cpu_sensor_clock": cpu_sensor_clock,
                "gpu_load": metrics.gpu_load,
                "gpu_temp": metrics.gpu_temp,
                "memory_percent": snapshot.memory_percent,
                "disk_percent": snapshot.disk_percent,
                "error": snapshot.error,
                "amd_error": snapshot.amd_error,
            },
            "codex": asdict(codex),
        }


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "KindleMonitor/0.1"

    @property
    def state(self) -> MonitorState:
        return self.server.state  # type: ignore[attr-defined]

    def _send(self, status: int, content_type: str, body: bytes, *, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        if not cache:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self.state.settings.auth_token
        if not expected:
            return self.client_address[0] in ("127.0.0.1", "::1")
        query = parse_qs(urlsplit(self.path).query)
        supplied = (query.get("token") or [""])[0]
        return hmac.compare_digest(expected, supplied)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path != "/healthz" and not self._authorized():
            self._send(403, "text/plain; charset=utf-8", b"forbidden\n")
            return
        if path in ("/", "/dashboard.png"):
            self._send(200, "image/png", self.state.dashboard())
            return
        if path == "/api/status":
            body = json.dumps(self.state.status(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", b"ok\n")
            return
        self._send(404, "text/plain; charset=utf-8", b"not found\n")

    def log_message(self, fmt: str, *args: object) -> None:
        # Do not log the query string because it carries the Kindle access token.
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} request completed")


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[RequestHandler], state: MonitorState) -> None:
        super().__init__(address, handler)
        self.state = state


def local_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = entry[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except socket.gaierror:
        pass
    return sorted(addresses)


def run(settings: Settings) -> None:
    state = MonitorState(settings)
    state.start()
    server = MonitorServer((settings.bind_host, settings.port), RequestHandler, state)
    pid_file = settings.runtime_dir / "server.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    print(f"Kindle monitor listening on {settings.bind_host}:{settings.port}")
    for address in local_addresses():
        print(f"  http://{address}:{settings.port}/dashboard.png")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.stop()
        try:
            if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                pid_file.unlink()
        except (FileNotFoundError, OSError):
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Kindle system dashboard")
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    args = parser.parse_args()
    run(load_settings(args.config))


if __name__ == "__main__":
    main()
