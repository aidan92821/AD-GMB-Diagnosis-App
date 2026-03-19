"""
GutSeq – PDF export service.

Generates a polished, multi-section PDF report from the in-memory
analysis results.  Uses ReportLab Platypus for flowing layout and
a custom canvas hook for consistent headers/footers on every page.

Usage (standalone):
    from services.pdf_exporter import build_report
    build_report("/path/to/output.pdf")
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from reportlab.lib            import colors
from reportlab.lib.enums      import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes  import A4
from reportlab.lib.styles     import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units       import mm, cm
from reportlab.platypus       import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes    import (
    Drawing, Rect, String, Line, Circle, Polygon,
)
from reportlab.graphics             import renderPDF
from reportlab.graphics.charts.barcharts  import VerticalBarChart
from reportlab.graphics.charts.piecharts  import Pie

from models.example_data import (
    PROJECT, GENERA, GENUS_ABUNDANCE, ASV_FEATURES,
    ALPHA_DIVERSITY, BETA_BRAY_CURTIS, BETA_UNIFRAC,
    PCOA_BRAY_CURTIS, ALZHEIMER_RISK,
)

# ── Design tokens (mirrors resources/styles.py) ───────────────────────────────
C_DARK    = colors.HexColor("#111827")
C_BODY    = colors.HexColor("#374151")
C_MUTED   = colors.HexColor("#6B7280")
C_HINT    = colors.HexColor("#9CA3AF")
C_BORDER  = colors.HexColor("#E5E7EB")
C_PAGE    = colors.HexColor("#F4F5F7")
C_WHITE   = colors.white
C_ACCENT  = colors.HexColor("#6366F1")
C_GREEN   = colors.HexColor("#10B981")
C_AMBER   = colors.HexColor("#F59E0B")
C_RED     = colors.HexColor("#EF4444")
C_DANGER  = colors.HexColor("#DC2626")

GENUS_HEX = [
    "#6366F1", "#10B981", "#F59E0B", "#3B82F6", "#EF4444",
    "#8B5CF6", "#14B8A6", "#F97316", "#EC4899", "#84CC16",
]
GENUS_COLORS_RL = [colors.HexColor(h) for h in GENUS_HEX]

W, H = A4   # 595.27 x 841.89 pts


# ── Style sheet ───────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    def s(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    font = "Helvetica"
    fontB = "Helvetica-Bold"

    return {
        "h1": s("h1", fontName=fontB, fontSize=18, textColor=C_DARK,
                spaceAfter=6, leading=22),
        "h2": s("h2", fontName=fontB, fontSize=13, textColor=C_DARK,
                spaceAfter=4, leading=16),
        "h3": s("h3", fontName=fontB, fontSize=11, textColor=C_BODY,
                spaceAfter=3, leading=14),
        "body": s("body", fontName=font, fontSize=10, textColor=C_BODY,
                  leading=14, spaceAfter=4),
        "small": s("small", fontName=font, fontSize=8.5, textColor=C_MUTED,
                   leading=12, spaceAfter=2),
        "hint":  s("hint",  fontName=font, fontSize=8,   textColor=C_HINT,
                   leading=11),
        "badge_green": s("bg", fontName=fontB, fontSize=8, textColor=C_GREEN),
        "badge_red":   s("br", fontName=fontB, fontSize=8, textColor=C_DANGER),
        "badge_ok":    s("bo", fontName=fontB, fontSize=8,
                         textColor=colors.HexColor("#065F46")),
        "disclaimer":  s("disc", fontName=font, fontSize=8, textColor=C_MUTED,
                         leading=12, borderColor=C_BORDER, borderWidth=0.5,
                         borderPadding=6, backColor=C_PAGE, spaceAfter=6),
    }


# ── Header / footer canvas hook ───────────────────────────────────────────────

class _PageDecorator:
    """
    Called by ReportLab on every page.  Draws the dark top bar with
    project title, and a footer with page number + timestamp.
    """

    HEADER_H = 36
    FOOTER_H = 20

    def __init__(self, project_title: str) -> None:
        self._title = project_title

    def __call__(self, canvas, doc) -> None:
        canvas.saveState()
        self._draw_header(canvas, doc)
        self._draw_footer(canvas, doc)
        canvas.restoreState()

    def _draw_header(self, canvas, doc) -> None:
        # Dark bar
        canvas.setFillColor(C_DARK)
        canvas.rect(0, H - self.HEADER_H, W, self.HEADER_H, fill=1, stroke=0)
        # Logo text
        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(20, H - self.HEADER_H + 12, "GutSeq")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#94A3B8"))
        canvas.drawString(72, H - self.HEADER_H + 12, f"  ·  {self._title}")
        # Section label (right aligned)
        canvas.setFillColor(colors.HexColor("#6366F1"))
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(W - 20, H - self.HEADER_H + 12,
                               "Microbiome Analytics Report")

    def _draw_footer(self, canvas, doc) -> None:
        canvas.setFillColor(C_HINT)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(20, 10, f"GutSeq · {PROJECT['bioproject_id']}")
        canvas.drawRightString(
            W - 20, 10, f"Page {doc.page}"
        )
        # Thin top line on footer
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(20, self.FOOTER_H - 4, W - 20, self.FOOTER_H - 4)


# ── Custom flowables ──────────────────────────────────────────────────────────

class SectionDivider(Flowable):
    """A thin full-width rule with a section title on the left."""

    def __init__(self, title: str, color=C_ACCENT) -> None:
        super().__init__()
        self._title = title
        self._color = color
        self.height = 20

    def wrap(self, avail_w, avail_h):
        self.width = avail_w
        return avail_w, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self._color)
        c.rect(0, 8, 4, 10, fill=1, stroke=0)
        c.setFillColor(C_DARK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(10, 8, self._title)
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.4)
        c.line(0, 4, self.width, 4)


class ColorBar(Flowable):
    """Horizontal stacked colour bar for genus composition."""

    def __init__(self, segments: list[tuple[str, float, str]],
                 bar_h: float = 14) -> None:
        """segments: list of (label, value, hex_color)"""
        super().__init__()
        self._segs  = segments
        self._bar_h = bar_h
        self.height = bar_h + 2

    def wrap(self, avail_w, avail_h):
        self.width = avail_w
        return avail_w, self.height

    def draw(self):
        total = sum(v for _, v, _ in self._segs) or 1.0
        x = 0
        for _, val, hex_c in self._segs:
            seg_w = self.width * val / total
            self.canv.setFillColor(colors.HexColor(hex_c))
            self.canv.rect(x, 0, seg_w - 1, self._bar_h, fill=1, stroke=0)
            x += seg_w


class RiskBar(Flowable):
    """Gradient green→amber→red risk meter with a dot marker."""

    HEIGHT = 16

    def __init__(self, pct: float) -> None:
        super().__init__()
        self._pct = pct
        self.height = self.HEIGHT + 4

    def wrap(self, avail_w, avail_h):
        self.width = avail_w
        return avail_w, self.height

    def draw(self):
        c = self.canv
        n = 60   # gradient steps
        for i in range(n):
            t  = i / n
            r_ = int(16  + (239 - 16)  * t)
            g_ = int(185 + (68  - 185) * t)
            b_ = int(129 + (68  - 129) * t)
            col = colors.Color(r_ / 255, g_ / 255, b_ / 255)
            c.setFillColor(col)
            c.rect(self.width * i / n, 4,
                   self.width / n + 1, self.HEIGHT - 4,
                   fill=1, stroke=0)

        # Marker dot
        mx = self.width * self._pct / 100
        c.setFillColor(C_DANGER)
        c.setStrokeColor(C_WHITE)
        c.setLineWidth(1.5)
        c.circle(mx, self.HEIGHT // 2, 5, fill=1, stroke=1)


# ── Chart builders ────────────────────────────────────────────────────────────

def _bar_chart(run: str, width: float = 220, height: float = 110) -> Drawing:
    """Vertical bar chart for genus relative abundance."""
    vals   = GENUS_ABUNDANCE[run]
    genera = [g[:10] for g in GENERA]   # truncate for labels

    d   = Drawing(width, height)
    bc  = VerticalBarChart()
    bc.x           = 30
    bc.y           = 25
    bc.width       = width - 40
    bc.height      = height - 35
    bc.data        = [vals]
    bc.valueAxis.valueMin      = 0
    bc.valueAxis.valueMax      = max(vals) * 1.15
    bc.valueAxis.valueStep     = 5
    bc.valueAxis.labels.fontSize   = 7
    bc.valueAxis.labels.fontName   = "Helvetica"
    bc.categoryAxis.categoryNames  = genera
    bc.categoryAxis.labels.angle   = 35
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.labels.dy      = -12
    bc.bars[0].fillColor  = colors.HexColor(GENUS_HEX[0])
    bc.bars[0].strokeColor = C_WHITE
    bc.bars[0].strokeWidth = 0.3

    # Individual bar colours
    for i in range(len(vals)):
        bc.bars[(0, i)].fillColor = GENUS_COLORS_RL[i % len(GENUS_COLORS_RL)]

    d.add(bc)
    return d


def _pie_chart(run: str, width: float = 130, height: float = 130) -> Drawing:
    """Pie chart for top-5 genera + Other."""
    vals    = GENUS_ABUNDANCE[run]
    top5    = sorted(enumerate(vals), key=lambda x: -x[1])[:5]
    other   = sum(vals) - sum(v for _, v in top5)
    slices  = [(GENERA[i], v) for i, v in top5] + [("Other", other)]

    d = Drawing(width, height)
    pie = Pie()
    pie.x      = 20
    pie.y      = 20
    pie.width  = 90
    pie.height = 90
    pie.data   = [v for _, v in slices]
    pie.labels = None   # labels in legend below

    for i in range(len(slices)):
        pie.slices[i].fillColor    = GENUS_COLORS_RL[i % len(GENUS_COLORS_RL)]
        pie.slices[i].strokeColor  = C_WHITE
        pie.slices[i].strokeWidth  = 0.8

    d.add(pie)
    return d


def _heatmap_drawing(matrix: list[list[float]], labels: list[str],
                     cell: int = 28) -> Drawing:
    """Heatmap grid drawing."""
    n      = len(labels)
    offset = 22
    size   = n * cell + offset + 4

    d = Drawing(size, size)
    fnt = "Helvetica"

    for i, lbl in enumerate(labels):
        d.add(String(offset + i * cell + cell // 2, size - 12,
                     lbl, fontSize=7, fontName=fnt,
                     textAnchor="middle", fillColor=C_MUTED))
        d.add(String(offset - 3, size - offset - i * cell - cell // 2 - 2,
                     lbl, fontSize=7, fontName=fnt,
                     textAnchor="end", fillColor=C_MUTED))

    for row in range(n):
        for col in range(n):
            val = matrix[row][col]
            r_ = int(8   + (236 - 8)   * val)
            g_ = int(128 + (252 - 128) * val)
            b_ = int(128 + (232 - 128) * val)
            fc = colors.Color(r_ / 255, g_ / 255, b_ / 255)
            x  = offset + col * cell
            y  = size - offset - (row + 1) * cell
            d.add(Rect(x, y, cell - 2, cell - 2, fillColor=fc,
                       strokeColor=C_WHITE, strokeWidth=1.5))

    return d


def _pcoa_drawing(coords: dict, run_colors: dict,
                  width: float = 160, height: float = 140) -> Drawing:
    """2D PCoA scatter plot."""
    d = Drawing(width, height)
    pad = 20

    xs = [v[0] for v in coords.values()]
    ys = [v[1] for v in coords.values()]
    x_lo, x_hi = min(xs) - 0.1, max(xs) + 0.1
    y_lo, y_hi = min(ys) - 0.1, max(ys) + 0.1
    x_span = x_hi - x_lo or 1
    y_span = y_hi - y_lo or 1
    cw = width - pad * 2
    ch = height - pad * 2

    def px(v): return pad + cw * (v - x_lo) / x_span
    def py(v): return pad + ch * (v - y_lo) / y_span

    # Axes
    d.add(Line(pad, py(0), width - pad, py(0),
               strokeColor=C_BORDER, strokeWidth=0.5))
    d.add(Line(px(0), pad, px(0), height - pad,
               strokeColor=C_BORDER, strokeWidth=0.5))

    # Cluster ellipses (approximate as large circles)
    for group, gc in [
        (["R1", "R2"], colors.HexColor("#10B98130")),
        (["R3", "R4"], colors.HexColor("#F59E0B30")),
    ]:
        gxs = [px(coords[r][0]) for r in group if r in coords]
        gys = [py(coords[r][1]) for r in group if r in coords]
        if len(gxs) >= 2:
            cx_ = sum(gxs) / len(gxs)
            cy_ = sum(gys) / len(gys)
            rx  = max(abs(gx - cx_) for gx in gxs) + 12
            ry  = max(abs(gy - cy_) for gy in gys) + 12
            # Draw as circle approximation
            d.add(Circle(cx_, cy_, max(rx, ry),
                         fillColor=gc,
                         strokeColor=colors.HexColor(
                             "#10B981" if "R1" in group else "#F59E0B"),
                         strokeWidth=0.7))

    # Points + labels
    for run, (vx, vy_) in coords.items():
        sc_x, sc_y = px(vx), py(vy_)
        col = colors.HexColor(run_colors.get(run, "#6366F1"))
        d.add(Circle(sc_x, sc_y, 4,
                     fillColor=col,
                     strokeColor=C_WHITE, strokeWidth=1))
        d.add(String(sc_x + 6, sc_y - 2, run,
                     fontSize=7, fontName="Helvetica-Bold",
                     fillColor=C_DARK))

    return d


# ── Section builders ──────────────────────────────────────────────────────────

def _section_cover(story: list, st: dict) -> None:
    """Full cover page."""
    story.append(Spacer(1, 60))
    # story.append(Paragraph("GutSeq", ParagraphStyle(
    #     "cover_logo", fontName="Helvetica-Bold", fontSize=32,
    #     textColor=C_ACCENT, spaceAfter=4)))
    story.append(Paragraph("Microbiome Analytics Report", ParagraphStyle(
        "cover_sub", fontName="Helvetica", fontSize=16,
        textColor=C_MUTED, spaceAfter=20)))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 16))

    info_data = [
        ["BioProject ID",  PROJECT["bioproject_id"]],
        ["Project ID",     PROJECT["project_id"]],
        ["Title",          PROJECT["title"]],
        ["Runs",           ", ".join(PROJECT["runs"])],
        ["ASVs",           f"{PROJECT['asv_count']:,}"],
        ["Genera",         str(PROJECT["genus_count"])],
        ["Library",        PROJECT["library"]],
    ]
    tbl = Table(info_data, colWidths=[120, 320])
    tbl.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 10),
        ("TEXTCOLOR",   (0, 0), (0, -1), C_MUTED),
        ("TEXTCOLOR",   (1, 0), (1, -1), C_DARK),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.3, C_BORDER),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "This report contains sequencing data analysis results including "
        "taxonomy classification, alpha/beta diversity metrics, phylogenetic "
        "relationships, and an experimental Alzheimer's disease risk assessment "
        "based on gut-brain axis biomarkers.",
        st["body"]
    ))
    story.append(PageBreak())


def _section_overview(story: list, st: dict) -> None:
    story.append(SectionDivider("Project Overview"))
    story.append(Spacer(1, 8))

    stat_data = [
        ["Metric", "Value", "Notes"],
        ["Project ID",    PROJECT["project_id"],         "Distinct from BioProject ID"],
        ["BioProject ID", PROJECT["bioproject_id"],      "NCBI BioProject accession"],
        ["Total Runs",    str(len(PROJECT["runs"])),     " · ".join(PROJECT["runs"])],
        ["ASVs",          f"{PROJECT['asv_count']:,}",  "Amplicon Sequence Variants"],
        ["Genera",        str(PROJECT["genus_count"]),   "Distinct bacterial genera"],
        ["Library",       PROJECT["library"],            "Sequencing library type"],
        ["Uploaded",
         f"{sum(PROJECT['uploaded'].values())} / {len(PROJECT['runs'])}",
         "R4 pending upload"],
    ]
    tbl = Table(stat_data, colWidths=[130, 110, 220])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",   (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("FONTNAME",    (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",   (0, 1), (0, -1), C_MUTED),
        ("TEXTCOLOR",   (1, 1), (-1, -1), C_DARK),
        ("BACKGROUND",  (0, 1), (-1, -1), C_WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_PAGE]),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID",        (0, 0), (-1, -1), 0.3, C_BORDER),
    ]))
    story.append(tbl)
    story.append(PageBreak())


def _section_taxonomy(story: list, st: dict) -> None:
    story.append(SectionDivider("Taxonomy"))
    story.append(Spacer(1, 6))

    for run in PROJECT["runs"]:
        story.append(KeepTogether([
            Paragraph(f"Run {run}  ({PROJECT['run_accessions'][run]})", st["h2"]),
        ]))

        # Bar chart + pie side by side
        bar = _bar_chart(run, width=310, height=120)
        pie = _pie_chart(run, width=140, height=120)

        chart_row = Table([[bar, pie]], colWidths=[310, 140])
        chart_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(chart_row)

        # Legend
        vals  = GENUS_ABUNDANCE[run]
        total = sum(vals) or 1
        top5  = sorted(enumerate(vals), key=lambda x: -x[1])[:5]
        leg_items = [(GENERA[i], v / total * 100, GENUS_HEX[i]) for i, v in top5]
        leg_items.append(("Other", (total - sum(v for _, v in top5)) / total * 100,
                           "#D1D5DB"))

        leg_data = [[
            Paragraph(f'<font color="{hx}">■</font>  {g}', st["small"]),
            Paragraph(f"{v:.1f}%", st["small"]),
        ] for g, v, hx in leg_items]

        # Two columns of legend
        half = len(leg_data) // 2 + len(leg_data) % 2
        col1 = leg_data[:half]
        col2 = leg_data[half:]
        while len(col2) < len(col1):
            col2.append(["", ""])

        combined = [[c1[0], c1[1], c2[0] if c2 else "", c2[1] if c2 else ""]
                    for c1, c2 in zip(col1, col2)]
        leg_tbl = Table(combined, colWidths=[160, 40, 160, 40])
        leg_tbl.setStyle(TableStyle([
            ("FONTSIZE",    (0, 0), (-1, -1), 8),
            ("TOPPADDING",  (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING",(0,0), (-1,-1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(leg_tbl)

        # Stacked composition bar
        story.append(Spacer(1, 6))
        segs = [(GENERA[i], vals[i], GENUS_HEX[i]) for i in range(len(GENERA))]
        story.append(ColorBar(segs, bar_h=12))
        story.append(Paragraph("← genus composition bar", st["hint"]))
        story.append(Spacer(1, 12))

    story.append(PageBreak())


def _section_diversity(story: list, st: dict) -> None:
    story.append(SectionDivider("Diversity"))
    story.append(Spacer(1, 8))

    # ── Alpha diversity table ──
    story.append(Paragraph("Alpha Diversity", st["h2"]))
    story.append(Paragraph(
        "Shannon index measures species richness and evenness.  "
        "Simpson index measures the probability that two randomly chosen "
        "individuals belong to different species.",
        st["body"]
    ))

    alpha_data = [["Run", "Shannon (median)", "Shannon range",
                   "Simpson (median)", "Simpson range"]]
    for run in PROJECT["runs"]:
        sh = ALPHA_DIVERSITY[run]["shannon"]
        si = ALPHA_DIVERSITY[run]["simpson"]
        alpha_data.append([
            run,
            f"{sh[2]:.2f}",
            f"{sh[0]:.2f} – {sh[4]:.2f}",
            f"{si[2]:.2f}",
            f"{si[0]:.2f} – {si[4]:.2f}",
        ])

    tbl = Table(alpha_data, colWidths=[40, 100, 110, 110, 100])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",   (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_PAGE]),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID",        (0, 0), (-1, -1), 0.3, C_BORDER),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # ── Beta diversity ──
    story.append(Paragraph("Beta Diversity", st["h2"]))
    story.append(Paragraph(
        "Bray-Curtis dissimilarity (0 = identical, 1 = no shared taxa).  "
        "UniFrac additionally weights by phylogenetic distance.",
        st["body"]
    ))

    for metric_label, matrix in [("Bray-Curtis", BETA_BRAY_CURTIS),
                                   ("UniFrac",    BETA_UNIFRAC)]:
        story.append(Paragraph(f"{metric_label} pairwise dissimilarity", st["h3"]))

        runs = PROJECT["runs"]
        header = [""] + runs
        rows   = [header]
        for i, r in enumerate(runs):
            row = [r] + [f"{matrix[i][j]:.2f}" for j in range(len(runs))]
            rows.append(row)

        n_cols = len(runs) + 1
        col_w  = [40] + [70] * len(runs)
        tbl = Table(rows, colWidths=col_w)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), C_DARK),
            ("BACKGROUND",  (0, 0), (0, -1), C_PAGE),
            ("TEXTCOLOR",   (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("ALIGN",       (1, 1), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_PAGE]),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID",        (0, 0), (-1, -1), 0.3, C_BORDER),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8))

    # ── Heatmap (Bray-Curtis) ──
    story.append(Paragraph("Beta diversity heatmap (Bray-Curtis)", st["h3"]))
    hm = _heatmap_drawing(BETA_BRAY_CURTIS, PROJECT["runs"], cell=36)
    story.append(hm)
    story.append(Paragraph(
        "Dark teal = similar communities (low dissimilarity). "
        "Light = dissimilar (high dissimilarity).", st["hint"]
    ))
    story.append(Spacer(1, 10))

    # ── PCoA ──
    story.append(Paragraph("PCoA scatter (Bray-Curtis)", st["h3"]))
    RUN_COLORS = {"R1": "#10B981", "R2": "#6366F1", "R3": "#F59E0B", "R4": "#EF4444"}
    pcoa = _pcoa_drawing(PCOA_BRAY_CURTIS, RUN_COLORS, width=220, height=160)
    story.append(pcoa)
    story.append(Paragraph(
        "Runs that share similar microbiome communities cluster together. "
        "R1+R2 form one cluster; R3+R4 form another.", st["hint"]
    ))
    story.append(PageBreak())


def _section_asv_table(story: list, st: dict) -> None:
    story.append(SectionDivider("ASV Feature Table"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Amplicon Sequence Variants detected per run, ranked by relative abundance.",
        st["body"]
    ))

    for run in PROJECT["runs"]:
        story.append(Paragraph(f"Run {run}", st["h2"]))
        header = ["Feature ID", "Genus", "Count", "Rel. %"]
        rows   = [header]
        for feat in ASV_FEATURES[run]:
            rows.append([
                feat["id"],
                feat["genus"],
                f"{feat['count']:,}",
                f"{feat['pct']:.1f}%",
            ])

        tbl = Table(rows, colWidths=[80, 180, 70, 70])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), C_DARK),
            ("TEXTCOLOR",   (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_PAGE]),
            ("TOPPADDING",  (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("GRID",        (0, 0), (-1, -1), 0.3, C_BORDER),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 10))

    story.append(PageBreak())


def _section_phylogeny(story: list, st: dict) -> None:
    story.append(SectionDivider("Phylogenetic Tree"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Phylogenetic relationships inferred by IQ-TREE from the representative "
        "ASV sequences. Tree topology is consistent across all four runs.",
        st["body"]
    ))

    tree_text = (
        "  ┌─── Bacteroides fragilis\n"
        "──┤  └─── Bacteroides thetaiotaomicron\n"
        "  │\n"
        "  ├─── Prevotella copri\n"
        "  │    └─── Prevotella melaninogenica\n"
        "  │\n"
        "  ├─── Ruminococcus gnavus\n"
        "  │\n"
        "  └─── Faecalibacterium prausnitzii\n"
        "       └─── Roseburia intestinalis"
    )
    mono = ParagraphStyle(
        "mono", fontName="Courier", fontSize=9,
        textColor=C_BODY, leading=14, spaceAfter=4,
        backColor=C_PAGE, borderPadding=10,
        borderColor=C_BORDER, borderWidth=0.5,
    )
    story.append(Spacer(1, 4))
    for line in tree_text.split("\n"):
        story.append(Paragraph(line.replace(" ", "&nbsp;"), mono))

    story.append(PageBreak())


def _section_alzheimer(story: list, st: dict) -> None:
    story.append(SectionDivider("Alzheimer Risk Prediction", color=C_DANGER))
    story.append(Spacer(1, 8))

    d = ALZHEIMER_RISK

    # Big risk number row
    risk_data = [
        [
            Paragraph(f"<b>{d['predicted_pct']:.0f}%</b>", ParagraphStyle(
                "big_risk", fontName="Helvetica-Bold", fontSize=28,
                textColor=C_DANGER, leading=32)),
            Paragraph(
                f"<b>Risk level:</b> {d['risk_level'].capitalize()}<br/>"
                f"<b>Confidence:</b> {d['confidence_pct']:.0f}%<br/>"
                "<font color='#6B7280' size='9'>"
                "Based on gut-brain axis biomarker profile</font>",
                st["body"]
            ),
        ]
    ]
    tbl = Table(risk_data, colWidths=[80, 380])
    tbl.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("BACKGROUND",   (0, 0), (-1, -1), C_PAGE),
        ("BOX",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8))

    # Risk bar
    story.append(Paragraph("Risk spectrum:", st["small"]))
    story.append(RiskBar(d["predicted_pct"]))
    story.append(Paragraph(
        "Low ◄────────────────────────────────────► High", st["hint"]
    ))
    story.append(Spacer(1, 14))

    # Biomarker table
    story.append(Paragraph("Key biomarkers", st["h2"]))

    bm_header = ["Biomarker", "Observed", "Unit", "Normal range",
                 "Role", "Status"]
    bm_rows   = [bm_header]
    for bm in d["biomarkers"]:
        arrow  = {"low": "↓", "high": "↑", "normal": "✓"}.get(bm["status"], "")
        status_col = {
            "low":    colors.HexColor("#DC2626"),
            "high":   colors.HexColor("#DC2626"),
            "normal": colors.HexColor("#065F46"),
        }.get(bm["status"], C_BODY)

        bm_rows.append([
            bm["name"],
            f"{bm['value']:.1f}",
            bm["unit"],
            bm["normal"],
            bm["role"],
            f"{arrow} {bm['status']}",
        ])

    tbl = Table(bm_rows, colWidths=[130, 50, 28, 65, 110, 62])
    style = [
        ("BACKGROUND",   (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_WHITE, C_PAGE]),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",         (0, 0), (-1, -1), 0.3, C_BORDER),
    ]
    # Colour the status column
    for i, bm in enumerate(d["biomarkers"], start=1):
        col = {
            "low":    colors.HexColor("#DC2626"),
            "high":   colors.HexColor("#DC2626"),
            "normal": colors.HexColor("#065F46"),
        }.get(bm["status"], C_BODY)
        style.append(("TEXTCOLOR", (5, i), (5, i), col))
        style.append(("FONTNAME",  (5, i), (5, i), "Helvetica-Bold"))

    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # Disclaimer
    story.append(Paragraph(
        "⚠  DISCLAIMER: This prediction is a research-grade estimate based on "
        "published gut-brain axis literature. It is NOT a clinical diagnosis. "
        "Biomarker thresholds are derived from population studies and may not "
        "apply to individual cases. Consult a qualified physician for any clinical "
        "assessment or medical decision.",
        st["disclaimer"]
    ))


# ── Public API ────────────────────────────────────────────────────────────────

def build_report(output_path: str | Path) -> Path:
    """
    Generate the full GutSeq PDF report.

    Parameters
    ----------
    output_path : destination file path (str or Path)

    Returns
    -------
    Path to the written PDF file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    decorator = _PageDecorator(
        f"{PROJECT['project_id']} — {PROJECT['title']}"
    )

    # Page frame: leave room for header (36pt) and footer (24pt)
    frame = Frame(
        15 * mm, 12 * mm,
        W - 30 * mm, H - 36 - 24,
        id="main"
    )
    template = PageTemplate(id="main", frames=[frame],
                            onPage=decorator)

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        pageTemplates=[template],
        title=f"GutSeq Report — {PROJECT['project_id']}",
        author="GutSeq Analytics",
        subject="Microbiome Analysis Report",
        leftMargin=0, rightMargin=0,
        topMargin=0,  bottomMargin=0,
    )

    st    = _styles()
    story: list[Any] = []

    _section_cover(story, st)
    _section_overview(story, st)
    _section_taxonomy(story, st)
    _section_diversity(story, st)
    _section_asv_table(story, st)
    _section_phylogeny(story, st)
    _section_alzheimer(story, st)

    doc.build(story)
    return output_path