# src/ui/profile_page.py
"""
User profile page — account info, project history, logout.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from resources.styles import (
    ACCENT, ACCENT_LIGHT, BG_CARD, BG_PAGE, BORDER, TEXT_H, TEXT_M, TEXT_HINT,
    SUCCESS_BG, SUCCESS_FG, WARN_BG, WARN_FG, DANGER_BG, DANGER_FG, SB_BG, WHITE,
)

from services.assessment_service import list_user_projects


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except Exception:
        return ""


class ProfilePage(QWidget):
    """
    Signed-in user's account info and project history.

    Signals:
        load_project(bio_proj_accession)  — re-fetch a past project
        logout_requested()                — user clicked Sign Out
    """

    load_project      = pyqtSignal(str)
    logout_requested  = pyqtSignal()
    delete_project    = pyqtSignal(int)   # emits project_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user: dict | None = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(24)

        # ── Page header ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("My Account")
        title.setObjectName("page_title")
        hdr.addWidget(title)
        hdr.addStretch()
        signout_btn = QPushButton("Sign Out")
        signout_btn.setObjectName("btn_outline")
        signout_btn.clicked.connect(self.logout_requested.emit)
        hdr.addWidget(signout_btn)
        root.addLayout(hdr)

        # ── User card ─────────────────────────────────────────────────────────
        self._user_card = self._build_user_card()
        root.addWidget(self._user_card)

        # ── Stats row ─────────────────────────────────────────────────────────
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(12)
        root.addLayout(self._stats_row)

        # ── Projects heading ──────────────────────────────────────────────────
        proj_hdr = QHBoxLayout()
        proj_lbl = QLabel("Projects")
        proj_lbl.setObjectName("section_title")
        proj_hdr.addWidget(proj_lbl)
        proj_hdr.addStretch()
        self._proj_count_lbl = QLabel("")
        self._proj_count_lbl.setObjectName("label_muted")
        proj_hdr.addWidget(self._proj_count_lbl)
        root.addLayout(proj_hdr)

        # ── Project cards ─────────────────────────────────────────────────────
        self._projects_layout = QVBoxLayout()
        self._projects_layout.setSpacing(10)
        root.addLayout(self._projects_layout)

        root.addStretch()

    def _build_user_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(18)

        # Avatar circle
        avatar = QFrame()
        avatar.setFixedSize(48, 48)
        avatar.setStyleSheet(f"""
            QFrame {{
                background: {ACCENT_LIGHT};
                border-radius: 24px;
                border: none;
            }}
        """)
        av_lay = QVBoxLayout(avatar)
        av_lay.setContentsMargins(0, 0, 0, 0)
        av_lbl = QLabel("◉")
        av_lbl.setStyleSheet(f"font-size: 20px; color: {ACCENT}; background: transparent;")
        av_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av_lay.addWidget(av_lbl)
        lay.addWidget(avatar)

        # Name + join date
        info = QVBoxLayout()
        info.setSpacing(4)
        self._username_lbl = QLabel("")
        self._username_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {TEXT_H}; background: transparent;"
        )
        self._joined_lbl = QLabel("")
        self._joined_lbl.setObjectName("label_muted")
        info.addWidget(self._username_lbl)
        info.addWidget(self._joined_lbl)
        lay.addLayout(info)
        lay.addStretch()

        # Role badge
        role_badge = QLabel("Researcher")
        role_badge.setStyleSheet(f"""
            background: {ACCENT_LIGHT};
            color: {ACCENT};
            border-radius: 10px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 700;
        """)
        lay.addWidget(role_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        return card

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, user: dict) -> None:
        """Call after login to populate the page."""
        self._user = user
        self._username_lbl.setText(user.get("username", ""))
        joined = _fmt_date(user.get("created_at"))
        self._joined_lbl.setText(f"Member since {joined}" if joined else "Axis member")
        self._refresh_projects()

    def refresh(self) -> None:
        """Re-load project list from DB (call after a fetch completes)."""
        if self._user:
            self._refresh_projects()

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh_projects(self) -> None:
        if not self._user:
            return

        # Clear stats row
        while self._stats_row.count():
            item = self._stats_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear project cards
        while self._projects_layout.count():
            item = self._projects_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            projects = list_user_projects(self._user["user_id"])
        except Exception:
            projects = []

        total_runs = sum(p["run_count"] for p in projects)

        # Stats
        for label, value, sub in [
            ("Projects",   str(len(projects)), "total"),
            ("Total Runs", str(total_runs),    "across all projects"),
        ]:
            self._stats_row.addWidget(self._stat_card(label, value, sub))
        self._stats_row.addStretch()

        # Project count label
        self._proj_count_lbl.setText(
            f"{len(projects)} project{'s' if len(projects) != 1 else ''}"
        )

        if not projects:
            empty = QFrame()
            empty.setObjectName("card_flat")
            empty_lay = QVBoxLayout(empty)
            empty_lay.setContentsMargins(24, 32, 24, 32)
            empty_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon = QLabel("⬡")
            icon.setStyleSheet(f"font-size: 28px; color: {ACCENT}; background: transparent;")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg = QLabel("No projects yet")
            msg.setStyleSheet(
                f"font-size: 14px; font-weight: 700; color: {TEXT_H}; background: transparent;"
            )
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint = QLabel("Fetch a BioProject from the Overview page to get started.")
            hint.setObjectName("label_hint")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            empty_lay.addWidget(icon)
            empty_lay.addSpacing(8)
            empty_lay.addWidget(msg)
            empty_lay.addSpacing(4)
            empty_lay.addWidget(hint)
            self._projects_layout.addWidget(empty)
            return

        for project in projects:
            self._projects_layout.addWidget(self._project_card(project))

    def _confirm_delete(self, project_id: int) -> None:
        """Ask the user to confirm before deleting a project."""
        box = QMessageBox(self)
        box.setWindowTitle("Delete project")
        box.setText("Delete this project?")
        box.setInformativeText(
            "All runs, genus data, diversity records and analysis results "
            "for this project will be permanently removed."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Yes).setText("Delete")
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.delete_project.emit(project_id)

    # ── Card builders ─────────────────────────────────────────────────────────

    def _stat_card(self, label: str, value: str, sub: str = "") -> QFrame:
        card = QFrame()
        card.setObjectName("stat_card")
        card.setFixedWidth(160)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        lbl = QLabel(label)
        lbl.setObjectName("stat_label")
        val = QLabel(value)
        val.setObjectName("stat_value")
        lay.addWidget(lbl)
        lay.addWidget(val)
        if sub:
            s = QLabel(sub)
            s.setObjectName("stat_sub")
            lay.addWidget(s)
        return card

    def _project_card(self, project: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card_flat")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top row: name + actions
        top = QHBoxLayout()
        top.setContentsMargins(20, 16, 16, 10)
        top.setSpacing(12)

        # Left: project name + meta
        info = QVBoxLayout()
        info.setSpacing(5)

        name_lbl = QLabel(project["name"])
        name_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {TEXT_H}; background: transparent;"
        )
        info.addWidget(name_lbl)

        runs       = project.get("runs", [])
        bio_projs  = list(dict.fromkeys(
            r["bio_proj_accession"] for r in runs if r.get("bio_proj_accession")
        ))
        n          = project["run_count"]
        date_str   = _fmt_date(project.get("created_at"))
        meta_parts = []
        if bio_projs:
            meta_parts.append("  ·  ".join(bio_projs[:2]))
        meta_parts.append(f"{n} run{'s' if n != 1 else ''}")
        if date_str:
            meta_parts.append(date_str)

        meta_lbl = QLabel("   ·   ".join(meta_parts))
        meta_lbl.setObjectName("label_muted")
        info.addWidget(meta_lbl)

        top.addLayout(info, 1)

        # Risk badge
        risk_labels = [r["risk_label"] for r in runs if r.get("risk_label")]
        if risk_labels:
            risk = _worst_risk(risk_labels)
            badge = QLabel(risk)
            badge.setStyleSheet(_risk_badge_qss(risk))
            top.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # Load button
        first_bp   = bio_projs[0] if bio_projs else None
        project_id = project["project_id"]
        if first_bp:
            load_btn = QPushButton("Load →")
            load_btn.setObjectName("btn_primary")
            load_btn.setFixedHeight(30)
            load_btn.setFixedWidth(80)
            load_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT};
                    color: white;
                    border: none;
                    border-radius: 7px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 0;
                }}
                QPushButton:hover   {{ background: #4F46E5; }}
                QPushButton:pressed {{ background: #4338CA; }}
            """)
            load_btn.setToolTip(f"Re-fetch {first_bp} from NCBI")
            load_btn.clicked.connect(lambda _, bp=first_bp: self.load_project.emit(bp))
            top.addWidget(load_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 30)
        del_btn.setToolTip("Delete this project and all its runs")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1.5px solid #FECACA;
                border-radius: 7px;
                color: #EF4444;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton:hover   {{ background: #FEF2F2; border-color: #EF4444; }}
            QPushButton:pressed {{ background: #FEE2E2; }}
        """)
        del_btn.clicked.connect(
            lambda _, pid=project_id: self._confirm_delete(pid)
        )
        top.addWidget(del_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        outer.addLayout(top)

        # Run pills row (if there are runs with accessions)
        run_accessions = [r["srr_accession"] for r in runs if r.get("srr_accession")]
        if run_accessions:
            divider = QFrame()
            divider.setStyleSheet(f"background: {BORDER}; max-height: 1px;")
            divider.setFixedHeight(1)
            outer.addWidget(divider)

            pills_row = QHBoxLayout()
            pills_row.setContentsMargins(20, 8, 20, 12)
            pills_row.setSpacing(6)
            for srr in run_accessions[:6]:
                pill = QLabel(srr)
                pill.setStyleSheet(f"""
                    background: {BG_PAGE};
                    color: {TEXT_M};
                    border: 1px solid {BORDER};
                    border-radius: 10px;
                    padding: 2px 9px;
                    font-size: 10px;
                    font-family: monospace;
                """)
                pills_row.addWidget(pill)
            if len(run_accessions) > 6:
                more = QLabel(f"+{len(run_accessions) - 6} more")
                more.setObjectName("label_hint")
                pills_row.addWidget(more)
            pills_row.addStretch()
            outer.addLayout(pills_row)

        return card


# ── Helpers ───────────────────────────────────────────────────────────────────

def _worst_risk(labels: list[str]) -> str:
    if "High" in labels:
        return "High"
    if "Moderate" in labels:
        return "Moderate"
    return "Low"


def _risk_badge_qss(risk: str) -> str:
    if risk == "High":
        bg, fg = DANGER_BG, DANGER_FG
    elif risk == "Moderate":
        bg, fg = WARN_BG, WARN_FG
    else:
        bg, fg = SUCCESS_BG, SUCCESS_FG
    return (
        f"background: {bg}; color: {fg}; border-radius: 10px; "
        "padding: 3px 11px; font-size: 11px; font-weight: 700;"
    )
