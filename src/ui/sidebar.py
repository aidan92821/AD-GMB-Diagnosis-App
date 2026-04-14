"""
Axis — left sidebar navigation.

The sidebar owns the list of nav items and emits *page_changed(index)*
when the user clicks a different section.  The main window listens to
this signal and switches the content QStackedWidget accordingly.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QWidget,
)
from PyQt6.QtCore import pyqtSignal

from resources.styles import TEXT_SECONDARY


# Navigation entries: (display_name, icon_char)
NAV_ITEMS = [
    ("Overview",        "⊞"),
    ("Upload Runs",     "↑"),
    ("Diversity",       "≋"),
    ("Taxonomy",        "⊙"),
    ("ASV Table",       "⋮"),
    ("Phylogeny",       "∿"),
    ("Alzheimer Risk",  "♥"),
]


class Sidebar(QFrame):
    """
    Vertical navigation panel.  Emits *page_changed(index)* (0-based)
    when the user selects a menu item.
    """

    page_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(175)

        self._buttons: list[QPushButton] = []
        self._active_index: int = 0

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Logo / app title ──
        logo = QLabel("Axis")
        logo.setStyleSheet(
            "font-size: 15px; font-weight: 700; padding: 14px 16px 4px;"
        )
        layout.addWidget(logo)

        subtitle = QLabel("microbiome analytics")
        subtitle.setObjectName("hint")
        subtitle.setStyleSheet("padding: 0 16px 12px; font-size: 10px;")
        layout.addWidget(subtitle)

        # Thin separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #E0DED6; max-height: 1px; margin: 0;")
        layout.addWidget(sep)

        # ── Nav items ──
        section_label = QLabel("Analysis")
        section_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            "letter-spacing: 0.07em; text-transform: uppercase; "
            "padding: 10px 16px 4px;"
        )
        layout.addWidget(section_label)

        for idx, (name, icon) in enumerate(NAV_ITEMS):
            # Separate "Insights" section before Alzheimer Risk
            if name == "Alzheimer Risk":
                insights_sep = QFrame()
                insights_sep.setFrameShape(QFrame.Shape.HLine)
                insights_sep.setStyleSheet("background: #E0DED6; max-height: 1px; margin: 4px 0;")
                layout.addWidget(insights_sep)

                insights_lbl = QLabel("Insights")
                insights_lbl.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: 10px; "
                    "letter-spacing: 0.07em; text-transform: uppercase; "
                    "padding: 8px 16px 4px;"
                )
                layout.addWidget(insights_lbl)

            btn = QPushButton(f"  {icon}  {name}")
            btn.setObjectName("nav_btn")
            btn.setProperty("active", idx == self._active_index)
            btn.clicked.connect(lambda _, i=idx: self._select(i))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()

        # ── Footer ──
        footer = QLabel("QIIME2 pipeline · v2024.5")
        footer.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; padding: 10px 16px;"
        )
        layout.addWidget(footer)

    def _select(self, index: int) -> None:
        """Activate button at *index* and emit the page_changed signal."""
        if index == self._active_index:
            return

        # Deactivate old button
        old_btn = self._buttons[self._active_index]
        old_btn.setProperty("active", False)
        old_btn.style().unpolish(old_btn)
        old_btn.style().polish(old_btn)

        # Activate new button
        self._active_index = index
        new_btn = self._buttons[index]
        new_btn.setProperty("active", True)
        new_btn.style().unpolish(new_btn)
        new_btn.style().polish(new_btn)

        self.page_changed.emit(index)