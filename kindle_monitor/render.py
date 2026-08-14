from __future__ import annotations

import io
import math
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .codex_usage import CodexUsage
from .config import Settings
from .sensors import SensorSnapshot


FONT_ROOT = Path("C:/Windows/Fonts")

# The reference is a paper-white panel with dense black technical ink.  The
# names describe their visual role in the original dark theme; values are
# intentionally inverted here so all existing primitives stay consistent.
BLACK = 255
GRID = 142
DIM = 72
WHITE = 18
BRIGHT = 0


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = ("consolab.ttf", "consola.ttf") if bold else ("consola.ttf", "lucon.ttf")
    for filename in candidates:
        path = FONT_ROOT / filename
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fmt_rate(bytes_per_second: float) -> str:
    value = max(0.0, bytes_per_second)
    for suffix in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1000 or suffix == "GB/s":
            if suffix == "B/s":
                return f"{value:0.0f} {suffix}"
            return f"{value:0.0f} {suffix}"
        value /= 1000
    return "0 B/s"


def _fmt_uptime(seconds: float) -> str:
    total_minutes = int(max(0, seconds) // 60)
    days, remaining = divmod(total_minutes, 1440)
    hours, minutes = divmod(remaining, 60)
    return f"{days}D:{hours:02d}H:{minutes:02d}M"


def _fmt_reset(timestamp: int | None) -> str:
    if not timestamp:
        return "--  --"
    remaining = max(0, timestamp - int(time.time()))
    hours = remaining // 3600
    if hours >= 24:
        return f"{hours // 24}D  {hours % 24:02d}H"
    minutes = (remaining % 3600) // 60
    return f"{hours:02d}H {minutes:02d}M"


@dataclass
class DashboardMetrics:
    cpu_load: float
    cpu_temp: float | None
    cpu_power: float | None
    cpu_clock: float | None
    gpu_load: float | None
    gpu_temp: float | None
    gpu_hotspot: float | None
    gpu_power: float | None
    gpu_memory_used: float | None
    gpu_memory_total: float | None


class DashboardRenderer:
    """Render the 1072x1448 monochrome tactical SYSWATCH dashboard."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # The sensor sampler runs every two seconds, so 61 points cover 120 seconds.
        self.cpu_history: deque[float] = deque([0.0] * 61, maxlen=61)
        self.gpu_history: deque[float] = deque([0.0] * 61, maxlen=61)

    @staticmethod
    def metrics(snapshot: SensorSnapshot) -> DashboardMetrics:
        cpu_load = snapshot.find("Cpu", "Load", ("cpu total",))
        if cpu_load is None:
            cpu_load = snapshot.cpu_percent
        cpu_clock = snapshot.find(
            "Cpu",
            "Clock",
            ("cores (average effective)", "windows average effective", "cores (average)"),
            positive=True,
        )
        if cpu_clock is None:
            cpu_clock = snapshot.cpu_frequency_mhz
        return DashboardMetrics(
            cpu_load=cpu_load,
            cpu_temp=snapshot.find("Cpu", "Temperature", ("tctl/tdie", "cpu package", "core"), positive=True),
            cpu_power=snapshot.find("Cpu", "Power", ("package",), positive=True),
            cpu_clock=cpu_clock,
            gpu_load=snapshot.find(("GpuNvidia", "GpuAmd", "GpuIntel"), "Load", ("gpu core",)),
            gpu_temp=snapshot.find(("GpuNvidia", "GpuAmd", "GpuIntel"), "Temperature", ("gpu core",), positive=True),
            gpu_hotspot=snapshot.find(
                ("GpuNvidia", "GpuAmd", "GpuIntel"),
                "Temperature",
                ("hot spot", "hotspot"),
                positive=True,
            ),
            gpu_power=snapshot.find(
                ("GpuNvidia", "GpuAmd", "GpuIntel"),
                "Power",
                ("gpu package", "package"),
                positive=True,
            ),
            gpu_memory_used=snapshot.find(
                ("GpuNvidia", "GpuAmd", "GpuIntel"),
                "SmallData",
                ("gpu memory used",),
            ),
            gpu_memory_total=snapshot.find(
                ("GpuNvidia", "GpuAmd", "GpuIntel"),
                "SmallData",
                ("gpu memory total",),
            ),
        )

    @staticmethod
    def _text(
        draw: ImageDraw.ImageDraw,
        xy: tuple[int, int],
        text: str,
        size: int,
        *,
        bold: bool = False,
        fill: int = WHITE,
        anchor: str | None = None,
        stroke: int = 0,
    ) -> None:
        draw.text(
            xy,
            text,
            font=_font(size, bold),
            fill=fill,
            anchor=anchor,
            stroke_width=stroke,
            stroke_fill=fill,
        )

    @staticmethod
    def _line(
        draw: ImageDraw.ImageDraw,
        points: tuple[int, ...] | list[tuple[int, int]],
        *,
        fill: int = WHITE,
        width: int = 4,
    ) -> None:
        draw.line(points, fill=fill, width=width)

    @staticmethod
    def _frame(
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        *,
        cut: int = 15,
        inner_bottom: bool = False,
    ) -> None:
        x1, y1, x2, y2 = box
        points = [
            (x1 + cut, y1),
            (x2 - cut, y1),
            (x2, y1 + cut),
            (x2, y2 - cut),
            (x2 - cut, y2),
            (x1 + cut, y2),
            (x1, y2 - cut),
            (x1, y1 + cut),
            (x1 + cut, y1),
        ]
        draw.line(points, fill=WHITE, width=5)
        if inner_bottom:
            draw.line(
                (
                    x1 + 9,
                    y2 - 16,
                    x1 + 20,
                    y2 - 6,
                    x2 - 20,
                    y2 - 6,
                    x2 - 9,
                    y2 - 16,
                ),
                fill=DIM,
                width=2,
            )

    @staticmethod
    def _value_with_unit(
        draw: ImageDraw.ImageDraw,
        xy: tuple[int, int],
        value: str,
        unit: str,
        *,
        value_size: int,
        unit_size: int,
    ) -> None:
        value_font = _font(value_size, True)
        draw.text(xy, value, font=value_font, fill=BRIGHT)
        value_width = int(draw.textlength(value, font=value_font))
        draw.text(
            (xy[0] + value_width + 5, xy[1] + value_size - unit_size - 3),
            unit,
            font=_font(unit_size, True),
            fill=WHITE,
        )

    @staticmethod
    def _slashes(draw: ImageDraw.ImageDraw, x: int, y: int, count: int = 3, *, fill: int = DIM) -> None:
        for index in range(count):
            left = x + index * 11
            draw.polygon(
                [(left, y + 12), (left + 7, y), (left + 13, y), (left + 6, y + 12)],
                fill=fill,
            )

    @staticmethod
    def _warning_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 22) -> None:
        """Draw a Kindle-safe monochrome warning triangle."""
        center_x = x + size // 2
        bottom = y + size
        draw.polygon(
            [(center_x, y), (x + size, bottom), (x, bottom)],
            fill=BRIGHT,
        )
        draw.line(
            (center_x, y + 5, center_x, y + size - 8),
            fill=BLACK,
            width=3,
        )
        draw.ellipse(
            (center_x - 2, y + size - 6, center_x + 2, y + size - 2),
            fill=BLACK,
        )

    @staticmethod
    def _dashed_line(
        draw: ImageDraw.ImageDraw,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        dash: int = 4,
        gap: int = 5,
        fill: int = GRID,
        width: int = 2,
    ) -> None:
        x1, y1 = start
        x2, y2 = end
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            return
        dx = (x2 - x1) / length
        dy = (y2 - y1) / length
        position = 0.0
        while position < length:
            segment_end = min(length, position + dash)
            draw.line(
                (
                    int(x1 + dx * position),
                    int(y1 + dy * position),
                    int(x1 + dx * segment_end),
                    int(y1 + dy * segment_end),
                ),
                fill=fill,
                width=width,
            )
            position += dash + gap

    @staticmethod
    def _segmented_bar(
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        percent: float,
        *,
        segments: int,
        gap: int = 5,
        outline: int = WHITE,
        active_fill: int = BRIGHT,
        outline_only: bool = False,
    ) -> None:
        x1, y1, x2, y2 = box
        percent = max(0.0, min(100.0, percent))
        total_width = x2 - x1
        segment_width = (total_width - gap * (segments - 1)) / segments
        active = int(round(percent * segments / 100.0))
        for index in range(segments):
            left = round(x1 + index * (segment_width + gap))
            right = round(left + segment_width)
            if index < active and not outline_only:
                draw.rectangle((left, y1, right, y2), fill=active_fill)
            else:
                draw.rectangle((left, y1, right, y2), outline=outline, width=4)

    def _header(self, draw: ImageDraw.ImageDraw, width: int, now: datetime) -> None:
        # Calibration bar and tiny registration marks from the reference panel.
        draw.rectangle((30, 24, 45, 114), fill=BRIGHT)

        self._text(draw, (67, 20), self.settings.dashboard_title, 48, bold=True, fill=BRIGHT)
        self._text(draw, (70, 85), "NODE/07  //  LOCAL TELEMETRY", 21, bold=True, fill=WHITE)

        # Decorative dotted uplink followed by the long reference rule.
        self._text(draw, (454, 91), ".... ....", 19, bold=True, fill=WHITE)
        draw.line((553, 104, 906, 104), fill=DIM, width=4)

        self._text(draw, (width - 24, 21), now.strftime("%Y.%m.%d"), 25, bold=True, fill=WHITE, anchor="ra")
        self._text(draw, (width - 24, 53), now.strftime("%H:%M"), 48, bold=True, fill=BRIGHT, anchor="ra")
        self._text(draw, (width - 24, 106), self.settings.machine_name, 21, bold=True, fill=WHITE, anchor="ra")

    def _card_header(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        title: str,
        device: str,
        code: str,
    ) -> None:
        x1, y1, x2, _ = box
        draw.line((x1 + 16, y1 + 67, x2 - 14, y1 + 67), fill=WHITE, width=4)
        self._text(draw, (x1 + 28, y1 + 17), title, 31, bold=True, fill=BRIGHT)
        self._text(draw, (x1 + 101, y1 + 22), "/", 23, bold=True, fill=WHITE)
        device_x = x1 + 135
        code_right = x2 - 24
        code_font = _font(22, True)
        code_width = int(draw.textlength(code, font=code_font))
        max_device_width = code_right - code_width - 16 - device_x
        device_size = 22
        while device_size > 16 and draw.textlength(device, font=_font(device_size, True)) > max_device_width:
            device_size -= 1
        self._text(draw, (device_x, y1 + 20), device, device_size, bold=True, fill=WHITE)
        self._text(draw, (code_right, y1 + 20), code, 22, bold=True, fill=WHITE, anchor="ra")

    def _chart(
        self,
        draw: ImageDraw.ImageDraw,
        history: deque[float],
        box: tuple[int, int, int, int],
    ) -> None:
        x1, y1, x2, y2 = box
        self._text(draw, (x1 - 38, y1 - 17), "100", 18, bold=True, fill=WHITE)
        self._text(draw, (x1 - 29, (y1 + y2) // 2 - 10), "50", 18, bold=True, fill=WHITE)
        self._text(draw, (x1 - 22, y2 - 15), "0", 18, bold=True, fill=WHITE)
        draw.rectangle(box, outline=WHITE, width=2)
        self._dashed_line(draw, (x1, (y1 + y2) // 2), (x2, (y1 + y2) // 2), fill=GRID)
        for index in range(1, 5):
            x = x1 + round((x2 - x1) * index / 5)
            self._dashed_line(draw, (x, y1), (x, y2), fill=GRID)

        points: list[tuple[int, int]] = []
        for index, value in enumerate(history):
            x = x1 + round(index * (x2 - x1) / max(1, len(history) - 1))
            y = y2 - round(max(0.0, min(100.0, value)) * (y2 - y1) / 100.0)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=BRIGHT, width=5, joint="curve")

    def _system_card(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        *,
        title: str,
        device: str,
        code: str,
        load: float | None,
        temp: float | None,
        telemetry: list[tuple[str, str]],
        history: deque[float],
    ) -> None:
        self._frame(draw, box)
        self._card_header(draw, box, title, device, code)
        x1, y1, x2, y2 = box
        value = max(0.0, load or 0.0)
        history.append(value)

        self._text(draw, (x1 + 29, y1 + 87), "CORE LOAD", 22, bold=True, fill=WHITE)
        load_size = 82 if value < 100 else 68
        self._value_with_unit(
            draw,
            (x1 + 32, y1 + 119),
            f"{value:0.1f}",
            "%",
            value_size=load_size,
            unit_size=39,
        )

        self._text(draw, (x1 + 309, y1 + 87), "TEMP", 22, bold=True, fill=WHITE)
        thermal = "--.-" if temp is None else f"{temp:0.1f}"
        self._value_with_unit(
            draw,
            (x1 + 323, y1 + 142),
            thermal,
            "°C",
            value_size=51,
            unit_size=27,
        )

        self._segmented_bar(
            draw,
            (x1 + 30, y1 + 236, x2 - 24, y1 + 261),
            value,
            segments=16,
            gap=5,
        )

        self._text(draw, (x1 + 30, y1 + 286), "120 SEC LOAD", 21, bold=True, fill=WHITE)
        self._chart(draw, history, (x1 + 65, y1 + 328, x2 - 28, y1 + 461))

        telemetry_y = y2 - 75
        inner_left = x1 + 29
        inner_right = x2 - 25
        count = len(telemetry)
        gap = 37
        cell_width = (inner_right - inner_left - gap * (count - 1)) // count
        for index, (label, sensor_value) in enumerate(telemetry):
            cell_x = inner_left + index * (cell_width + gap)
            draw.line((cell_x, telemetry_y, cell_x + cell_width, telemetry_y), fill=WHITE, width=4)
            self._text(draw, (cell_x, telemetry_y + 10), label, 20, bold=True, fill=WHITE)
            self._text(draw, (cell_x + cell_width, telemetry_y + 8), sensor_value, 24, bold=True, fill=BRIGHT, anchor="ra")
            if index < count - 1:
                divider_x = cell_x + cell_width + gap // 2
                draw.line((divider_x, telemetry_y + 12, divider_x, telemetry_y + 45), fill=DIM, width=4)

    def _resources(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        snapshot: SensorSnapshot,
    ) -> None:
        self._frame(draw, box)
        x1, y1, x2, y2 = box
        draw.line((x1 + 8, y1 + 57, x2 - 8, y1 + 57), fill=WHITE, width=4)
        self._text(draw, (x1 + 27, y1 + 17), "SYSTEM / RESOURCES", 28, bold=True, fill=BRIGHT)
        self._text(draw, (x2 - 28, y1 + 18), "MEM / IO / NET", 21, bold=True, fill=WHITE, anchor="ra")

        divider1 = x1 + 341
        divider2 = x1 + 727
        for divider in (divider1, divider2):
            self._dashed_line(draw, (divider, y1 + 72), (divider, y2 - 21), dash=2, gap=2, fill=DIM)

        # Memory column.
        self._text(draw, (x1 + 31, y1 + 81), "RAM USAGE", 22, bold=True, fill=WHITE)
        self._text(draw, (divider1 - 36, y1 + 78), f"{snapshot.memory_percent:0.0f}%", 47, bold=True, fill=BRIGHT, anchor="ra")
        self._segmented_bar(
            draw,
            (x1 + 31, y1 + 139, divider1 - 36, y1 + 161),
            snapshot.memory_percent,
            segments=11,
            gap=4,
        )
        self._text(
            draw,
            (x1 + 31, y1 + 190),
            f"{snapshot.memory_used_gib:0.1f} / {snapshot.memory_total_gib:0.1f} GiB",
            24,
            bold=True,
            fill=WHITE,
        )

        # Disk column.
        disk_left = divider1 + 30
        if snapshot.disk_percent >= 80:
            disk_label = "DISK / HIGH"
        else:
            disk_label = "SYSTEM DISK"
        self._text(draw, (disk_left, y1 + 81), disk_label, 21, bold=True, fill=WHITE)
        if snapshot.disk_percent >= 80:
            label_font = _font(21, True)
            label_width = int(draw.textlength(disk_label, font=label_font))
            # Consolas Bold 21 has an ink bottom 18 px below this text origin.
            # Align the 22 px warning triangle to that exact bottom edge.
            self._warning_icon(draw, disk_left + label_width + 10, y1 + 77)
        self._text(draw, (divider2 - 38, y1 + 78), f"{snapshot.disk_percent:0.0f}%", 47, bold=True, fill=BRIGHT, anchor="ra")
        self._segmented_bar(
            draw,
            (disk_left, y1 + 139, divider2 - 38, y1 + 161),
            snapshot.disk_percent,
            segments=11,
            gap=4,
        )
        self._text(
            draw,
            (disk_left, y1 + 190),
            f"{snapshot.disk_used_gib:0.0f} / {snapshot.disk_total_gib:0.0f} GiB",
            24,
            bold=True,
            fill=WHITE,
        )

        # Network column.
        net_left = divider2 + 30
        self._text(draw, (net_left, y1 + 81), "NETWORK", 22, bold=True, fill=WHITE)
        self._text(draw, (x2 - 28, y1 + 74), "LIVE", 34, bold=True, fill=BRIGHT, anchor="ra")
        self._text(draw, (net_left + 3, y1 + 132), "↓", 37, fill=BRIGHT)
        self._text(draw, (net_left + 51, y1 + 136), _fmt_rate(snapshot.network_down_bps), 26, bold=True, fill=WHITE)
        self._text(draw, (net_left + 3, y1 + 177), "↑", 37, fill=BRIGHT)
        self._text(draw, (net_left + 51, y1 + 181), _fmt_rate(snapshot.network_up_bps), 26, bold=True, fill=WHITE)

    def _codex(self, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], codex: CodexUsage) -> None:
        self._frame(draw, box)
        x1, y1, x2, y2 = box
        draw.line((x1 + 8, y1 + 53, x2 - 8, y1 + 53), fill=WHITE, width=4)
        self._text(draw, (x1 + 27, y1 + 11), "CODEX / WEEKLY BUDGET", 27, bold=True, fill=BRIGHT)
        self._text(draw, (x2 - 30, y1 + 11), "ACCOUNT", 22, bold=True, fill=WHITE, anchor="ra")

        if codex.available and codex.primary:
            remaining = codex.primary.remaining_percent
            plan = str(codex.plan_type or "PLUS").upper()
            reset = _fmt_reset(codex.primary.resets_at)
            self._text(draw, (x1 + 32, y1 + 63), "WEEK REMAINING", 22, bold=True, fill=WHITE)
            self._text(draw, ((x1 + x2) // 2, y1 + 63), f"PLAN / {plan}", 22, bold=True, fill=WHITE, anchor="ma")
            self._text(draw, (x2 - 30, y1 + 63), "RESET IN", 22, bold=True, fill=WHITE, anchor="ra")
            self._text(draw, (x1 + 32, y1 + 96), f"{remaining}%", 70, bold=True, fill=BRIGHT)
            reset_parts = reset.split()
            if len(reset_parts) == 2:
                reset_right = x2 - 31
                reset_font = _font(51, True)
                tail = reset_parts[1]
                tail_width = int(draw.textlength(tail, font=reset_font))
                # Keep the hour value fixed and leave half a monospace cell
                # between the two values. Compared with the previous two-space
                # string this moves the day value right by about 1.5 letters.
                self._text(draw, (reset_right, y1 + 106), tail, 51, bold=True, fill=BRIGHT, anchor="ra")
                self._text(
                    draw,
                    (reset_right - tail_width - 15, y1 + 106),
                    reset_parts[0],
                    51,
                    bold=True,
                    fill=BRIGHT,
                    anchor="ra",
                )
            else:
                self._text(draw, (x2 - 31, y1 + 106), reset, 51, bold=True, fill=BRIGHT, anchor="ra")
            self._segmented_bar(
                draw,
                (x1 + 33, y1 + 168, x2 - 31, y1 + 192),
                remaining,
                segments=17,
                gap=5,
                outline_only=False,
            )
            self._text(draw, (x1 + 32, y1 + 199), "0", 20, bold=True, fill=WHITE)
            self._text(draw, ((x1 + x2) // 2, y1 + 199), "WEEKLY ALLOCATION", 22, bold=True, fill=WHITE, anchor="ma")
            self._text(draw, (x2 - 32, y1 + 199), "100", 20, bold=True, fill=WHITE, anchor="ra")
        else:
            self._text(draw, (x1 + 32, y1 + 63), "WEEK REMAINING", 22, bold=True, fill=WHITE)
            self._text(draw, (x1 + 32, y1 + 111), "OFFLINE", 58, bold=True, fill=BRIGHT)
            self._text(draw, (x2 - 32, y1 + 126), (codex.error or "ACCOUNT FEED UNAVAILABLE")[:45].upper(), 17, fill=DIM, anchor="ra")

    def _sensor_icon(self, draw: ImageDraw.ImageDraw, center: tuple[int, int]) -> None:
        x, y = center
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), outline=WHITE, width=4)
        draw.line((x - 10, y, x - 2, y + 8, x + 12, y - 9), fill=BRIGHT, width=5)

    def _clock_icon(self, draw: ImageDraw.ImageDraw, center: tuple[int, int]) -> None:
        x, y = center
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), outline=WHITE, width=4)
        draw.line((x, y, x, y - 13), fill=BRIGHT, width=4)
        draw.line((x, y, x + 11, y + 7), fill=BRIGHT, width=4)

    def _database_icon(self, draw: ImageDraw.ImageDraw, center: tuple[int, int]) -> None:
        x, y = center
        draw.ellipse((x - 15, y - 17, x + 15, y - 6), outline=WHITE, width=4)
        draw.line((x - 15, y - 12, x - 15, y + 14), fill=WHITE, width=4)
        draw.line((x + 15, y - 12, x + 15, y + 14), fill=WHITE, width=4)
        draw.arc((x - 15, y + 3, x + 15, y + 14), 0, 180, fill=WHITE, width=4)
        draw.arc((x - 15, y - 4, x + 15, y + 7), 0, 180, fill=DIM, width=2)

    def _status(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        snapshot: SensorSnapshot,
        metrics: DashboardMetrics,
    ) -> None:
        x1, y1, x2, y2 = box
        divider = x1 + 258
        left_panel = [
            (x1 + 15, y1),
            (divider, y1),
            (divider, y2),
            (x1 + 15, y2),
            (x1, y2 - 15),
            (x1, y1 + 15),
        ]
        draw.polygon(left_panel, fill=BRIGHT)
        self._frame(draw, box, inner_bottom=False)
        draw.line((divider, y1 + 6, divider, y2 - 6), fill=WHITE, width=4)

        self._text(draw, (x1 + 29, y1 + 14), "SYSWATCH", 21, bold=True, fill=BLACK)
        self._text(draw, (x1 + 29, y1 + 52), "ACTIVE", 43, bold=True, fill=BLACK)
        self._segmented_bar(
            draw,
            (x1 + 29, y1 + 99, x1 + 174, y1 + 108),
            60,
            segments=10,
            gap=4,
            outline=BLACK,
            active_fill=BLACK,
        )
        self._text(draw, (x1 + 29, y1 + 119), self.settings.status_label, 22, bold=True, fill=BLACK)

        top_y = y1 + 49
        sensor_online = metrics.cpu_temp is not None and metrics.cpu_power is not None and not snapshot.error
        self._sensor_icon(draw, (divider + 59, top_y))
        self._text(draw, (divider + 100, y1 + 21), "SENSOR BUS", 21, bold=True, fill=WHITE)
        self._text(draw, (divider + 100, y1 + 51), "ONLINE" if sensor_online else "DEGRADED", 21, bold=True, fill=WHITE)

        separator1 = divider + 259
        self._dashed_line(draw, (separator1, y1 + 25), (separator1, y1 + 76), dash=2, gap=4, fill=DIM)
        self._clock_icon(draw, (separator1 + 53, top_y))
        self._text(draw, (separator1 + 90, y1 + 22), "UPTIME", 21, bold=True, fill=WHITE)
        self._text(draw, (separator1 + 90, y1 + 52), _fmt_uptime(snapshot.uptime_seconds), 21, bold=True, fill=WHITE)

        separator2 = divider + 514
        self._dashed_line(draw, (separator2, y1 + 25), (separator2, y1 + 76), dash=2, gap=4, fill=DIM)
        self._database_icon(draw, (separator2 + 63, top_y))
        self._text(draw, (separator2 + 99, y1 + 22), "DATA LINK", 21, bold=True, fill=WHITE)
        self._text(draw, (separator2 + 99, y1 + 52), "READY", 21, bold=True, fill=WHITE)

        self._dashed_line(draw, (divider + 31, y1 + 98), (x2 - 23, y1 + 98), dash=2, gap=3, fill=DIM)
        self._text(draw, (divider + 40, y1 + 119), self.settings.refresh_label, 22, bold=True, fill=WHITE)
        self._text(draw, (x2 - 24, y1 + 120), self.settings.kindle_model, 20, bold=True, fill=WHITE, anchor="ra")

    def render(self, snapshot: SensorSnapshot, codex: CodexUsage) -> tuple[bytes, Image.Image]:
        metrics = self.metrics(snapshot)
        image = Image.new("L", (self.settings.screen_width, self.settings.screen_height), BLACK)
        draw = ImageDraw.Draw(image)
        width = self.settings.screen_width
        height = self.settings.screen_height
        now = datetime.now()

        self._frame(draw, (0, 0, width - 1, height - 1), cut=14, inner_bottom=False)
        self._header(draw, width, now)

        margin = 21
        gap = 20
        card_width = (width - margin * 2 - gap) // 2
        cpu_box = (margin, 142, margin + card_width, 709)
        gpu_box = (margin + card_width + gap, 142, width - margin, 709)

        cpu_telemetry = [
            ("PWR", "--W" if metrics.cpu_power is None else f"{metrics.cpu_power:0.0f}W"),
            ("CLOCK", "--.--GHz" if metrics.cpu_clock is None else f"{metrics.cpu_clock / 1000:0.2f}GHz"),
        ]
        self._system_card(
            draw,
            cpu_box,
            title="CPU",
            device=self.settings.cpu_name,
            code=self.settings.cpu_code,
            load=metrics.cpu_load,
            temp=metrics.cpu_temp,
            telemetry=cpu_telemetry,
            history=self.cpu_history,
        )

        vram = "--.-G"
        if metrics.gpu_memory_used is not None:
            vram = f"{metrics.gpu_memory_used / 1024:0.1f}G"
        gpu_telemetry = [
            ("HOT", "--°C" if metrics.gpu_hotspot is None else f"{metrics.gpu_hotspot:0.0f}°C"),
            ("PWR", "--W" if metrics.gpu_power is None else f"{metrics.gpu_power:0.0f}W"),
            ("VRAM", vram),
        ]
        self._system_card(
            draw,
            gpu_box,
            title="GPU",
            device=self.settings.gpu_name,
            code=self.settings.gpu_code,
            load=metrics.gpu_load,
            temp=metrics.gpu_temp,
            telemetry=gpu_telemetry,
            history=self.gpu_history,
        )

        self._resources(draw, (margin, 734, width - margin, 987), snapshot)
        self._codex(draw, (margin, 1009, width - margin, 1251), codex)
        self._status(draw, (margin, 1270, width - margin, 1427), snapshot, metrics)

        output = io.BytesIO()
        image.save(output, format="PNG", optimize=False, compress_level=6)
        return output.getvalue(), image
