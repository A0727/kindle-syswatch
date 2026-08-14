from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil


@dataclass(frozen=True)
class Sensor:
    hardware_type: str
    hardware_name: str
    sensor_type: str
    sensor_name: str
    value: float
    sensor_id: str


@dataclass
class SensorSnapshot:
    timestamp: float = 0.0
    sensors: list[Sensor] = field(default_factory=list)
    cpu_percent: float = 0.0
    cpu_frequency_mhz: float | None = None
    memory_percent: float = 0.0
    memory_used_gib: float = 0.0
    memory_total_gib: float = 0.0
    disk_percent: float = 0.0
    disk_used_gib: float = 0.0
    disk_total_gib: float = 0.0
    network_up_bps: float = 0.0
    network_down_bps: float = 0.0
    uptime_seconds: float = 0.0
    error: str | None = None
    amd_error: str | None = None

    def find(
        self,
        hardware_type: str | tuple[str, ...],
        sensor_type: str,
        names: tuple[str, ...],
        *,
        positive: bool = False,
    ) -> float | None:
        hardware_types = (hardware_type,) if isinstance(hardware_type, str) else hardware_type
        lowered = tuple(item.lower() for item in names)
        for sensor in self.sensors:
            if sensor.hardware_type not in hardware_types or sensor.sensor_type != sensor_type:
                continue
            sensor_name = sensor.sensor_name.lower()
            if not any(name in sensor_name for name in lowered):
                continue
            if positive and sensor.value <= 0:
                continue
            return sensor.value
        return None


_NUMBER = r"([-+]?\d+(?:\.\d+)?)"


def parse_ryzen_master_output(output: str) -> list[Sensor]:
    """Convert the read-only Ryzen Master PM table into synthetic CPU sensors."""
    sensors: list[Sensor] = []

    temperature = re.search(
        rf"GetCurrentTemperature[^\r\n]*?{_NUMBER}\s+Celsius",
        output,
        re.IGNORECASE,
    )
    power = re.search(
        rf"^\s*PPT Current Value\s*:\s*{_NUMBER}\s+W",
        output,
        re.IGNORECASE | re.MULTILINE,
    )
    effective_clocks = [
        float(value)
        for value in re.findall(
            rf"GetEffectiveFrequency Core[^\r\n]*?{_NUMBER}\s+MHz",
            output,
            re.IGNORECASE,
        )
        if float(value) > 0
    ]
    current_clocks = [
        float(value)
        for value in re.findall(
            rf"GetCurrentFrequency Core[^\r\n]*?{_NUMBER}\s+MHz",
            output,
            re.IGNORECASE,
        )
        if float(value) > 0
    ]

    def add(sensor_type: str, sensor_name: str, value: float, sensor_id: str) -> None:
        sensors.append(
            Sensor(
                hardware_type="Cpu",
                hardware_name="AMD Ryzen Master SDK",
                sensor_type=sensor_type,
                sensor_name=sensor_name,
                value=value,
                sensor_id=sensor_id,
            )
        )

    if temperature:
        value = float(temperature.group(1))
        if 0 < value < 130:
            add("Temperature", "CPU Package (Ryzen Master)", value, "/amdrm/cpu/temperature")
    if power:
        value = float(power.group(1))
        if 0 < value < 1000:
            add("Power", "Package (Ryzen Master PPT)", value, "/amdrm/cpu/power")

    clocks = effective_clocks or current_clocks
    if clocks:
        value = sum(clocks) / len(clocks)
        if 100 < value < 10000:
            add("Clock", "Cores (Average Effective) (Ryzen Master)", value, "/amdrm/cpu/clock")

    return sensors


class RyzenMasterSampler:
    def __init__(self, cli: Path, interval: float) -> None:
        self.cli = cli
        self.interval = interval
        self._lock = threading.Lock()
        self._sensors: list[Sensor] = []
        self._error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.cli.exists() or (self._thread and self._thread.is_alive()):
            return
        self._thread = threading.Thread(target=self._run, name="ryzen-master-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self) -> tuple[list[Sensor], str | None]:
        with self._lock:
            return list(self._sensors), self._error

    def _run(self) -> None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        while not self._stop.is_set():
            try:
                result = subprocess.run(
                    [str(self.cli), "-a", "GetPMTableData"],
                    cwd=str(self.cli.parent),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(30.0, self.interval * 2),
                    creationflags=creation_flags,
                    check=False,
                )
                output = "\n".join(part for part in (result.stdout, result.stderr) if part)
                sensors = parse_ryzen_master_output(output)
                if not sensors:
                    detail = next((line.strip() for line in output.splitlines() if line.strip()), "no metrics returned")
                    raise RuntimeError(detail)
                with self._lock:
                    self._sensors = sensors
                    self._error = None
            except Exception as exception:
                with self._lock:
                    self._sensors = []
                    self._error = str(exception)
            self._stop.wait(self.interval)


class SensorSampler:
    def __init__(
        self,
        bridge: Path,
        interval: float = 2.0,
        ryzen_master_cli: Path | None = None,
        amd_interval: float = 10.0,
    ) -> None:
        self.bridge = bridge
        self.interval = interval
        self._lock = threading.Lock()
        self._snapshot = SensorSnapshot()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._previous_net = psutil.net_io_counters()
        self._previous_net_at = time.monotonic()
        self._ryzen_master = RyzenMasterSampler(ryzen_master_cli, amd_interval) if ryzen_master_cli else None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self._ryzen_master:
            self._ryzen_master.start()
        self._thread = threading.Thread(target=self._run, name="sensor-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._ryzen_master:
            self._ryzen_master.stop()

    def snapshot(self) -> SensorSnapshot:
        with self._lock:
            return self._snapshot

    def _system_metrics(self, sensors: list[Sensor], error: str | None = None) -> SensorSnapshot:
        now = time.time()
        memory = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage("C:\\")
        except OSError:
            disk = psutil.disk_usage("/")

        current_net = psutil.net_io_counters()
        current_net_at = time.monotonic()
        elapsed = max(0.001, current_net_at - self._previous_net_at)
        up = max(0.0, (current_net.bytes_sent - self._previous_net.bytes_sent) / elapsed)
        down = max(0.0, (current_net.bytes_recv - self._previous_net.bytes_recv) / elapsed)
        self._previous_net = current_net
        self._previous_net_at = current_net_at
        cpu_frequency = psutil.cpu_freq()

        amd_error: str | None = None
        if self._ryzen_master:
            amd_sensors, amd_error = self._ryzen_master.snapshot()
            sensors = [*sensors, *amd_sensors]

        return SensorSnapshot(
            timestamp=now,
            sensors=sensors,
            cpu_percent=psutil.cpu_percent(interval=None),
            cpu_frequency_mhz=cpu_frequency.current if cpu_frequency else None,
            memory_percent=memory.percent,
            memory_used_gib=memory.used / 2**30,
            memory_total_gib=memory.total / 2**30,
            disk_percent=disk.percent,
            disk_used_gib=disk.used / 2**30,
            disk_total_gib=disk.total / 2**30,
            network_up_bps=up,
            network_down_bps=down,
            uptime_seconds=max(0.0, now - psutil.boot_time()),
            error=error,
            amd_error=amd_error,
        )

    def _run(self) -> None:
        if not self.bridge.exists():
            with self._lock:
                self._snapshot = self._system_metrics([], f"Sensor bridge not found: {self.bridge}")
            return

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        while not self._stop.is_set():
            process: subprocess.Popen[str] | None = None
            try:
                process = subprocess.Popen(
                    [str(self.bridge), "--interval-ms", str(int(self.interval * 1000))],
                    cwd=str(self.bridge.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creation_flags,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    if self._stop.is_set():
                        break
                    try:
                        raw: dict[str, Any] = json.loads(line)
                        if not raw.get("ok"):
                            raise RuntimeError(raw.get("message", "sensor bridge error"))
                        sensors = [
                            Sensor(
                                hardware_type=item["hardware_type"],
                                hardware_name=item["hardware_name"],
                                sensor_type=item["sensor_type"],
                                sensor_name=item["sensor_name"],
                                value=float(item["value"]),
                                sensor_id=item["sensor_id"],
                            )
                            for item in raw.get("sensors", [])
                        ]
                        new_snapshot = self._system_metrics(sensors)
                    except Exception as exception:
                        new_snapshot = self._system_metrics([], str(exception))
                    with self._lock:
                        self._snapshot = new_snapshot
                if not self._stop.is_set():
                    raise RuntimeError("sensor bridge exited")
            except Exception as exception:
                with self._lock:
                    self._snapshot = self._system_metrics([], str(exception))
                self._stop.wait(3)
            finally:
                if process and process.poll() is None:
                    process.terminate()
