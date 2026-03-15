"""
GutSeq – primitive reusable widgets.

All custom-painted widgets live here.  They have zero knowledge of the
application domain; they accept plain Python lists/dicts and paint them.
"""

from __future__ import annotations
import math
from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QSizePolicy
from PyQt6.QtCore    import Qt, QRect, QRectF, QPointF
from PyQt6.QtGui     import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QFont, QPainterPath,
)
from resources.styles import GENUS_COLORS, BORDER, TEXT_M, TEXT_HINT, BG_CARD


# ── Helpers ───────────────────────────────────────────────────────────────────

def _color(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


# ── Vertical bar chart ────────────────────────────────────────────────────────

class BarChartWidget(QWidget):
    """
    Vertical bar chart.
    data: list of (label, value) tuples.
    """

    def __init__(self, data: list[tuple[str, float]],
                 colors: list[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data   = data
        self._colors = colors or GENUS_COLORS
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H     = self.width(), self.height()
        pad_b    = 24   # bottom label space
        pad_t    = 8
        chart_h  = H - pad_b - pad_t
        max_val  = max(v for _, v in self._data) or 1.0
        n        = len(self._data)
        gap      = 4
        bar_w    = max(6, (W - gap * (n + 1)) // n)

        font = QFont(); font.setPointSize(8)
        p.setFont(font)

        for i, (label, value) in enumerate(self._data):
            bar_h  = int(chart_h * value / max_val)
            x      = gap + i * (bar_w + gap)
            y      = pad_t + (chart_h - bar_h)
            color  = _color(self._colors[i % len(self._colors)])

            # Bar
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bar_w, bar_h), 3, 3)
            p.fillPath(path, color)

        # X-axis labels: only first and last
        p.setPen(_color(TEXT_M))
        if self._data:
            p.drawText(gap, H - pad_b + 4, W // 3, pad_b,
                       Qt.AlignmentFlag.AlignLeft, self._data[0][0])
            p.drawText(W - W // 3 - gap, H - pad_b + 4, W // 3, pad_b,
                       Qt.AlignmentFlag.AlignRight, self._data[-1][0])
        p.end()


# ── Horizontal stacked bar chart ──────────────────────────────────────────────

class StackedBarWidget(QWidget):
    """
    Horizontal stacked bar per run.
    data: dict  run_label → list of (genus, value)
    """

    ROW_H   = 14
    ROW_GAP = 20   # includes label above

    def __init__(self, data: dict[str, list[tuple[str, float]]],
                 colors: list[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data   = data
        self._colors = colors or GENUS_COLORS
        self._recalc_height()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, data: dict[str, list[tuple[str, float]]]) -> None:
        self._data = data
        self._recalc_height()
        self.update()

    def _recalc_height(self) -> None:
        h = len(self._data) * self.ROW_GAP + 8
        self.setFixedHeight(max(h, 20))

    def paintEvent(self, _):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = self.width()
        font = QFont(); font.setPointSize(8)
        p.setFont(font)

        y = 0
        for run_label, segments in self._data.items():
            # Run label
            p.setPen(_color(TEXT_M))
            p.drawText(0, y, 24, 14, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       run_label)

            total = sum(v for _, v in segments) or 1.0
            x = 28
            avail = W - 28
            bar_y = y + 1

            for j, (_, value) in enumerate(segments):
                seg_w = max(int(avail * value / total), 0)
                color = _color(self._colors[j % len(self._colors)])
                p.setBrush(QBrush(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(x, bar_y, seg_w, self.ROW_H)
                x += seg_w

            y += self.ROW_GAP
        p.end()


# ── Boxplot ───────────────────────────────────────────────────────────────────

class BoxPlotWidget(QWidget):
    """
    Side-by-side box plots.
    data: dict  run_label → (min, q1, median, q3, max)
    colors: list of hex strings, one per run
    """

    def __init__(self, data: dict[str, tuple],
                 colors: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data   = data
        self._colors = colors
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: dict[str, tuple]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H    = self.width(), self.height()
        pad_b   = 20   # label space
        pad_t   = 8
        chart_h = H - pad_b - pad_t

        runs    = list(self._data.keys())
        n       = len(runs)
        slot_w  = W // n
        box_w   = max(20, slot_w // 2)

        # Global value range
        all_vals = [v for tup in self._data.values() for v in tup]
        lo, hi   = min(all_vals), max(all_vals)
        span     = hi - lo or 1.0

        def vy(val: float) -> int:
            """Map a data value to a y pixel (top = high)."""
            return pad_t + int(chart_h * (1 - (val - lo) / span))

        font = QFont(); font.setPointSize(8)
        p.setFont(font)

        for i, run in enumerate(runs):
            mn, q1, med, q3, mx = self._data[run]
            cx = slot_w * i + slot_w // 2
            bx = cx - box_w // 2
            color = _color(self._colors[i % len(self._colors)])
            light = _color(self._colors[i % len(self._colors)], 60)

            # Whiskers
            p.setPen(QPen(_color("#9CA3AF"), 1))
            p.drawLine(cx, vy(mn), cx, vy(q1))
            p.drawLine(cx, vy(q3), cx, vy(mx))
            # Whisker caps
            cap = box_w // 3
            p.drawLine(cx - cap, vy(mn), cx + cap, vy(mn))
            p.drawLine(cx - cap, vy(mx), cx + cap, vy(mx))

            # Box (IQR)
            p.setBrush(QBrush(light))
            p.setPen(QPen(color, 1))
            p.drawRect(bx, vy(q3), box_w, vy(q1) - vy(q3))

            # Median line
            p.setPen(QPen(color, 2))
            p.drawLine(bx, vy(med), bx + box_w, vy(med))

            # Run label
            p.setPen(_color(TEXT_M))
            p.setFont(font)
            p.drawText(cx - 16, H - pad_b + 4, 32, 16,
                       Qt.AlignmentFlag.AlignCenter, run)

        p.end()


# ── PCoA scatter plot ─────────────────────────────────────────────────────────

class PCoAWidget(QWidget):
    """
    Simple 2D scatter plot for PCoA coordinates.
    coords: dict  run_label → (pc1, pc2)
    groups: list of lists of run labels (each group gets same cluster ellipse)
    """

    def __init__(self, coords: dict[str, tuple[float, float]],
                 colors: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._coords = coords
        self._colors = colors   # run_label → hex color
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, coords: dict[str, tuple[float, float]]) -> None:
        self._coords = coords
        self.update()

    def paintEvent(self, _):
        if not self._coords:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H    = self.width(), self.height()
        pad     = 30
        chart_w = W - pad * 2
        chart_h = H - pad * 2

        xs = [v[0] for v in self._coords.values()]
        ys = [v[1] for v in self._coords.values()]
        x_lo, x_hi = min(xs) - 0.1, max(xs) + 0.1
        y_lo, y_hi = min(ys) - 0.1, max(ys) + 0.1
        x_span = x_hi - x_lo or 1.0
        y_span = y_hi - y_lo or 1.0

        def px(v: float) -> int:
            return pad + int(chart_w * (v - x_lo) / x_span)

        def py(v: float) -> int:
            return pad + int(chart_h * (1 - (v - y_lo) / y_span))

        # Axes
        p.setPen(QPen(_color(BORDER), 1))
        cx = px(0.0); cy = py(0.0)
        p.drawLine(pad, cy, W - pad, cy)
        p.drawLine(cx, pad, cx, H - pad)

        font = QFont(); font.setPointSize(8)
        p.setFont(font)
        p.setPen(_color(TEXT_HINT))
        p.drawText(2, cy - 8, "PC2")
        p.drawText(W - pad - 4, cy + 12, "PC1")

        # Cluster ellipses: group R1+R2 and R3+R4
        groups = [
            [r for r in ["R1", "R2"] if r in self._coords],
            [r for r in ["R3", "R4"] if r in self._coords],
        ]
        group_colors = ["#10B981", "#F59E0B"]

        for grp, gcol in zip(groups, group_colors):
            if len(grp) < 2:
                continue
            gxs = [px(self._coords[r][0]) for r in grp]
            gys = [py(self._coords[r][1]) for r in grp]
            cx_e = sum(gxs) // len(gxs)
            cy_e = sum(gys) // len(gys)
            rx   = max(abs(gx - cx_e) for gx in gxs) + 18
            ry   = max(abs(gy - cy_e) for gy in gys) + 18
            ec   = _color(gcol, 40)
            p.setBrush(QBrush(ec))
            p.setPen(QPen(_color(gcol, 180), 1))
            p.drawEllipse(QPointF(cx_e, cy_e), rx, ry)

        # Dots + labels
        dot_r = 6
        for run, (vx, vy_) in self._coords.items():
            screen_x = px(vx)
            screen_y = py(vy_)
            col = _color(self._colors.get(run, "#6366F1"))
            p.setBrush(QBrush(col))
            p.setPen(QPen(_color("#FFFFFF"), 1.5))
            p.drawEllipse(QPointF(screen_x, screen_y), dot_r, dot_r)

            p.setPen(_color("#374151"))
            p.setFont(font)
            p.drawText(screen_x + dot_r + 2, screen_y + 4, run)

        p.end()


# ── Heatmap ───────────────────────────────────────────────────────────────────

class HeatmapWidget(QWidget):
    """
    Square dissimilarity heatmap.
    labels: list of run labels
    values: 2-D list (0.0 = identical → 1.0 = totally different)
    """

    CELL = 30

    def __init__(self, labels: list[str], values: list[list[float]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels = labels
        self._values = values
        n = len(labels)
        side = n * self.CELL + 28
        self.setFixedSize(side, side)

    def set_data(self, labels: list[str], values: list[list[float]]) -> None:
        self._labels = labels
        self._values = values
        n = len(labels)
        side = n * self.CELL + 28
        self.setFixedSize(side, side)
        self.update()

    def paintEvent(self, _):
        if not self._labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        n      = len(self._labels)
        offset = 24

        font = QFont(); font.setPointSize(8)
        p.setFont(font)

        # Axis labels
        p.setPen(_color(TEXT_M))
        for i, lbl in enumerate(self._labels):
            x = offset + i * self.CELL + self.CELL // 2
            p.drawText(x - 12, 0, 24, offset - 2,
                       Qt.AlignmentFlag.AlignCenter, lbl)
            p.drawText(0, offset + i * self.CELL, offset - 2, self.CELL,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)

        # Cells: dark teal = similar (low), light = dissimilar (high)
        for row in range(n):
            for col in range(n):
                val = self._values[row][col] if (
                    row < len(self._values) and col < len(self._values[row])
                ) else 0.0
                # Teal gradient: 0→dark, 1→light
                r_ = int(8   + (236 - 8)   * val)
                g_ = int(128 + (252 - 128) * val)
                b_ = int(128 + (232 - 128) * val)
                color = QColor(r_, g_, b_)

                cx = offset + col * self.CELL
                cy = offset + row * self.CELL
                p.setBrush(QBrush(color))
                p.setPen(QPen(_color("#FFFFFF"), 2))
                p.drawRect(cx, cy, self.CELL - 1, self.CELL - 1)
        p.end()


# ── Risk meter ────────────────────────────────────────────────────────────────

class RiskMeterWidget(QWidget):
    """
    Horizontal green-amber-red gradient bar with a circular marker.
    """

    def __init__(self, risk_pct: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pct = max(0.0, min(risk_pct, 100.0))
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_pct(self, pct: float) -> None:
        self._pct = max(0.0, min(pct, 100.0))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H   = self.width(), self.height()
        bar_y  = 7
        bar_h  = 10
        r_dot  = 8

        # Gradient bar
        grad = QLinearGradient(0, bar_y, W, bar_y)
        grad.setColorAt(0.0,  QColor("#10B981"))
        grad.setColorAt(0.5,  QColor("#F59E0B"))
        grad.setColorAt(1.0,  QColor("#EF4444"))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, bar_y, W, bar_h), 5, 5)
        p.fillPath(path, QBrush(grad))

        # Marker
        mx = int(W * self._pct / 100)
        my = bar_y + bar_h // 2
        p.setBrush(QBrush(QColor("#DC2626")))
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.drawEllipse(QPointF(mx, my), r_dot // 2 + 1, r_dot // 2 + 1)
        p.end()