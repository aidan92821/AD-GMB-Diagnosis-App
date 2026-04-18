"""
Axis – styles.

Single source of truth for colours and the application stylesheet.
Every widget imports from here; nothing is hard-coded in panel files.
"""

# ── Colour tokens ─────────────────────────────────────────────────────────────
WHITE        = "#FFFFFF"
BLACK        = "#000000"
BG_PAGE      = "#F4F5F7"
BG_CARD      = "#FFFFFF"
BG_INPUT     = "#F9FAFB"

BORDER       = "#E5E7EB"
BORDER_FOCUS = "#6366F1"

TEXT_H        = "#111827"
TEXT_B        = "#374151"
TEXT_M        = "#6B7280"
TEXT_HINT     = "#9CA3AF"
TEXT_SECONDARY = "#9CA3AF"

ACCENT       = "#6366F1"
ACCENT_DARK  = "#4F46E5"
ACCENT_LIGHT = "#EEF2FF"

SUCCESS_BG = "#ECFDF5"; SUCCESS_FG = "#065F46"
WARN_BG    = "#FFFBEB"; WARN_FG    = "#92400E"
DANGER_BG  = "#FEF2F2"; DANGER_FG  = "#991B1B"

# Sidebar
SB_BG          = "#1E2128"
SB_ACTIVE_BG   = "#2D3748"
SB_ACTIVE_TEXT = "#FFFFFF"
SB_IDLE_TEXT   = "#94A3B8"
SB_HOVER_BG    = "#252B38"
SB_SECTION     = "#64748B"

# Chart genus palette
GENUS_COLORS = [
    "#6366F1", "#10B981", "#F59E0B", "#3B82F6", "#EF4444",
    "#8B5CF6", "#14B8A6", "#F97316", "#EC4899", "#84CC16",
]

# ── Full application QSS ──────────────────────────────────────────────────────
APP_QSS = f"""

/* ── Global reset ── */
* {{
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: {TEXT_B};
}}

QMainWindow {{
    background: {BG_PAGE};
}}

QWidget {{
    background: transparent;
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: transparent;
    width: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #D1D5DB;
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #9CA3AF;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 5px;
}}
QScrollBar::handle:horizontal {{
    background: #D1D5DB;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #9CA3AF;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Sidebar ── */
QFrame#sidebar {{
    background: {SB_BG};
    border: none;
    border-right: 1px solid #2D3748;
}}

QLabel#sb_logo {{
    color: {WHITE};
    font-size: 16px;
    font-weight: 800;
    background: transparent;
    letter-spacing: -0.3px;
    padding: 0;
}}

QLabel#sb_sub {{
    color: #475569;
    font-size: 10px;
    background: transparent;
    letter-spacing: 0.3px;
}}

QLabel#sb_section {{
    color: #475569;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    background: transparent;
    padding: 16px 20px 5px 20px;
}}

QPushButton#nav_btn {{
    background: transparent;
    border: none;
    border-radius: 7px;
    color: {SB_IDLE_TEXT};
    font-size: 13px;
    text-align: left;
    padding: 9px 14px;
    margin: 1px 10px;
}}
QPushButton#nav_btn:hover {{
    background: {SB_HOVER_BG};
    color: #E2E8F0;
}}
QPushButton#nav_btn[active=true] {{
    background: #6366F1;
    color: {WHITE};
    font-weight: 600;
}}

QLabel#sb_footer {{
    color: #374151;
    font-size: 10px;
    background: transparent;
    padding: 10px 20px;
}}

/* ── Top bar ── */
QFrame#topbar {{
    background: {BG_CARD};
    border-bottom: 1px solid {BORDER};
}}
QLabel#topbar_title {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT_H};
    background: transparent;
    letter-spacing: -0.2px;
}}
QLabel#topbar_sub {{
    font-size: 12px;
    color: {TEXT_M};
    background: transparent;
}}

/* ── Badge labels ── */
QLabel#badge_green {{
    background: {SUCCESS_BG};
    color: {SUCCESS_FG};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#badge_yellow {{
    background: {WARN_BG};
    color: {WARN_FG};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#badge_red {{
    background: {DANGER_BG};
    color: {DANGER_FG};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

/* ── Content area ── */
QScrollArea#content_scroll {{
    background: {BG_PAGE};
    border: none;
}}
QWidget#content_host {{
    background: {BG_PAGE};
}}

/* ── Cards ── */
QFrame#card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#card_flat {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

/* ── Page / section headings ── */
QLabel#page_title {{
    font-size: 20px;
    font-weight: 800;
    color: {TEXT_H};
    background: transparent;
    letter-spacing: -0.4px;
}}
QLabel#section_title {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT_H};
    background: transparent;
}}
QLabel#label_muted {{
    font-size: 12px;
    color: {TEXT_M};
    background: transparent;
}}
QLabel#label_hint {{
    font-size: 11px;
    color: {TEXT_HINT};
    background: transparent;
}}

/* ── Stat card ── */
QFrame#stat_card {{
    background: {BG_PAGE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#stat_value {{
    font-size: 24px;
    font-weight: 800;
    color: {TEXT_H};
    background: transparent;
    letter-spacing: -0.5px;
}}
QLabel#stat_label {{
    font-size: 11px;
    font-weight: 600;
    color: {TEXT_M};
    background: transparent;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QLabel#stat_sub {{
    font-size: 10px;
    color: {TEXT_HINT};
    background: transparent;
}}

/* ── Inputs ── */
QLineEdit {{
    background: {BG_PAGE};
    border: 1.5px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    color: {TEXT_H};
    selection-background-color: {ACCENT_LIGHT};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
    background: {WHITE};
}}
QLineEdit[state=ok] {{
    border-color: #10B981;
}}
QLineEdit[state=err] {{
    border-color: #EF4444;
}}
QLineEdit:disabled {{
    background: {BG_PAGE};
    color: {TEXT_HINT};
}}
QLineEdit::placeholder {{
    color: {TEXT_HINT};
}}

QComboBox {{
    background: {BG_PAGE};
    border: 1.5px solid {BORDER};
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
    color: {TEXT_H};
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {ACCENT_DARK};
    outline: none;
    padding: 4px;
}}

/* ── Buttons ── */
QPushButton#btn_primary {{
    background: {ACCENT};
    color: {WHITE};
    border: none;
    border-radius: 8px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#btn_primary:hover {{
    background: {ACCENT_DARK};
}}
QPushButton#btn_primary:pressed {{
    background: #4338CA;
}}
QPushButton#btn_primary:disabled {{
    background: #C7D2FE;
    color: #818CF8;
}}

QPushButton#btn_run_pipeline {{
    background: #059669;
    color: {WHITE};
    border: none;
    border-radius: 8px;
    padding: 9px 24px;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.2px;
}}
QPushButton#btn_run_pipeline:hover {{
    background: #047857;
}}
QPushButton#btn_run_pipeline:pressed {{
    background: #065F46;
}}
QPushButton#btn_run_pipeline:disabled {{
    background: #6EE7B7;
    color: #ECFDF5;
}}

QPushButton#btn_outline {{
    background: transparent;
    border: 1.5px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 500;
    color: {TEXT_B};
}}
QPushButton#btn_outline:hover {{
    background: {BG_PAGE};
    border-color: #9CA3AF;
    color: {TEXT_H};
}}
QPushButton#btn_outline:pressed {{
    background: #E5E7EB;
}}

/* Run pill buttons */
QPushButton#pill {{
    background: transparent;
    border: 1.5px solid {BORDER};
    border-radius: 14px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: 500;
    color: {TEXT_M};
}}
QPushButton#pill:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
    background: {ACCENT_LIGHT};
}}
QPushButton#pill[active=true] {{
    background: {TEXT_H};
    border-color: {TEXT_H};
    color: {WHITE};
    font-weight: 700;
}}

/* Metric-switch pills */
QPushButton#metric_pill {{
    background: transparent;
    border: 1.5px solid {BORDER};
    border-radius: 14px;
    padding: 3px 10px;
    font-size: 11px;
    color: {TEXT_M};
}}
QPushButton#metric_pill:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton#metric_pill[active=true] {{
    background: {TEXT_H};
    border-color: {TEXT_H};
    color: {WHITE};
    font-weight: 700;
}}

/* ── Tables ── */
QTableWidget {{
    background: {BG_CARD};
    border: none;
    gridline-color: {BORDER};
    font-size: 12px;
    color: {TEXT_B};
    alternate-background-color: #FAFAFA;
}}
QTableWidget::item {{
    padding: 6px 10px;
    border: none;
}}
QTableWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {ACCENT_DARK};
}}
QHeaderView::section {{
    background: {BG_PAGE};
    color: {TEXT_M};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}

/* ── Error / info banners ── */
QFrame#banner_err {{
    background: {DANGER_BG};
    border: 1px solid #FECACA;
    border-radius: 8px;
}}
QFrame#banner_warn {{
    background: {WARN_BG};
    border: 1px solid #FDE68A;
    border-radius: 8px;
}}
QFrame#banner_ok {{
    background: {SUCCESS_BG};
    border: 1px solid #A7F3D0;
    border-radius: 8px;
}}
QLabel#banner_text_err  {{ color: {DANGER_FG}; font-size: 12px; background: transparent; }}
QLabel#banner_text_warn {{ color: {WARN_FG};   font-size: 12px; background: transparent; }}
QLabel#banner_text_ok   {{ color: {SUCCESS_FG};font-size: 12px; background: transparent; }}

/* ── Upload zone ── */
QFrame#upload_zone {{
    background: {ACCENT_LIGHT};
    border: 2px dashed #C7D2FE;
    border-radius: 10px;
}}
QFrame#upload_zone:hover {{
    background: #E0E7FF;
    border-color: {ACCENT};
}}

/* ── Dividers ── */
QFrame#hdivider {{
    background: {BORDER};
    max-height: 1px;
    border: none;
}}
QFrame#vdivider {{
    background: {BORDER};
    max-width: 1px;
    border: none;
}}

/* ── Alzheimer risk number ── */
QLabel#risk_number {{
    font-size: 42px;
    font-weight: 800;
    color: #DC2626;
    background: transparent;
    letter-spacing: -1px;
}}
QLabel#risk_level {{
    font-size: 12px;
    font-weight: 700;
    color: #DC2626;
    background: transparent;
    letter-spacing: 0.5px;
}}
QLabel#conf_number {{
    font-size: 24px;
    font-weight: 800;
    color: {TEXT_H};
    background: transparent;
}}

/* ── Biomarker card ── */
QFrame#bm_card {{
    background: {BG_PAGE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#bm_name  {{ font-size: 12px; color: {TEXT_M}; background: transparent; }}
QLabel#bm_val_low  {{ font-size: 16px; font-weight: 700; color: #DC2626; background: transparent; }}
QLabel#bm_val_high {{ font-size: 16px; font-weight: 700; color: #DC2626; background: transparent; }}
QLabel#bm_val_ok   {{ font-size: 16px; font-weight: 700; color: #065F46; background: transparent; }}
QLabel#bm_ref   {{ font-size: 10px; color: {TEXT_HINT}; background: transparent; }}

/* ── Monospace tree ── */
QLabel#tree_text {{
    font-family: "JetBrains Mono", "Fira Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: {TEXT_B};
    background: transparent;
    line-height: 1.6;
}}
"""