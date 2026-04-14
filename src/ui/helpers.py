"""
Axis – layout helpers.

Factory functions that produce correctly-named/styled Qt widgets so that
the app stylesheet selectors actually match.  Every panel imports from here
instead of constructing QFrame/QLabel inline with magic strings.
"""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt


# ── Cards ─────────────────────────────────────────────────────────────────────

def card(parent: QWidget | None = None) -> QFrame:
    """White rounded card with border."""
    f = QFrame(parent)
    f.setObjectName("card")
    f.setLayout(QVBoxLayout())
    f.layout().setContentsMargins(14, 12, 14, 12)
    f.layout().setSpacing(8)
    return f


def card_flat(parent: QWidget | None = None) -> QFrame:
    """Slightly smaller card variant."""
    f = QFrame(parent)
    f.setObjectName("card_flat")
    f.setLayout(QVBoxLayout())
    f.layout().setContentsMargins(12, 10, 12, 10)
    f.layout().setSpacing(6)
    return f


# ── Labels ────────────────────────────────────────────────────────────────────

def page_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("page_title")
    return lbl


def section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section_title")
    return lbl


def label_muted(text: str, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("label_muted")
    lbl.setWordWrap(wrap)
    return lbl


def label_hint(text: str, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("label_hint")
    lbl.setWordWrap(wrap)
    return lbl


def stat_card(value: str, label: str, sub: str = "") -> QFrame:
    """Small stat tile: big number + label row."""
    f = QFrame()
    f.setObjectName("stat_card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(2)

    lbl = QLabel(label)
    lbl.setObjectName("stat_label")
    lay.addWidget(lbl)

    val = QLabel(value)
    val.setObjectName("stat_value")
    lay.addWidget(val)

    if sub:
        s = QLabel(sub)
        s.setObjectName("stat_sub")
        lay.addWidget(s)
    return f


# ── Buttons ───────────────────────────────────────────────────────────────────

def btn_primary(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("btn_primary")
    return b


def btn_outline(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("btn_outline")
    return b


# ── Run / metric pill switcher ────────────────────────────────────────────────

class PillSwitcher(QWidget):
    """
    A row of toggle-style pills.
    Emits nothing by itself — connect to button.clicked externally,
    or use the convenience method active_label().
    """

    def __init__(self, labels: list[str],
                 obj_name: str = "pill",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._obj   = obj_name
        self._btns: dict[str, QPushButton] = {}
        self._active: str = labels[0] if labels else ""

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        for lbl in labels:
            b = QPushButton(lbl)
            b.setObjectName(obj_name)
            b.setProperty("active", lbl == self._active)
            b.clicked.connect(lambda _, l=lbl: self.select(l))
            lay.addWidget(b)
            self._btns[lbl] = b

    def select(self, label: str) -> None:
        if label not in self._btns or label == self._active:
            return
        # deactivate old
        self._btns[self._active].setProperty("active", False)
        self._btns[self._active].style().unpolish(self._btns[self._active])
        self._btns[self._active].style().polish(self._btns[self._active])
        # activate new
        self._active = label
        self._btns[label].setProperty("active", True)
        self._btns[label].style().unpolish(self._btns[label])
        self._btns[label].style().polish(self._btns[label])

    @property
    def active(self) -> str:
        return self._active

    def on_changed(self, slot) -> None:
        """Connect all buttons to the same slot(label: str)."""
        for lbl, btn in self._btns.items():
            btn.clicked.connect(lambda _, l=lbl: slot(l))


# ── Dividers ──────────────────────────────────────────────────────────────────

def hdivider() -> QFrame:
    f = QFrame()
    f.setObjectName("hdivider")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    return f


def vdivider() -> QFrame:
    f = QFrame()
    f.setObjectName("vdivider")
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFixedWidth(1)
    return f


# ── Banners ───────────────────────────────────────────────────────────────────

def banner(text: str, kind: str = "err") -> QFrame:
    """kind: 'err' | 'warn' | 'ok'"""
    f = QFrame()
    f.setObjectName(f"banner_{kind}")
    lay = QHBoxLayout(f)
    lay.setContentsMargins(12, 8, 12, 8)
    lbl = QLabel(text)
    lbl.setObjectName(f"banner_text_{kind}")
    lbl.setWordWrap(True)
    lay.addWidget(lbl)
    return f


# ── Stretch spacer ────────────────────────────────────────────────────────────

def vstretch() -> QWidget:
    sp = QWidget()
    sp.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    return sp