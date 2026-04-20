"""
Axis – primitive reusable widgets.

All custom-painted widgets live here.  They have zero knowledge of the
application domain; they accept plain Python lists/dicts and paint them.
"""

from __future__ import annotations
import math
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout,
                             QSizePolicy, QTableWidgetItem, QTableWidget,
                             QHeaderView)
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


def _build_genus_palette(n: int, base_colors: list[str]) -> list[str]:

    if n <= len(base_colors):
        return base_colors[:n]

    palette = list(base_colors)
    needed  = n - len(base_colors)

    hue_step = 360 / (needed + 1)
    hue_start = 37.0
    for i in range(needed):
        hue = int((hue_start + hue_step * i) % 360)
        c   = QColor.fromHsl(hue, 155, 110)
        palette.append(c.name())

    return palette


class NumericSortItem(QTableWidgetItem):
    '''
    QTableWidgetItem w/ float sort key instead of str
    '''
    def __init__(self, value: float, fmt: str = ",") -> None:
        display = format(int(value), ",") if fmt == "," else format(value, fmt)
        super().__init__(display)
        self._numeric = float(value)
        self.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, NumericSortItem):
            return self._numeric < other._numeric
        return super().__lt__(other)


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


class _AlphaBarWidget(BarChartWidget):
    """
    BarChartWidget that additionally paints the numeric scalar value above
    each bar.  Alpha diversity values (Shannon ~2–4 bits, Simpson 0–1) are
    meaningful absolute numbers, not just relative heights.
    """

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._data:
            return

        from PyQt6.QtGui import QPainter, QFont, QColor
        from PyQt6.QtCore import Qt as _Qt

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H    = self.width(), self.height()
        pad_b   = 24
        pad_t   = 8
        chart_h = H - pad_b - pad_t
        max_val = max(v for _, v in self._data) or 1.0
        n       = len(self._data)
        gap     = 4
        bar_w   = max(6, (W - gap * (n + 1)) // n)

        font = QFont()
        font.setPointSize(7)
        p.setFont(font)

        from resources.styles import TEXT_M
        p.setPen(QColor(TEXT_M))

        for i, (_, value) in enumerate(self._data):
            bar_h = int(chart_h * value / max_val)
            x     = gap + i * (bar_w + gap)
            y     = pad_t + (chart_h - bar_h)
            p.drawText(
                x, y - 14, bar_w, 13,
                _Qt.AlignmentFlag.AlignCenter,
                f"{value:.3f}",
            )
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

        # Rebuild genus→color map whenever data changes
        all_keys = list(dict.fromkeys(
            g for segs in data.values() for g, _ in segs
        ))
        pal = _build_genus_palette(len(all_keys), self._colors)
        self._genus_color_map: dict[str, str] = {
            g: pal[i] for i, g in enumerate(all_keys)
        }

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

        W, H     = self.width(), self.height()
        pad_l    = 46   # y-axis label space
        pad_b    = 24
        pad_t    = 12
        pad_r    = 12
        chart_w  = W - pad_l - pad_r
        chart_h  = H - pad_b - pad_t

        runs     = list(self._data.keys())
        n        = len(runs)
        slot_w   = chart_w // max(n, 1)
        box_w    = max(18, slot_w * 2 // 5)

        all_vals = [v for tup in self._data.values() for v in tup]
        lo, hi   = min(all_vals), max(all_vals)
        span     = hi - lo or 1.0
        # Pad the range slightly
        lo -= span * 0.05
        hi += span * 0.05
        span = hi - lo

        def vy(val: float) -> int:
            return pad_t + int(chart_h * (1 - (val - lo) / span))

        font_sm = QFont(); font_sm.setPointSize(7)
        font_md = QFont(); font_md.setPointSize(8)

        # ── Horizontal grid lines + y-axis ticks ──────────────────────────
        n_ticks = 4
        for k in range(n_ticks + 1):
            tick_val = lo + span * k / n_ticks
            ty = vy(tick_val)
            p.setPen(QPen(_color("#E5E7EB"), 1, Qt.PenStyle.DotLine))
            p.drawLine(pad_l, ty, W - pad_r, ty)
            p.setPen(_color("#9CA3AF"))
            p.setFont(font_sm)
            p.drawText(0, ty - 7, pad_l - 4, 14,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{tick_val:.2f}")

        # ── Boxes ──────────────────────────────────────────────────────────
        for i, run in enumerate(runs):
            mn, q1, med, q3, mx = self._data[run]
            cx   = pad_l + slot_w * i + slot_w // 2
            bx   = cx - box_w // 2
            col  = _color(self._colors[i % len(self._colors)])
            fill = _color(self._colors[i % len(self._colors)], 55)

            # Whisker line
            p.setPen(QPen(_color("#9CA3AF"), 1.5))
            p.drawLine(cx, vy(mn), cx, vy(q1))
            p.drawLine(cx, vy(q3), cx, vy(mx))
            # Whisker caps
            cap = box_w // 3
            p.setPen(QPen(_color("#9CA3AF"), 1.5))
            p.drawLine(cx - cap, vy(mn), cx + cap, vy(mn))
            p.drawLine(cx - cap, vy(mx), cx + cap, vy(mx))

            # IQR box
            box_top = vy(q3); box_bot = vy(q1)
            p.setBrush(QBrush(fill))
            p.setPen(QPen(col, 1.5))
            p.drawRoundedRect(bx, box_top, box_w, box_bot - box_top, 3, 3)

            # Median line
            p.setPen(QPen(col, 2.5))
            p.drawLine(bx, vy(med), bx + box_w, vy(med))

            # Median value annotation
            p.setPen(col)
            p.setFont(font_sm)
            p.drawText(cx - 20, vy(med) - 14, 40, 12,
                       Qt.AlignmentFlag.AlignCenter, f"{med:.3f}")

            # Run label
            p.setPen(_color(TEXT_M))
            p.setFont(font_md)
            p.drawText(cx - 20, H - pad_b + 4, 40, 16,
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

        W, H     = self.width(), self.height()
        pad_l    = 48
        pad_r    = 16
        pad_t    = 16
        pad_b    = 36
        chart_w  = W - pad_l - pad_r
        chart_h  = H - pad_t - pad_b

        xs = [v[0] for v in self._coords.values()]
        ys = [v[1] for v in self._coords.values()]
        margin = max((max(xs) - min(xs)) * 0.2, 0.05)
        x_lo = min(xs) - margin;  x_hi = max(xs) + margin
        y_lo = min(ys) - margin;  y_hi = max(ys) + margin
        x_span = x_hi - x_lo or 1.0
        y_span = y_hi - y_lo or 1.0

        def sx(v: float) -> int:
            return pad_l + int(chart_w * (v - x_lo) / x_span)

        def sy(v: float) -> int:
            return pad_t + int(chart_h * (1 - (v - y_lo) / y_span))

        font_sm = QFont(); font_sm.setPointSize(7)
        font_md = QFont(); font_md.setPointSize(8)

        # ── Plot border ───────────────────────────────────────────────────
        p.setPen(QPen(_color(BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(pad_l, pad_t, chart_w, chart_h)

        # ── Grid lines ────────────────────────────────────────────────────
        n_grid = 4
        p.setPen(QPen(_color("#E5E7EB"), 1, Qt.PenStyle.DotLine))
        for k in range(1, n_grid):
            gx = pad_l + chart_w * k // n_grid
            gy = pad_t + chart_h * k // n_grid
            p.drawLine(gx, pad_t, gx, pad_t + chart_h)
            p.drawLine(pad_l, gy, pad_l + chart_w, gy)

        # ── Zero axes (bold) ──────────────────────────────────────────────
        p.setPen(QPen(_color("#9CA3AF"), 1))
        zero_x = sx(0.0); zero_y = sy(0.0)
        if pad_l <= zero_x <= pad_l + chart_w:
            p.drawLine(zero_x, pad_t, zero_x, pad_t + chart_h)
        if pad_t <= zero_y <= pad_t + chart_h:
            p.drawLine(pad_l, zero_y, pad_l + chart_w, zero_y)

        # ── Axis tick labels ──────────────────────────────────────────────
        p.setFont(font_sm)
        p.setPen(_color("#9CA3AF"))
        for k in range(n_grid + 1):
            xv = x_lo + x_span * k / n_grid
            gx = pad_l + chart_w * k // n_grid
            p.drawText(gx - 18, pad_t + chart_h + 4, 36, 14,
                       Qt.AlignmentFlag.AlignCenter, f"{xv:.2f}")
        for k in range(n_grid + 1):
            yv = y_lo + y_span * k / n_grid
            gy = pad_t + chart_h - chart_h * k // n_grid
            p.drawText(0, gy - 7, pad_l - 4, 14,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{yv:.2f}")

        # ── Axis titles ───────────────────────────────────────────────────
        p.setFont(font_md)
        p.setPen(_color(TEXT_M))
        p.drawText(pad_l, H - 16, chart_w, 14,
                   Qt.AlignmentFlag.AlignCenter, "PC1 (Axis 1)")
        # Rotated "PC2" on left
        p.save()
        p.translate(10, pad_t + chart_h // 2)
        p.rotate(-90)
        p.drawText(-30, -5, 60, 14, Qt.AlignmentFlag.AlignCenter, "PC2")
        p.restore()

        # ── Cluster ellipses (one per pair of runs) ───────────────────────
        all_runs = list(self._coords.keys())
        half     = max(len(all_runs) // 2, 1)
        groups   = [all_runs[:half], all_runs[half:]]
        g_cols   = ["#6366F1", "#10B981"]

        for grp, gcol in zip(groups, g_cols):
            if len(grp) < 2:
                continue
            gxs = [sx(self._coords[r][0]) for r in grp]
            gys = [sy(self._coords[r][1]) for r in grp]
            cxe = sum(gxs) // len(gxs)
            cye = sum(gys) // len(gys)
            rx  = max(abs(gx - cxe) for gx in gxs) + 20
            ry  = max(abs(gy - cye) for gy in gys) + 20
            p.setBrush(QBrush(_color(gcol, 28)))
            p.setPen(QPen(_color(gcol, 160), 1.5, Qt.PenStyle.DashLine))
            p.drawEllipse(QPointF(cxe, cye), float(rx), float(ry))

        # ── Points ────────────────────────────────────────────────────────
        dot_r = 7.0
        for run, (vx, vy_val) in self._coords.items():
            screen_x = sx(vx)
            screen_y = sy(vy_val)
            col      = _color(self._colors.get(run, "#6366F1"))
            # Shadow
            p.setBrush(QBrush(_color("#000000", 20)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(screen_x + 1.5, screen_y + 1.5), dot_r, dot_r)
            # Fill
            p.setBrush(QBrush(col))
            p.setPen(QPen(_color("#FFFFFF"), 2))
            p.drawEllipse(QPointF(screen_x, screen_y), dot_r, dot_r)
            # Label
            p.setPen(_color("#1F2937"))
            p.setFont(font_md)
            p.drawText(screen_x + int(dot_r) + 3, screen_y - 6, 32, 14,
                       Qt.AlignmentFlag.AlignLeft, run)

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
        self._resize()

    def _resize(self) -> None:
        n = len(self._labels)
        w = n * self.CELL + 28
        h = n * self.CELL + 28 + 28   # extra 28 for legend
        self.setFixedSize(max(w, 60), max(h, 60))

    def set_data(self, labels: list[str], values: list[list[float]]) -> None:
        self._labels = labels
        self._values = values
        self._resize()
        self.update()

    @staticmethod
    def _val_to_color(val: float, diagonal: bool = False) -> QColor:
        """
        White → amber → crimson color scale for dissimilarity values.
          0.0  =  white       (identical — diagonal)
          0.5  =  amber
          1.0  =  deep red
        """
        if diagonal:
            return QColor("#E0E7FF")   # light indigo for self-comparisons
        v = max(0.0, min(val, 1.0))
        if v <= 0.5:
            t  = v * 2.0
            r_ = 255
            g_ = int(255 - 85 * t)     # 255 → 170
            b_ = int(255 - 210 * t)    # 255 → 45
        else:
            t  = (v - 0.5) * 2.0
            r_ = int(255 - 75 * t)     # 255 → 180
            g_ = int(170 - 150 * t)    # 170 → 20
            b_ = int(45  - 10 * t)     # 45  → 35
        return QColor(r_, g_, b_)

    def paintEvent(self, _):
        if not self._labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        n      = len(self._labels)
        offset = 28

        font_lbl = QFont(); font_lbl.setPointSize(8); font_lbl.setBold(True)
        font_val = QFont(); font_val.setPointSize(7)

        # ── Axis labels ───────────────────────────────────────────────────
        p.setFont(font_lbl)
        p.setPen(_color(TEXT_M))
        for i, lbl in enumerate(self._labels):
            x = offset + i * self.CELL + self.CELL // 2
            p.drawText(x - 16, 2, 32, offset - 4,
                       Qt.AlignmentFlag.AlignCenter, lbl)
            p.drawText(0, offset + i * self.CELL, offset - 4, self.CELL,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)

        # ── Cells ─────────────────────────────────────────────────────────
        for row in range(n):
            for col in range(n):
                val = self._values[row][col] if (
                    row < len(self._values) and col < len(self._values[row])
                ) else 0.0
                is_diag = (row == col)
                color   = self._val_to_color(val, diagonal=is_diag)

                cx = offset + col * self.CELL
                cy = offset + row * self.CELL

                p.setBrush(QBrush(color))
                p.setPen(QPen(_color("#FFFFFF"), 1.5))
                p.drawRect(cx, cy, self.CELL - 1, self.CELL - 1)

                # Cell value text — dark on light cells, white on dark cells
                p.setFont(font_val)
                brightness = (color.red() * 299 + color.green() * 587
                              + color.blue() * 114) / 1000
                text_col = "#1F2937" if brightness > 140 else "#FFFFFF"
                p.setPen(_color(text_col))
                label_txt = "—" if is_diag else f"{val:.2f}"
                p.drawText(cx, cy, self.CELL - 1, self.CELL - 1,
                           Qt.AlignmentFlag.AlignCenter, label_txt)

        # ── Color scale legend ────────────────────────────────────────────
        legend_x = offset
        legend_y = offset + n * self.CELL + 6
        legend_w = n * self.CELL
        legend_h = 8
        if legend_w > 0:
            grad = QLinearGradient(legend_x, 0, legend_x + legend_w, 0)
            grad.setColorAt(0.0, self._val_to_color(0.0))
            grad.setColorAt(0.5, self._val_to_color(0.5))
            grad.setColorAt(1.0, self._val_to_color(1.0))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(legend_x, legend_y, legend_w, legend_h, 3, 3)
            p.setFont(font_val)
            p.setPen(_color(TEXT_M))
            p.drawText(legend_x, legend_y + legend_h + 2, 30, 12,
                       Qt.AlignmentFlag.AlignLeft, "0.0")
            p.drawText(legend_x + legend_w // 2 - 10, legend_y + legend_h + 2,
                       20, 12, Qt.AlignmentFlag.AlignCenter, "0.5")
            p.drawText(legend_x + legend_w - 24, legend_y + legend_h + 2,
                       24, 12, Qt.AlignmentFlag.AlignRight, "1.0")

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


class GenusTableWidget(QWidget):
    """
    Sortable two-column table: Genus name | Relative abundance (%).

    data: list of {"genus": str, "relative_abundance": float}
          as returned by assessment_service.get_genus_data(run_id).

    The user can click either column header to sort ascending / descending.
    """

    def __init__(
        self,
        data: list[dict] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data: list[dict] = data or []
        self._build()
        if self._data:
            self._populate()

    # ── Construction ──────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Summary label (e.g. "14 genera")
        self._summary = QLabel("")
        self._summary.setStyleSheet(f"font-size:11px; color:{TEXT_HINT};")
        root.addWidget(self._summary)

        # Table
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Genus", "Rel. Abundance (%)"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            "QTableWidget { border: none; }"
            "QHeaderView::section { font-size: 11px; padding: 4px 8px; }"
        )
        # Default sort: descending abundance
        self._table.sortItems(1, Qt.SortOrder.DescendingOrder)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._table)

    # ── Public API ────────────────────────────────────────────────────────

    def set_data(self, data: list[dict]) -> None:
        """
        Refresh the table.
        data: [{"genus": str, "relative_abundance": float}, ...]
        """
        self._data = data
        self._populate()

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._summary.setText("")

    # ── Internal ──────────────────────────────────────────────────────────

    def _populate(self) -> None:
        # Disable sorting while inserting to avoid mid-insert re-sorts
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._data))

        for row, entry in enumerate(self._data):
            genus = entry.get("genus", "Unknown")
            abundance = float(entry.get("relative_abundance", 0.0))

            genus_item = QTableWidgetItem(genus)
            genus_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            # Color dot prefix: reuse GENUS_COLORS palette by index
            # (purely cosmetic — the dot is drawn via a styled QLabel in the
            #  legend; here we tint the text a little instead)
            abund_item = NumericSortItem(abundance, fmt=".2f")

            self._table.setItem(row, 0, genus_item)
            self._table.setItem(row, 1, abund_item)

        # Re-enable sorting and apply default (abundance descending)
        self._table.setSortingEnabled(True)
        self._table.sortItems(1, Qt.SortOrder.DescendingOrder)

        n = len(self._data)
        self._summary.setText(
            f"{n} genera"
        )
