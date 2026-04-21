# src/ui/auth_page.py
"""
Login / Register screen — two-column layout.
Left  : dark branded panel (logo, tagline, feature bullets)
Right : white form panel (login / register)
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QStackedWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from services.assessment_service import login_user, register_user

# Colour constants (inline so auth_page works standalone before APP_QSS loads)
_DARK   = "#1E2128"
_DARK2  = "#252B38"
_ACCENT = "#6366F1"
_ACCENT_D = "#4F46E5"
_WHITE  = "#FFFFFF"
_BG     = "#F4F5F7"
_CARD   = "#FFFFFF"
_BORDER = "#E5E7EB"
_TH     = "#111827"
_TM     = "#6B7280"
_HINT   = "#9CA3AF"
_ERR_FG = "#991B1B"
_ERR_BG = "#FEF2F2"
_OK_FG  = "#065F46"
_OK_BG  = "#ECFDF5"


class AuthPage(QWidget):
    """
    Full-screen login / register page.
    Emits login_success({"user_id": int, "username": str}) on success.
    """

    login_success = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {_DARK};")
        self._build_ui()

    # ── Root layout: left branding | right form ───────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_left_panel(), 5)
        root.addWidget(self._build_right_panel(), 4)

    # ── Left: dark brand panel ────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {_DARK};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(64, 64, 64, 64)
        lay.setSpacing(0)

        # Logo mark
        logo_mark = QLabel("⬡")
        logo_mark.setStyleSheet(
            f"font-size: 42px; color: {_ACCENT}; background: transparent;"
        )
        lay.addWidget(logo_mark)
        lay.addSpacing(16)

        # App name
        app_name = QLabel("Axis")
        app_name.setStyleSheet(
            f"font-size: 32px; font-weight: 800; color: {_WHITE}; background: transparent;"
        )
        lay.addWidget(app_name)
        lay.addSpacing(12)

        # Tagline
        tagline = QLabel("Microbiome-based\nAlzheimer's risk analytics")
        tagline.setStyleSheet(
            f"font-size: 15px; color: #94A3B8; background: transparent; line-height: 1.5;"
        )
        tagline.setWordWrap(True)
        lay.addWidget(tagline)
        lay.addSpacing(48)

        # Feature bullets
        features = [
            ("⬇", "Fetch real NCBI sequencing data"),
            ("≋",  "Alpha & beta diversity analysis"),
            ("⊙",  "Taxonomy & ASV profiling"),
            ("♥",  "Alzheimer's risk assessment"),
        ]
        for icon, text in features:
            row = QHBoxLayout()
            row.setSpacing(14)
            ic = QLabel(icon)
            ic.setFixedWidth(22)
            ic.setStyleSheet(f"color: {_ACCENT}; font-size: 15px; background: transparent;")
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tx = QLabel(text)
            tx.setStyleSheet(f"font-size: 13px; color: #CBD5E1; background: transparent;")
            row.addWidget(ic)
            row.addWidget(tx)
            row.addStretch()
            lay.addLayout(row)
            lay.addSpacing(14)

        lay.addStretch()

        # Footer note
        note = QLabel("Experimental research tool.\nNot for clinical use.")
        note.setStyleSheet(
            f"font-size: 11px; color: #475569; background: transparent;"
        )
        lay.addWidget(note)

        return panel

    # ── Right: white form panel ───────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {_CARD};")
        lay = QVBoxLayout(panel)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(60, 60, 60, 60)

        # Inner stack: 0=login, 1=register
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QWidget { background: transparent; border: none; }")
        self._stack.setFixedWidth(340)
        self._stack.addWidget(self._build_login_form())
        self._stack.addWidget(self._build_register_form())

        lay.addWidget(self._stack, 0, Qt.AlignmentFlag.AlignCenter)
        return panel

    # ── Login form ────────────────────────────────────────────────────────────

    def _build_login_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        heading = QLabel("Welcome back")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {_TH}; background: transparent;"
        )
        sub = QLabel("Sign in to your Axis account")
        sub.setStyleSheet(
            f"font-size: 13px; color: {_TM}; background: transparent; padding-bottom: 28px;"
        )
        lay.addWidget(heading)
        lay.addWidget(sub)

        lay.addWidget(_field_label("Username"))
        self._login_username = _input("Enter your username")
        lay.addWidget(self._login_username)
        lay.addSpacing(14)

        lay.addWidget(_field_label("Password"))
        self._login_password = _input("Enter your password", password=True)
        self._login_password.returnPressed.connect(self._on_login)
        lay.addWidget(self._login_password)
        lay.addSpacing(6)

        self._login_error = _error_label()
        lay.addWidget(self._login_error)
        lay.addSpacing(10)

        login_btn = _primary_btn("Sign In")
        login_btn.clicked.connect(self._on_login)
        lay.addWidget(login_btn)
        lay.addSpacing(20)

        div = _divider_with_text("or")
        lay.addWidget(div)
        lay.addSpacing(20)

        switch_btn = QPushButton("Create an account")
        switch_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1.5px solid {_BORDER};
                border-radius: 8px;
                color: {_TH};
                font-size: 13px;
                font-weight: 600;
                padding: 10px;
            }}
            QPushButton:hover {{
                background: {_BG};
                border-color: #9CA3AF;
            }}
        """)
        switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        switch_btn.clicked.connect(self._go_register)
        lay.addWidget(switch_btn)

        return w

    # ── Register form ─────────────────────────────────────────────────────────

    def _build_register_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        heading = QLabel("Create account")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {_TH}; background: transparent;"
        )
        sub = QLabel("Start analysing your microbiome data")
        sub.setStyleSheet(
            f"font-size: 13px; color: {_TM}; background: transparent; padding-bottom: 28px;"
        )
        lay.addWidget(heading)
        lay.addWidget(sub)

        lay.addWidget(_field_label("Username"))
        self._reg_username = _input("Choose a username")
        lay.addWidget(self._reg_username)
        lay.addSpacing(14)

        lay.addWidget(_field_label("Password"))
        self._reg_password = _input("At least 6 characters", password=True)
        lay.addWidget(self._reg_password)
        lay.addSpacing(14)

        lay.addWidget(_field_label("Confirm password"))
        self._reg_confirm = _input("Re-enter your password", password=True)
        self._reg_confirm.returnPressed.connect(self._on_register)
        lay.addWidget(self._reg_confirm)
        lay.addSpacing(6)

        self._reg_error = _error_label()
        lay.addWidget(self._reg_error)
        lay.addSpacing(10)

        reg_btn = _primary_btn("Create Account")
        reg_btn.clicked.connect(self._on_register)
        lay.addWidget(reg_btn)
        lay.addSpacing(16)

        back_row = QHBoxLayout()
        back_row.setSpacing(4)
        already = QLabel("Already have an account?")
        already.setStyleSheet(f"font-size: 12px; color: {_TM}; background: transparent;")
        back_btn = QPushButton("Sign in")
        back_btn.setStyleSheet(
            f"color: {_ACCENT}; background: transparent; border: none; "
            f"font-size: 12px; font-weight: 600; padding: 0;"
        )
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._go_login)
        back_row.addStretch()
        back_row.addWidget(already)
        back_row.addWidget(back_btn)
        back_row.addStretch()
        lay.addLayout(back_row)

        return w

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _on_login(self) -> None:
        username = self._login_username.text().strip()
        password = self._login_password.text()
        if not username or not password:
            self._show_login_error("Please enter your username and password.")
            return
        try:
            user = login_user(username, password)
            self._login_password.clear()
            self._login_error.hide()
            self.login_success.emit(user)
        except Exception as exc:
            self._show_login_error(str(exc))

    def _on_register(self) -> None:
        username = self._reg_username.text().strip()
        password = self._reg_password.text()
        confirm  = self._reg_confirm.text()
        if not username or not password or not confirm:
            self._show_reg_error("All fields are required.")
            return
        if len(password) < 6:
            self._show_reg_error("Password must be at least 6 characters.")
            return
        if password != confirm:
            self._show_reg_error("Passwords do not match.")
            return
        try:
            user = register_user(username, password, email="")
            self._reg_username.clear()
            self._reg_password.clear()
            self._reg_confirm.clear()
            self._reg_error.hide()
            self.login_success.emit(user)
        except Exception as exc:
            self._show_reg_error(str(exc))

    def _go_register(self) -> None:
        self._login_error.hide()
        self._stack.setCurrentIndex(1)

    def _go_login(self) -> None:
        self._reg_error.hide()
        self._stack.setCurrentIndex(0)

    def _show_login_error(self, msg: str) -> None:
        self._login_error.setText(f"  {msg}")
        self._login_error.show()

    def _show_reg_error(self, msg: str) -> None:
        self._reg_error.setText(f"  {msg}")
        self._reg_error.show()


# ── Widget helpers ────────────────────────────────────────────────────────────

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 12px; font-weight: 600; color: {_TH}; "
        "background: transparent; padding-bottom: 5px;"
    )
    return lbl


def _input(placeholder: str, *, password: bool = False) -> QLineEdit:
    f = QLineEdit()
    f.setPlaceholderText(placeholder)
    f.setFixedHeight(42)
    if password:
        f.setEchoMode(QLineEdit.EchoMode.Password)
    f.setStyleSheet(f"""
        QLineEdit {{
            background: {_BG};
            border: 1.5px solid {_BORDER};
            border-radius: 8px;
            padding: 0 12px;
            font-size: 13px;
            color: {_TH};
        }}
        QLineEdit:focus {{
            border-color: #6366F1;
            background: {_WHITE};
        }}
    """)
    return f


def _primary_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(44)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {_ACCENT};
            color: {_WHITE};
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 700;
        }}
        QPushButton:hover   {{ background: {_ACCENT_D}; }}
        QPushButton:pressed {{ background: #4338CA; }}
    """)
    return btn


def _error_label() -> QLabel:
    lbl = QLabel("")
    lbl.setStyleSheet(f"""
        background: {_ERR_BG};
        color: {_ERR_FG};
        border: 1px solid #FECACA;
        border-radius: 6px;
        font-size: 12px;
        padding: 7px 10px;
    """)
    lbl.setWordWrap(True)
    lbl.hide()
    return lbl


def _divider_with_text(text: str) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    for _ in range(2):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {_BORDER}; max-height: 1px;")
        row.addWidget(line, 1)
        if _ == 0:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size: 11px; color: {_HINT}; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(lbl)
    return w
