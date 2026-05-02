"""
Axis – PDF export service.

Generates a polished, multi-section PDF report from the in-memory
analysis results.  Uses ReportLab Platypus for flowing layout and
a custom canvas hook for consistent headers/footers on every page.

Usage (standalone):
    from services.pdf_exporter import build_report
    build_report("/path/to/output.pdf")
"""

from __future__ import annotations

import io
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
    Image as RLImage,
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes    import (
    Drawing, Rect, String, Line, Circle, Polygon,
)
from reportlab.graphics             import renderPDF
from reportlab.graphics.charts.barcharts  import VerticalBarChart
from reportlab.graphics.charts.piecharts  import Pie

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


# ── Matplotlib helpers ────────────────────────────────────────────────────────

def _fig_to_rl_image(fig, width_pt: float, height_pt: float) -> RLImage:
    """Render a matplotlib Figure to a ReportLab Image flowable."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    return RLImage(buf, width=width_pt, height=height_pt)


def _render_phylo_figure(newick: str, max_tips: int = 60):
    """
    Render a newick tree using Bio.Phylo + matplotlib.
    Returns a matplotlib Figure, or None on failure.
    """
    try:
        from Bio import Phylo as BP
        from matplotlib.figure import Figure as MFig
        from io import StringIO

        tree = BP.read(StringIO(newick), "newick")
        tips = tree.get_terminals()
        n    = len(tips)

        # Subsample large trees
        if n > max_tips:
            keep = set(tips[i] for i in range(0, n, max(1, n // max_tips)))
            tree.prune([t for t in tips if t not in keep])
            tips = tree.get_terminals()
            n    = len(tips)

        fig_h = max(min(n * 0.20, 22), 5)
        fig   = MFig(figsize=(9, fig_h))
        ax    = fig.add_subplot(111)
        BP.draw(tree, axes=ax, do_show=False)
        ax.set_facecolor("#F8FAFC")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        return fig
    except Exception:
        return None


_BUTYRATE_SIM = {"Faecalibacterium", "Roseburia", "Blautia", "Eubacterium",
                 "Butyrivibrio", "Anaerostipes", "Subdoligranulum"}
_PROBIOTIC_SIM = {"Bifidobacterium", "Lactobacillus", "Lactococcus"}
_INFLAM_SIM    = {"Fusobacterium", "Escherichia", "Klebsiella", "Enterococcus",
                  "Sutterella"}


def _run_simulation_model(genus_abundances: dict[str, float], params: dict) -> dict:
    """
    Run the 30-day COMETS-inspired ODE model.
    Returns arrays needed to build plots and the species-change table.
    """
    import numpy as np

    antibiotic = params.get("antibiotic", 0)  / 100.0
    probiotic  = params.get("probiotic",  30) / 100.0
    fiber      = params.get("fiber",      50) / 100.0
    processed  = params.get("processed",  20) / 100.0

    genera  = list(genus_abundances.keys())
    init_ab = np.array(list(genus_abundances.values()), dtype=float)
    total   = init_ab.sum()
    if total > 0:
        init_ab /= total

    is_but  = np.array([g in _BUTYRATE_SIM  for g in genera], dtype=float)
    is_pro  = np.array([g in _PROBIOTIC_SIM for g in genera], dtype=float)
    is_inf  = np.array([g in _INFLAM_SIM    for g in genera], dtype=float)

    T       = 30
    history = np.zeros((T, len(genera)))
    history[0] = init_ab.copy()

    for t in range(1, T):
        prev   = history[t - 1].copy()
        kill   = antibiotic * np.exp(-0.12 * t) * 0.9
        delta  = -kill * prev
        delta += probiotic * 0.018 * is_pro
        delta += fiber     * 0.014 * is_but
        delta += processed * 0.012 * is_inf
        delta -= processed * 0.010 * is_but
        new    = np.clip(prev + delta, 1e-7, None)
        new   /= new.sum()
        history[t] = new

    def _sh(ab):
        p = ab[ab > 0]
        return float(-np.sum(p * np.log2(p)))

    times    = np.arange(T)
    diversity= np.array([_sh(history[t]) for t in range(T)])
    butyrate = np.array([(history[t] * is_but).sum() for t in range(T)])
    inflam   = np.array([(history[t] * is_inf).sum() for t in range(T)])
    max_sh   = math.log2(len(genera)) if len(genera) > 1 else 1.0
    ad_risk  = 100.0 * (
        0.35 * np.clip(inflam    / max(float(inflam.max()),   1e-9), 0, 1) +
        0.30 * np.clip(1 - diversity / max_sh,                      0, 1) +
        0.35 * np.clip(1 - butyrate / max(float(butyrate.max()), 1e-9), 0, 1)
    )
    return {
        "genera": genera, "times": times, "history": history,
        "init_ab": init_ab, "diversity": diversity,
        "butyrate": butyrate, "inflam": inflam, "ad_risk": ad_risk,
        "params": params,
    }


# ── Data layer ────────────────────────────────────────────────────────────────

def _build_report_data(state) -> dict:
    """
    Build a normalised data dict for all report sections.
    Uses real AppState data where available, falls back to example data.
    """
    from models.example_data import (
        PROJECT as EX_PROJECT, GENERA as EX_GENERA,
        GENUS_ABUNDANCE as EX_ABUNDANCE, ASV_FEATURES as EX_ASV,
        ALPHA_DIVERSITY as EX_ALPHA, BETA_BRAY_CURTIS as EX_BC,
        BETA_UNIFRAC as EX_UF, PCOA_BRAY_CURTIS as EX_PCOA,
        ALZHEIMER_RISK as EX_AD,
    )

    if state is None or not getattr(state, "has_project", False):
        return {
            "project":          EX_PROJECT,
            "genera":           EX_GENERA,
            "genus_abundance":  EX_ABUNDANCE,
            "asv_features":     EX_ASV,
            "alpha_diversity":  EX_ALPHA,
            "beta_bray_curtis": EX_BC,
            "beta_unifrac":     EX_UF,
            "pcoa_bray_curtis": EX_PCOA,
            "alzheimer_risk":   EX_AD,
            "phylo_newick":     "",
            "simulation_data":  None,
        }

    # ── Project ──────────────────────────────────────────────────────────────
    p = state.to_project_dict()
    project = {
        "bioproject_id":  p["bioproject_id"],
        "project_id":     p.get("project_uid") or p["bioproject_id"],
        "title":          p["title"],
        "runs":           p["runs"],
        "run_accessions": p.get("run_accessions", {}),
        "asv_count":      p["asv_count"],
        "genus_count":    p["genus_count"],
        "library":        p["library"],
        "uploaded":       p.get("uploaded", {}),
        "qiime_errors":   p.get("qiime_errors", {}),
    }

    # ── Genus / taxonomy ─────────────────────────────────────────────────────
    genera = EX_GENERA
    genus_abundance = dict(EX_ABUNDANCE)

    if state.genus_abundances:
        all_genera: list[str] = []
        for run_data in state.genus_abundances.values():
            for item in run_data:
                g = item["genus"] if isinstance(item, dict) else item[0]
                if g not in all_genera:
                    all_genera.append(g)
        if all_genera:
            genera = all_genera[:10]
            genus_abundance = {}
            for run_label, run_data in state.genus_abundances.items():
                genus_dict: dict[str, float] = {}
                for item in run_data:
                    g = item["genus"] if isinstance(item, dict) else item[0]
                    v = float(
                        item["relative_abundance"] if isinstance(item, dict) else item[1]
                    )
                    genus_dict[g] = v * 100 if v <= 1.0 else v  # normalise to %
                genus_abundance[run_label] = [genus_dict.get(g, 0.0) for g in genera]

    # Fill any missing run label from example fallback
    for run in project["runs"]:
        if run not in genus_abundance:
            genus_abundance[run] = EX_ABUNDANCE.get(run, [0.0] * len(genera))

    # ── ASV features ─────────────────────────────────────────────────────────
    asv_features = EX_ASV
    if getattr(state, "asv_features", None):
        asv_features = state.asv_features

    # ── Alpha diversity ───────────────────────────────────────────────────────
    alpha_diversity = dict(EX_ALPHA)
    if getattr(state, "alpha_diversity", None):
        alpha_diversity = dict(state.alpha_diversity)
        ex_fallback = (3.0, 3.2, 3.4, 3.6, 3.9)
        si_fallback = (0.80, 0.85, 0.88, 0.91, 0.95)
        for run in project["runs"]:
            if run not in alpha_diversity:
                alpha_diversity[run] = EX_ALPHA.get(
                    run, {"shannon": ex_fallback, "simpson": si_fallback}
                )

    # ── Beta / PCoA (not yet in AppState — always use example) ───────────────
    beta_bc = EX_BC
    beta_uf = EX_UF
    pcoa_bc = EX_PCOA

    # ── Alzheimer risk ────────────────────────────────────────────────────────
    alzheimer_risk = EX_AD
    if getattr(state, "risk_result", None):
        r = state.risk_result
        alzheimer_risk = {
            "predicted_pct":  float(r.get("predicted_pct", 0.0)),
            "confidence_pct": float(r.get("confidence_pct", 0.0)),
            "risk_level":     r.get("risk_level", "unknown"),
            "biomarkers":     r.get("biomarkers", []),
        }

    # ── Phylogeny newick ──────────────────────────────────────────────────────
    phylo_newick = ""
    if getattr(state, "db_project_id", None):
        try:
            from services.assessment_service import get_tree
            info = get_tree(state.db_project_id)
            phylo_newick = info.get("newick_string", "")
        except Exception:
            pass
    if not phylo_newick and getattr(state, "bioproject_id", None):
        base = Path(__file__).parent.parent / "pipeline" / "data"
        for layout in ("single", "paired"):
            p = base / state.bioproject_id / "reps-tree" / layout / "tree.nwk"
            if p.exists():
                phylo_newick = p.read_text().strip()
                break

    # ── Simulation (pre-run with default params) ──────────────────────────────
    simulation_data = None
    if state.genus_abundances:
        genus_avg: dict[str, float] = {}
        run_count = len(state.genus_abundances)
        for run_data in state.genus_abundances.values():
            for item in run_data:
                g = item["genus"] if isinstance(item, dict) else item[0]
                v = float(item["relative_abundance"] if isinstance(item, dict) else item[1])
                genus_avg[g] = genus_avg.get(g, 0.0) + v / run_count
        if genus_avg:
            try:
                simulation_data = _run_simulation_model(
                    genus_avg,
                    {"antibiotic": 0, "probiotic": 30, "fiber": 50, "processed": 20},
                )
            except Exception:
                pass

    return {
        "project":          project,
        "genera":           genera,
        "genus_abundance":  genus_abundance,
        "asv_features":     asv_features,
        "alpha_diversity":  alpha_diversity,
        "beta_bray_curtis": beta_bc,
        "beta_unifrac":     beta_uf,
        "pcoa_bray_curtis": pcoa_bc,
        "alzheimer_risk":   alzheimer_risk,
        "phylo_newick":     phylo_newick,
        "simulation_data":  simulation_data,
    }


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
    """Draws the dark top bar and page-number footer on every page."""

    HEADER_H = 36
    FOOTER_H = 20

    def __init__(self, project_title: str, bioproject_id: str) -> None:
        self._title         = project_title
        self._bioproject_id = bioproject_id

    def __call__(self, canvas, doc) -> None:
        canvas.saveState()
        self._draw_header(canvas, doc)
        self._draw_footer(canvas, doc)
        canvas.restoreState()

    def _draw_header(self, canvas, doc) -> None:
        canvas.setFillColor(C_DARK)
        canvas.rect(0, H - self.HEADER_H, W, self.HEADER_H, fill=1, stroke=0)
        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(20, H - self.HEADER_H + 12, "Axis")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#94A3B8"))
        canvas.drawString(72, H - self.HEADER_H + 12, f"  ·  {self._title}")
        canvas.setFillColor(colors.HexColor("#6366F1"))
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(W - 20, H - self.HEADER_H + 12,
                               "Microbiome Analytics Report")

    def _draw_footer(self, canvas, doc) -> None:
        canvas.setFillColor(C_HINT)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(20, 10, f"Axis · {self._bioproject_id}")
        canvas.drawRightString(W - 20, 10, f"Page {doc.page}")
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
        n = 60
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
        mx = self.width * self._pct / 100
        c.setFillColor(C_DANGER)
        c.setStrokeColor(C_WHITE)
        c.setLineWidth(1.5)
        c.circle(mx, self.HEIGHT // 2, 5, fill=1, stroke=1)


# ── Chart builders ────────────────────────────────────────────────────────────

def _bar_chart(run: str, genera: list[str], genus_abundance: dict[str, list],
               width: float = 220, height: float = 110) -> Drawing:
    vals        = genus_abundance.get(run, [0.0] * len(genera))
    genera_lbl  = [g[:10] for g in genera]

    d  = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x           = 30
    bc.y           = 25
    bc.width       = width - 40
    bc.height      = height - 35
    bc.data        = [vals]
    bc.valueAxis.valueMin      = 0
    bc.valueAxis.valueMax      = (max(vals) * 1.15) if vals else 1
    bc.valueAxis.valueStep     = 5
    bc.valueAxis.labels.fontSize   = 7
    bc.valueAxis.labels.fontName   = "Helvetica"
    bc.categoryAxis.categoryNames  = genera_lbl
    bc.categoryAxis.labels.angle   = 35
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.labels.dy      = -12
    bc.bars[0].fillColor  = colors.HexColor(GENUS_HEX[0])
    bc.bars[0].strokeColor = C_WHITE
    bc.bars[0].strokeWidth = 0.3

    for i in range(len(vals)):
        bc.bars[(0, i)].fillColor = GENUS_COLORS_RL[i % len(GENUS_COLORS_RL)]

    d.add(bc)
    return d


def _pie_chart(run: str, genera: list[str], genus_abundance: dict[str, list],
               width: float = 130, height: float = 130) -> Drawing:
    vals   = genus_abundance.get(run, [0.0] * len(genera))
    top5   = sorted(enumerate(vals), key=lambda x: -x[1])[:5]
    other  = sum(vals) - sum(v for _, v in top5)
    slices = [(genera[i], v) for i, v in top5] + [("Other", max(other, 0))]

    d = Drawing(width, height)
    pie = Pie()
    pie.x      = 20
    pie.y      = 20
    pie.width  = 90
    pie.height = 90
    pie.data   = [v for _, v in slices]
    pie.labels = None

    for i in range(len(slices)):
        pie.slices[i].fillColor    = GENUS_COLORS_RL[i % len(GENUS_COLORS_RL)]
        pie.slices[i].strokeColor  = C_WHITE
        pie.slices[i].strokeWidth  = 0.8

    d.add(pie)
    return d


def _heatmap_drawing(matrix: list[list[float]], labels: list[str],
                     cell: int = 28) -> Drawing:
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

    d.add(Line(pad, py(0), width - pad, py(0),
               strokeColor=C_BORDER, strokeWidth=0.5))
    d.add(Line(px(0), pad, px(0), height - pad,
               strokeColor=C_BORDER, strokeWidth=0.5))

    runs_list = list(coords.keys())
    groups = [runs_list[:len(runs_list)//2], runs_list[len(runs_list)//2:]]
    group_colors = [colors.HexColor("#10B98130"), colors.HexColor("#F59E0B30")]
    group_stroke = ["#10B981", "#F59E0B"]

    for idx, group in enumerate(groups):
        gxs = [px(coords[r][0]) for r in group if r in coords]
        gys = [py(coords[r][1]) for r in group if r in coords]
        if len(gxs) >= 2:
            cx_ = sum(gxs) / len(gxs)
            cy_ = sum(gys) / len(gys)
            rx  = max(abs(gx - cx_) for gx in gxs) + 12
            ry  = max(abs(gy - cy_) for gy in gys) + 12
            d.add(Circle(cx_, cy_, max(rx, ry),
                         fillColor=group_colors[idx],
                         strokeColor=colors.HexColor(group_stroke[idx]),
                         strokeWidth=0.7))

    for run, (vx, vy_) in coords.items():
        sc_x, sc_y = px(vx), py(vy_)
        col = colors.HexColor(run_colors.get(run, "#6366F1"))
        d.add(Circle(sc_x, sc_y, 4, fillColor=col,
                     strokeColor=C_WHITE, strokeWidth=1))
        d.add(String(sc_x + 6, sc_y - 2, run,
                     fontSize=7, fontName="Helvetica-Bold", fillColor=C_DARK))

    return d


# ── Section builders ──────────────────────────────────────────────────────────

def _section_cover(story: list, st: dict, data: dict) -> None:
    project = data["project"]
    story.append(Spacer(1, 60))
    story.append(Paragraph("Microbiome Analytics Report", ParagraphStyle(
        "cover_sub", fontName="Helvetica", fontSize=16,
        textColor=C_MUTED, spaceAfter=20)))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 16))

    runs = project.get("runs", [])
    uploaded = project.get("uploaded", {})
    uploaded_str = f"{sum(1 for v in uploaded.values() if v)} / {len(runs)}"

    info_data = [
        ["BioProject ID",  project.get("bioproject_id", "—")],
        ["Project ID",     project.get("project_id", "—")],
        ["Title",          project.get("title", "—")],
        ["Runs",           ", ".join(runs)],
        ["ASVs",           f"{project.get('asv_count', 0):,}"],
        ["Genera",         str(project.get("genus_count", 0))],
        ["Library",        project.get("library", "—")],
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


def _section_overview(story: list, st: dict, data: dict) -> None:
    project = data["project"]
    runs    = project.get("runs", [])
    uploaded = project.get("uploaded", {})

    story.append(SectionDivider("Project Overview"))
    story.append(Spacer(1, 8))

    uploaded_count = sum(1 for v in uploaded.values() if v)
    stat_data = [
        ["Metric", "Value", "Notes"],
        ["Project ID",    project.get("project_id", "—"),       "Distinct from BioProject ID"],
        ["BioProject ID", project.get("bioproject_id", "—"),    "NCBI BioProject accession"],
        ["Total Runs",    str(len(runs)),                        " · ".join(runs)],
        ["ASVs",          f"{project.get('asv_count', 0):,}",   "Amplicon Sequence Variants"],
        ["Genera",        str(project.get("genus_count", 0)),   "Distinct bacterial genera"],
        ["Library",       project.get("library", "—"),          "Sequencing library type"],
        ["Uploaded",      f"{uploaded_count} / {len(runs)}",    "Runs with FASTQ uploaded"],
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


def _section_taxonomy(story: list, st: dict, data: dict) -> None:
    project        = data["project"]
    genera         = data["genera"]
    genus_abundance = data["genus_abundance"]
    runs           = project.get("runs", [])
    run_accessions = project.get("run_accessions", {})

    story.append(SectionDivider("Taxonomy"))
    story.append(Spacer(1, 6))

    for run in runs:
        acc = run_accessions.get(run, run)
        story.append(KeepTogether([
            Paragraph(f"Run {run}  ({acc})", st["h2"]),
        ]))

        bar = _bar_chart(run, genera, genus_abundance, width=310, height=120)
        pie = _pie_chart(run, genera, genus_abundance, width=140, height=120)

        chart_row = Table([[bar, pie]], colWidths=[310, 140])
        chart_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(chart_row)

        vals  = genus_abundance.get(run, [0.0] * len(genera))
        total = sum(vals) or 1
        top5  = sorted(enumerate(vals), key=lambda x: -x[1])[:5]
        leg_items = [(genera[i], v / total * 100, GENUS_HEX[i]) for i, v in top5]
        leg_items.append(("Other", max(0, (total - sum(v for _, v in top5))) / total * 100,
                           "#D1D5DB"))

        leg_data = [[
            Paragraph(f'<font color="{hx}">■</font>  {g}', st["small"]),
            Paragraph(f"{v:.1f}%", st["small"]),
        ] for g, v, hx in leg_items]

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

        story.append(Spacer(1, 6))
        segs = [(genera[i], vals[i], GENUS_HEX[i % len(GENUS_HEX)])
                for i in range(len(genera))]
        story.append(ColorBar(segs, bar_h=12))
        story.append(Paragraph("← genus composition bar", st["hint"]))
        story.append(Spacer(1, 12))

    story.append(PageBreak())


def _section_diversity(story: list, st: dict, data: dict) -> None:
    project         = data["project"]
    alpha_diversity = data["alpha_diversity"]
    beta_bc         = data["beta_bray_curtis"]
    beta_uf         = data["beta_unifrac"]
    pcoa_bc         = data["pcoa_bray_curtis"]
    runs            = project.get("runs", [])

    story.append(SectionDivider("Diversity"))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Alpha Diversity", st["h2"]))
    story.append(Paragraph(
        "Shannon index measures species richness and evenness.  "
        "Simpson index measures the probability that two randomly chosen "
        "individuals belong to different species.",
        st["body"]
    ))

    alpha_data = [["Run", "Shannon (median)", "Shannon range",
                   "Simpson (median)", "Simpson range"]]
    for run in runs:
        ad = alpha_diversity.get(run, {})
        sh = ad.get("shannon", (0, 0, 0, 0, 0))
        si = ad.get("simpson", (0, 0, 0, 0, 0))
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

    story.append(Paragraph("Beta Diversity", st["h2"]))
    story.append(Paragraph(
        "Bray-Curtis dissimilarity (0 = identical, 1 = no shared taxa).  "
        "UniFrac additionally weights by phylogenetic distance.",
        st["body"]
    ))

    for metric_label, matrix in [("Bray-Curtis", beta_bc), ("UniFrac", beta_uf)]:
        n = len(runs)
        if not matrix or len(matrix) < n:
            continue
        story.append(Paragraph(f"{metric_label} pairwise dissimilarity", st["h3"]))

        header = [""] + runs
        rows   = [header]
        for i, r in enumerate(runs):
            if i >= len(matrix):
                break
            row = [r] + [f"{matrix[i][j]:.2f}" if j < len(matrix[i]) else "—"
                          for j in range(n)]
            rows.append(row)

        col_w = [40] + [70] * n
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

    if beta_bc and len(beta_bc) >= len(runs):
        story.append(Paragraph("Beta diversity heatmap (Bray-Curtis)", st["h3"]))
        hm = _heatmap_drawing(beta_bc, runs, cell=36)
        story.append(hm)
        story.append(Paragraph(
            "Dark teal = similar communities (low dissimilarity). "
            "Light = dissimilar (high dissimilarity).", st["hint"]
        ))
        story.append(Spacer(1, 10))

    if pcoa_bc and len(pcoa_bc) >= 2:
        story.append(Paragraph("PCoA scatter (Bray-Curtis)", st["h3"]))
        palette = ["#10B981", "#6366F1", "#F59E0B", "#EF4444",
                   "#8B5CF6", "#14B8A6", "#F97316", "#EC4899"]
        run_colors = {r: palette[i % len(palette)] for i, r in enumerate(runs)}
        pcoa = _pcoa_drawing(pcoa_bc, run_colors, width=220, height=160)
        story.append(pcoa)
        story.append(Paragraph(
            "Runs that share similar microbiome communities cluster together.",
            st["hint"]
        ))
    story.append(PageBreak())


def _section_asv_table(story: list, st: dict, data: dict) -> None:
    project      = data["project"]
    asv_features = data["asv_features"]
    runs         = project.get("runs", [])

    story.append(SectionDivider("ASV Feature Table"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Amplicon Sequence Variants detected per run, ranked by relative abundance.",
        st["body"]
    ))

    for run in runs:
        story.append(Paragraph(f"Run {run}", st["h2"]))
        feats = asv_features.get(run, [])
        if not feats:
            story.append(Paragraph("No ASV data available for this run.", st["small"]))
            story.append(Spacer(1, 8))
            continue

        header = ["Feature ID", "Genus", "Count", "Rel. %"]
        rows   = [header]
        for feat in feats:
            try:
                rows.append([
                    str(feat.get("id", "—")),
                    str(feat.get("genus", "—")),
                    f"{int(feat.get('count', 0)):,}",
                    f"{float(feat.get('pct', 0)):.1f}%",
                ])
            except (TypeError, ValueError):
                continue

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


def _section_phylogeny(story: list, st: dict, data: dict) -> None:
    newick  = data.get("phylo_newick", "")
    project = data["project"]

    story.append(SectionDivider("Phylogenetic Tree"))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Phylogenetic relationships inferred by IQ-TREE from the representative "
        "ASV sequences for project "
        f"{project.get('bioproject_id', '')}.",
        st["body"]
    ))

    FRAME_W = W - 30 * mm   # usable frame width in points

    if newick:
        # ── Try to render real tree with Bio.Phylo ────────────────────────────
        try:
            from Bio import Phylo as BP
            from io import StringIO

            tree      = BP.read(StringIO(newick), "newick")
            tips      = tree.get_terminals()
            n_tips    = len(tips)
            n_int     = len(tree.get_nonterminals())

            # Collect branch lengths for depth stat
            branch_lengths = [c.branch_length or 0.0
                              for c in tree.find_clades() if c.branch_length]
            max_depth = sum(sorted(branch_lengths, reverse=True)[:20])
        except Exception:
            n_tips = n_int = 0
            max_depth = 0.0

        # Stats row
        stats_data = [
            ["Total Tips", "Internal Nodes", "Max Branch Depth"],
            [
                f"{n_tips:,}" if n_tips else "—",
                f"{n_int:,}"  if n_int  else "—",
                f"{max_depth:.4f}" if max_depth else "—",
            ],
        ]
        stat_tbl = Table(stats_data, colWidths=[FRAME_W / 3] * 3)
        stat_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), C_DARK),
            ("TEXTCOLOR",    (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
            ("TEXTCOLOR",    (0, 1), (-1, 1), C_ACCENT),
            ("FONTSIZE",     (0, 1), (-1, 1), 14),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("GRID",         (0, 0), (-1, -1), 0.3, C_BORDER),
        ]))
        story.append(stat_tbl)
        story.append(Spacer(1, 10))

        # Render tree figure
        fig = _render_phylo_figure(newick, max_tips=60)
        if fig:
            img_h = min(max(n_tips * 12, 200), 560)
            story.append(_fig_to_rl_image(fig, FRAME_W, img_h))
            story.append(Paragraph(
                "Rectangular phylogram · branch lengths represent estimated "
                "evolutionary distance from IQ-TREE.",
                st["hint"]
            ))
        else:
            story.append(Paragraph(
                "Could not render tree figure (Bio.Phylo unavailable). "
                "See raw newick string below.",
                st["small"]
            ))
            mono = ParagraphStyle(
                "mono2", fontName="Courier", fontSize=7,
                textColor=C_BODY, leading=10, spaceAfter=2,
                backColor=C_PAGE, borderPadding=6,
                borderColor=C_BORDER, borderWidth=0.5,
            )
            snippet = newick[:800] + ("…" if len(newick) > 800 else "")
            story.append(Paragraph(snippet, mono))

    else:
        # ── No newick: static representative tree ─────────────────────────────
        story.append(Paragraph(
            "No phylogenetic tree found for this project. "
            "Run the QIIME2 pipeline to generate one. "
            "The representative topology below is shown for illustration.",
            st["small"]
        ))
        story.append(Spacer(1, 6))

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
        for line in tree_text.split("\n"):
            story.append(Paragraph(line.replace(" ", "&nbsp;"), mono))

    story.append(PageBreak())


def _section_alzheimer(story: list, st: dict, data: dict) -> None:
    d = data["alzheimer_risk"]

    story.append(SectionDivider("Alzheimer Risk Prediction", color=C_DANGER))
    story.append(Spacer(1, 8))

    predicted_pct  = float(d.get("predicted_pct", 0.0))
    confidence_pct = float(d.get("confidence_pct", 0.0))
    risk_level     = str(d.get("risk_level", "unknown"))
    biomarkers     = d.get("biomarkers", [])

    risk_data = [[
        Paragraph(f"<b>{predicted_pct:.0f}%</b>", ParagraphStyle(
            "big_risk", fontName="Helvetica-Bold", fontSize=28,
            textColor=C_DANGER, leading=32)),
        Paragraph(
            f"<b>Risk level:</b> {risk_level.capitalize()}<br/>"
            f"<b>Confidence:</b> {confidence_pct:.0f}%<br/>"
            "<font color='#6B7280' size='9'>"
            "Based on gut-brain axis biomarker profile</font>",
            st["body"]
        ),
    ]]
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

    story.append(Paragraph("Risk spectrum:", st["small"]))
    story.append(RiskBar(predicted_pct))
    story.append(Paragraph(
        "Low ◄────────────────────────────────────► High", st["hint"]
    ))
    story.append(Spacer(1, 14))

    if biomarkers:
        story.append(Paragraph("Key biomarkers", st["h2"]))

        bm_header = ["Biomarker", "Observed", "Unit", "Normal range", "Role", "Status"]
        bm_rows   = [bm_header]
        for bm in biomarkers:
            arrow  = {"low": "↓", "high": "↑", "normal": "✓"}.get(bm.get("status", ""), "")
            try:
                val_str = f"{float(bm.get('value', 0)):.1f}"
            except (TypeError, ValueError):
                val_str = str(bm.get("value", "—"))

            bm_rows.append([
                str(bm.get("name", "—")),
                val_str,
                str(bm.get("unit", "")),
                str(bm.get("normal", "—")),
                str(bm.get("role", "—")),
                f"{arrow} {bm.get('status', '—')}",
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
        for i, bm in enumerate(biomarkers, start=1):
            col = {
                "low":    colors.HexColor("#DC2626"),
                "high":   colors.HexColor("#DC2626"),
                "normal": colors.HexColor("#065F46"),
            }.get(bm.get("status", ""), C_BODY)
            style.append(("TEXTCOLOR", (5, i), (5, i), col))
            style.append(("FONTNAME",  (5, i), (5, i), "Helvetica-Bold"))

        tbl.setStyle(TableStyle(style))
        story.append(tbl)
        story.append(Spacer(1, 14))

    story.append(Paragraph(
        "⚠  DISCLAIMER: This prediction is a research-grade estimate based on "
        "published gut-brain axis literature. It is NOT a clinical diagnosis. "
        "Biomarker thresholds are derived from population studies and may not "
        "apply to individual cases. Consult a qualified physician for any clinical "
        "assessment or medical decision.",
        st["disclaimer"]
    ))


def _section_simulation(story: list, st: dict, data: dict) -> None:
    from matplotlib.figure import Figure as MFig

    FRAME_W  = W - 30 * mm   # usable frame width in points
    FULL_H   = 160            # tall full-width chart
    THIRD_W  = FRAME_W / 3
    THIRD_H  = 130            # short side-by-side charts

    COLORS = ["#6366F1", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4"]

    story.append(SectionDivider("Gut Microbiome Simulation", color=C_GREEN))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "COMETS-inspired 30-day dynamic ODE model. "
        "Dietary and microbiome interventions (default: Probiotic 30 %, "
        "Dietary Fiber 50 %, Processed Food 20 %, Antibiotic 0 %) are "
        "applied to the project's genus abundance profile to project "
        "community trajectory and predicted AD-risk trend.",
        st["body"]
    ))
    story.append(Spacer(1, 8))

    sim = data.get("simulation_data")
    if sim is None or not sim.get("genera"):
        story.append(Paragraph(
            "Simulation unavailable — no genus abundance data found. "
            "Load a project and complete the QIIME2 pipeline first.",
            st["small"]
        ))
        story.append(PageBreak())
        return

    genera   = sim["genera"]
    times    = sim["times"]
    history  = sim["history"]
    init_ab  = sim["init_ab"]
    diversity= sim["diversity"]
    butyrate = sim["butyrate"]
    inflam   = sim["inflam"]
    ad_risk  = sim["ad_risk"]

    top_n   = min(6, len(genera))
    top_idx = sorted(range(len(genera)), key=lambda i: -init_ab[i])[:top_n]

    # ── Intervention summary table ────────────────────────────────────────────
    params = sim.get("params", {})
    int_data = [
        ["Intervention",   "Level", "Effect"],
        ["Antibiotic",     f"{params.get('antibiotic', 0)} %",
         "Broad-spectrum kill (decays over time)"],
        ["Probiotic",      f"{params.get('probiotic', 30)} %",
         "Boosts Bifidobacterium, Lactobacillus, Lactococcus"],
        ["Dietary Fiber",  f"{params.get('fiber', 50)} %",
         "Feeds butyrate producers (Faecalibacterium, Roseburia…)"],
        ["Processed Food", f"{params.get('processed', 20)} %",
         "Promotes Fusobacterium, Klebsiella; starves SCFA producers"],
    ]
    int_tbl = Table(int_data, colWidths=[120, 60, FRAME_W - 180])
    int_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_WHITE, C_PAGE]),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",         (0, 0), (-1, -1), 0.3, C_BORDER),
    ]))
    story.append(int_tbl)
    story.append(Spacer(1, 10))

    # ── Plot 1: Top-genus abundance over time (full width) ────────────────────
    fig1 = MFig(figsize=(9, 2.8))
    ax1  = fig1.add_subplot(111)
    for k, i in enumerate(top_idx):
        ax1.plot(times, history[:, i] * 100,
                 label=genera[i], color=COLORS[k % len(COLORS)], linewidth=1.5)
    ax1.set_title("Genus Relative Abundance Over Time", fontsize=9, fontweight="bold")
    ax1.set_xlabel("Day", fontsize=8)
    ax1.set_ylabel("Rel. Abundance (%)", fontsize=8)
    ax1.tick_params(labelsize=7)
    ax1.legend(fontsize=7, loc="upper right", framealpha=0.8,
               ncol=min(3, top_n))
    ax1.set_facecolor("#F8FAFC")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    fig1.tight_layout()
    story.append(_fig_to_rl_image(fig1, FRAME_W, FULL_H))
    story.append(Spacer(1, 6))

    # ── Plots 2 / 3 / 4 side-by-side ─────────────────────────────────────────
    fig2 = MFig(figsize=(3, 2.2))
    ax2  = fig2.add_subplot(111)
    ax2.plot(times, diversity, color="#10B981", linewidth=1.6)
    ax2.fill_between(times, diversity, alpha=0.15, color="#10B981")
    ax2.set_title("Alpha Diversity", fontsize=8, fontweight="bold")
    ax2.set_xlabel("Day", fontsize=7); ax2.set_ylabel("Shannon Index", fontsize=7)
    ax2.tick_params(labelsize=7)
    ax2.set_facecolor("#F8FAFC")
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)
    fig2.tight_layout()

    fig3 = MFig(figsize=(3, 2.2))
    ax3  = fig3.add_subplot(111)
    ax3.plot(times, butyrate * 100, label="Butyrate/SCFA",
             color="#10B981", linewidth=1.5)
    ax3.plot(times, inflam   * 100, label="LPS/Inflam.",
             color="#EF4444", linewidth=1.5, linestyle="--")
    ax3.set_title("Metabolite Proxies", fontsize=8, fontweight="bold")
    ax3.set_xlabel("Day", fontsize=7); ax3.set_ylabel("Rel. Level (%)", fontsize=7)
    ax3.tick_params(labelsize=7)
    ax3.legend(fontsize=6, framealpha=0.7)
    ax3.set_facecolor("#F8FAFC")
    ax3.spines["top"].set_visible(False); ax3.spines["right"].set_visible(False)
    fig3.tight_layout()

    fig4 = MFig(figsize=(3, 2.2))
    ax4  = fig4.add_subplot(111)
    ax4.plot(times, ad_risk, color="#EF4444", linewidth=1.6)
    ax4.fill_between(times, ad_risk, alpha=0.10, color="#EF4444")
    ax4.axhline(33, color="#F59E0B", linestyle=":", linewidth=1.0, label="Moderate")
    ax4.axhline(66, color="#EF4444", linestyle=":", linewidth=1.0, label="High")
    ax4.set_ylim(0, 100)
    ax4.set_title("Projected AD Risk Score", fontsize=8, fontweight="bold")
    ax4.set_xlabel("Day", fontsize=7); ax4.set_ylabel("Risk Score", fontsize=7)
    ax4.tick_params(labelsize=7)
    ax4.legend(fontsize=6, framealpha=0.7)
    ax4.set_facecolor("#F8FAFC")
    ax4.spines["top"].set_visible(False); ax4.spines["right"].set_visible(False)
    fig4.tight_layout()

    side_row = Table(
        [[_fig_to_rl_image(fig2, THIRD_W, THIRD_H),
          _fig_to_rl_image(fig3, THIRD_W, THIRD_H),
          _fig_to_rl_image(fig4, THIRD_W, THIRD_H)]],
        colWidths=[THIRD_W, THIRD_W, THIRD_W],
    )
    side_row.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(side_row)
    story.append(Spacer(1, 12))

    # ── Species changes table ─────────────────────────────────────────────────
    story.append(Paragraph("Species Changes: Initial → Day 30", st["h2"]))
    story.append(Spacer(1, 4))

    final_ab = history[-1]
    rows_sorted = sorted(
        [(genera[i], init_ab[i] * 100, final_ab[i] * 100,
          (final_ab[i] - init_ab[i]) * 100)
         for i in range(len(genera))],
        key=lambda x: abs(x[3]), reverse=True,
    )[:20]   # cap at 20 rows

    tbl_hdr = ["Genus", "Initial %", "Day 30 %", "Δ Change"]
    tbl_data = [tbl_hdr]
    delta_signs = []
    for genus, ini, fin, delta in rows_sorted:
        tbl_data.append([
            genus,
            f"{ini:.3f}%",
            f"{fin:.3f}%",
            f"{'+'if delta >= 0 else ''}{delta:.3f}%",
        ])
        delta_signs.append(delta)

    col_w = [220, 75, 75, 75]
    tbl = Table(tbl_data, colWidths=col_w)
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_PAGE]),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
    ]
    for i, delta in enumerate(delta_signs, start=1):
        col = colors.HexColor("#065F46") if delta >= 0 else colors.HexColor("#DC2626")
        style.append(("TEXTCOLOR", (3, i), (3, i), col))
        style.append(("FONTNAME",  (3, i), (3, i), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    story.append(PageBreak())


# ── Public API ────────────────────────────────────────────────────────────────

_SECTION_BUILDERS = {
    "cover":      _section_cover,
    "overview":   _section_overview,
    "taxonomy":   _section_taxonomy,
    "diversity":  _section_diversity,
    "asv":        _section_asv_table,
    "phylogeny":  _section_phylogeny,
    "alzheimer":  _section_alzheimer,
    "simulation": _section_simulation,
}

_SECTION_ORDER = ["cover", "overview", "taxonomy", "diversity",
                  "asv", "phylogeny", "alzheimer", "simulation"]


def build_report(
    output_path: str | Path,
    sections: list[str] | None = None,
    state=None,
) -> Path:
    """
    Generate the Axis PDF report.

    Parameters
    ----------
    output_path : destination file path (str or Path)
    sections    : list of section keys to include (None = all)
    state       : AppState instance for real data (None = example data)

    Returns
    -------
    Path to the written PDF file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = _build_report_data(state)
    project = data["project"]

    decorator = _PageDecorator(
        project_title=f"{project.get('project_id', '')} — {project.get('title', '')}",
        bioproject_id=project.get("bioproject_id", ""),
    )

    frame = Frame(
        15 * mm, 12 * mm,
        W - 30 * mm, H - 36 - 24,
        id="main"
    )
    template = PageTemplate(id="main", frames=[frame], onPage=decorator)

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        pageTemplates=[template],
        title=f"Axis Report — {project.get('project_id', '')}",
        author="Axis Analytics",
        subject="Microbiome Analysis Report",
        leftMargin=0, rightMargin=0,
        topMargin=0,  bottomMargin=0,
    )

    st    = _styles()
    story: list[Any] = []

    active_sections = sections if sections else _SECTION_ORDER
    for key in _SECTION_ORDER:
        if key in active_sections and key in _SECTION_BUILDERS:
            _SECTION_BUILDERS[key](story, st, data)

    doc.build(story)
    return output_path
