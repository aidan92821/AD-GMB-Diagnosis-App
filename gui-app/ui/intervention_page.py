"""
Intervention Simulation Page  (Figure 2)
─────────────────────────────────────────
Left  : sliders for Probiotic, Antibiotics, Fiber, Processed Foods
Right : line chart – AD Risk (%) vs. Number of Simulations
"""
import random
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QSlider, QPushButton, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# ── Line chart ───────────────────────────────────────────────
class SimulationChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.fig.add_subplot(111)
        self._style_ax()
        self.draw()

    def _style_ax(self):
        self.ax.set_xlabel("Number of Simulations", fontsize=10, fontweight="bold")
        self.ax.set_ylabel("AD Risk (%)", fontsize=10, fontweight="bold")
        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(0, 100)
        self.ax.set_facecolor("white")
        self.fig.patch.set_facecolor("white")
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)

    def update_chart(self, history: list):
        self.ax.clear()
        self._style_ax()
        if history:
            xs = list(range(1, len(history) + 1))
            self.ax.plot(xs, history, marker="o", color="#2979d4",
                         linewidth=2, markersize=7, markerfacecolor="#2979d4")
            self.ax.set_xlim(0, max(10, len(history) + 1))
        self.draw()


# ── Labelled Slider row ──────────────────────────────────────
class LabelledSlider(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setObjectName("SliderLabel")
        layout.addWidget(lbl)

        row = QHBoxLayout()
        minus = QLabel("-")
        minus.setStyleSheet("color:#2979d4; font-weight:bold; font-size:16px;")
        plus  = QLabel("+")
        plus.setStyleSheet("color:#2979d4; font-weight:bold; font-size:16px;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-10, 10)
        self.slider.setValue(0)
        self.slider.setFixedHeight(28)

        row.addWidget(minus)
        row.addWidget(self.slider, 1)
        row.addWidget(plus)
        layout.addLayout(row)

    @property
    def value(self) -> int:
        return self.slider.value()


# ── Intervention Page ────────────────────────────────────────
class InterventionPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app = app_state
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # ── Left panel ────────────────────────────────────────
        left = QFrame()
        left.setObjectName("Card")
        left.setFixedWidth(200)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 12, 16)
        left_layout.setSpacing(6)

        title = QLabel("Adjust\nVariables")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title)
        left_layout.addSpacing(8)

        self.probiotic     = LabelledSlider("Probiotic")
        self.antibiotics   = LabelledSlider("Antibiotics")
        self.fiber         = LabelledSlider("Fiber")
        self.processed     = LabelledSlider("Processed Foods")

        for w in [self.probiotic, self.antibiotics, self.fiber, self.processed]:
            left_layout.addWidget(w)

        left_layout.addStretch(1)

        sim_btn = QPushButton("SIMULATE\nINTERVENTION")
        sim_btn.setObjectName("ActionBtn")
        sim_btn.clicked.connect(self._run_simulation)
        left_layout.addWidget(sim_btn)

        outer.addWidget(left)

        # ── Right panel ───────────────────────────────────────
        right = QFrame()
        right.setObjectName("Card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 10)

        header = QHBoxLayout()
        chart_title = QLabel("Intervention Simulation")
        chart_title.setObjectName("CardTitle")
        chart_title.setStyleSheet("font-size:16px; font-weight:bold; color:#2979d4;")
        header.addWidget(chart_title)
        header.addStretch()

        tog = QPushButton("☀")
        tog.setObjectName("ToggleBtn")
        tog.setCheckable(True)
        header.addWidget(tog)
        right_layout.addLayout(header)

        self.chart = SimulationChart()
        right_layout.addWidget(self.chart)

        outer.addWidget(right, stretch=1)

    # ── Simulation logic ─────────────────────────────────────
    def _run_simulation(self):
        """
        Placeholder model:
        Adjusts baseline risk based on slider positions, adds noise.
        Replace with real model inference.
        """
        base = self.app.ad_risk if self.app.ad_risk else 50.0

        # crude delta from sliders (positive = protective for probiotic/fiber)
        delta = (
            - self.probiotic.value * 1.5
            + self.antibiotics.value * 1.2
            - self.fiber.value * 1.0
            + self.processed.value * 1.3
        )
        new_risk = max(1, min(99, base + delta + random.gauss(0, 3)))
        new_risk = round(new_risk, 1)

        self.app.simulation_history.append(new_risk)
        self.app.ad_risk = new_risk
        self.refresh_chart()

        # Update dashboard risk label too
        self.app.dashboard_page.risk_label.setText(f"{new_risk}%")

    def refresh_chart(self):
        self.chart.update_chart(self.app.simulation_history)

    def reset(self):
        for slider in [self.probiotic, self.antibiotics, self.fiber, self.processed]:
            slider.slider.setValue(0)
        self.chart.update_chart([])