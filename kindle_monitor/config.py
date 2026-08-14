from __future__ import annotations

import socket
import shutil
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def default_ryzen_master_cli() -> Path:
    sdk_root = Path(r"C:\Program Files\AMD\RyzenMasterSDK")
    return sdk_root / "AMDRyzenMasterCLI" / "bin-prebuilt" / "AMDRyzenMasterCLI.exe"


def default_codex_binary() -> Path:
    discovered = shutil.which("codex.exe") or shutil.which("codex")
    if discovered:
        return Path(discovered).resolve()
    return PROJECT_ROOT.parent / "work" / "codex.exe"


@dataclass(frozen=True)
class Settings:
    bind_host: str = "127.0.0.1"
    port: int = 8765
    auth_token: str = ""
    sample_interval_seconds: float = 2.0
    codex_interval_seconds: float = 60.0
    amd_sample_interval_seconds: float = 10.0
    machine_name: str = socket.gethostname().upper()
    screen_width: int = 1072
    screen_height: int = 1448
    dashboard_title: str = "KINDLE // SYSWATCH"
    cpu_name: str = "INTEL CORE I5-12490F"
    cpu_code: str = "A0"
    gpu_name: str = "AMD RADEON RX 6600 XT"
    gpu_code: str = "B1"
    status_label: str = "NEONS / 0921"
    kindle_model: str = "PW3::1072X1448"
    refresh_label: str = "REFRESH 10S  /  CLEAN CYCLE 30M"
    sensor_bridge: Path = PROJECT_ROOT / "vendor" / "librehardwaremonitor" / "KindleMonitor.SensorBridge.exe"
    ryzen_master_cli: Path = default_ryzen_master_cli()
    codex_binary: Path = default_codex_binary()
    runtime_dir: Path = PROJECT_ROOT / "runtime"


def load_settings(path: Path | None = None) -> Settings:
    settings = Settings()
    config_path = path or PROJECT_ROOT / "config.toml"
    if not config_path.exists():
        return settings

    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    server = raw.get("server", {})
    dashboard = raw.get("dashboard", {})
    paths = raw.get("paths", {})

    updates: dict[str, object] = {}
    mapping = {
        "bind_host": server.get("bind_host"),
        "port": server.get("port"),
        "auth_token": server.get("auth_token"),
        "sample_interval_seconds": server.get("sample_interval_seconds"),
        "codex_interval_seconds": server.get("codex_interval_seconds"),
        "amd_sample_interval_seconds": server.get("amd_sample_interval_seconds"),
        "machine_name": dashboard.get("machine_name"),
        "dashboard_title": dashboard.get("title"),
        "cpu_name": dashboard.get("cpu_name"),
        "cpu_code": dashboard.get("cpu_code"),
        "gpu_name": dashboard.get("gpu_name"),
        "gpu_code": dashboard.get("gpu_code"),
        "status_label": dashboard.get("status_label"),
        "kindle_model": dashboard.get("kindle_model"),
        "refresh_label": dashboard.get("refresh_label"),
    }
    for key, value in mapping.items():
        if value is not None:
            updates[key] = value

    if paths.get("sensor_bridge"):
        updates["sensor_bridge"] = (PROJECT_ROOT / paths["sensor_bridge"]).resolve()
    if paths.get("codex_binary"):
        updates["codex_binary"] = (PROJECT_ROOT / paths["codex_binary"]).resolve()
    if paths.get("ryzen_master_cli"):
        configured_cli = Path(paths["ryzen_master_cli"])
        updates["ryzen_master_cli"] = (
            configured_cli if configured_cli.is_absolute() else (PROJECT_ROOT / configured_cli).resolve()
        )

    result = replace(settings, **updates)
    if not 1 <= int(result.port) <= 65535:
        raise ValueError("server.port must be between 1 and 65535")
    if result.bind_host != "127.0.0.1" and len(result.auth_token) < 24:
        raise ValueError("a token of at least 24 characters is required for network access")
    if float(result.sample_interval_seconds) < 1:
        raise ValueError("sample interval must be at least one second")
    if float(result.amd_sample_interval_seconds) < 5:
        raise ValueError("AMD sample interval must be at least five seconds")
    return result
