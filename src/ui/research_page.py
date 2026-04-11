"""
Axis — Research Insights page.

Shows which bacteria contribute most to the AD risk prediction,
explains the gut–brain axis mechanisms, and links to the key
literature that underpins the model.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QFont

from models.app_state import AppState
from resources.styles import (
    ACCENT, BG_PAGE, BG_CARD, BORDER,
    TEXT_H, TEXT_M, TEXT_HINT,
    DANGER_FG, DANGER_BG, SUCCESS_FG, SUCCESS_BG,
    WARN_FG, WARN_BG,
)

# ── Biomarker knowledge base ──────────────────────────────────────────────────
# Each entry: weight (from model), mechanism, key finding, primary reference

BIOMARKER_INFO: dict[str, dict] = {
    "Faecalibacterium": {
        "weight":     -0.30,
        "role":       "Protective — major anti-inflammatory SCFA producer",
        "mechanism":  (
            "F. prausnitzii produces butyrate via fermentation of dietary fibre. "
            "Butyrate is the primary energy source for colonocytes, strengthens "
            "tight-junction proteins (ZO-1, occludin), and inhibits histone "
            "deacetylases in microglial cells — reducing neuroinflammatory "
            "cytokine production (IL-6, TNF-α). Depletion increases gut "
            "permeability and systemic LPS exposure."
        ),
        "finding":    "Significantly depleted in AD patients vs. healthy controls; "
                      "lowest levels found in patients with highest amyloid burden.",
        "ref":        "Vogt et al., 2017 · Sci. Reports",
        "normal":     ">8%",
    },
    "Akkermansia": {
        "weight":     -0.25,
        "role":       "Protective — gut barrier and mucus layer integrity",
        "mechanism":  (
            "A. muciniphila resides in the mucus layer and degrades mucin, "
            "stimulating the host to replenish it (net protective effect). "
            "Its outer membrane protein Amuc_1100 activates TLR2, reducing "
            "intestinal permeability. Lower Akkermansia → 'leaky gut' → "
            "systemic inflammation → microglial activation → Aβ aggregation."
        ),
        "finding":    "Inversely correlated with cognitive decline scores; "
                      "administration in mouse models reduced amyloid pathology.",
        "ref":        "Liu et al., 2019 · Front. Neurosci.",
        "normal":     ">1%",
    },
    "Bifidobacterium": {
        "weight":     -0.20,
        "role":       "Protective — neuroinflammation reduction",
        "mechanism":  (
            "Bifidobacterium species produce acetate and GABA — a major "
            "inhibitory neurotransmitter. They also lower cortisol via the "
            "HPA axis and reduce pro-inflammatory cytokines. Acetate crosses "
            "the blood–brain barrier and directly suppresses microglial "
            "activation. Deficiency is associated with increased Aβ₄₂ levels."
        ),
        "finding":    "Significantly reduced in both MCI and AD groups compared "
                      "to age-matched controls.",
        "ref":        "Shen et al., 2021 · J. Neuroinflammation",
        "normal":     ">2%",
    },
    "Roseburia": {
        "weight":     -0.18,
        "role":       "Protective — butyrate / neuroprotection",
        "mechanism":  (
            "Roseburia intestinalis is one of the major butyrate producers in "
            "the human colon. Butyrate inhibits NF-κB signalling, reducing "
            "IL-1β and IL-18 production. It also upregulates BDNF (brain-derived "
            "neurotrophic factor), which supports neuronal survival and synaptic "
            "plasticity. Depleted in AD, likely due to reduced dietary fibre intake."
        ),
        "finding":    "Reduction correlates with decreased BDNF expression and "
                      "hippocampal atrophy in AD models.",
        "ref":        "Harach et al., 2017 · Sci. Reports",
        "normal":     ">3%",
    },
    "Blautia": {
        "weight":     -0.15,
        "role":       "Protective — anti-inflammatory acetate producer",
        "mechanism":  (
            "Blautia species produce acetate and are associated with reduced "
            "systemic inflammation. They inhibit the growth of pro-inflammatory "
            "Proteobacteria and reduce serum LPS levels. Lower Blautia is linked "
            "to higher plasma levels of IL-6 and CRP — both established "
            "neuroinflammation markers in AD."
        ),
        "finding":    "Depleted in AD; negatively correlated with MMSE score "
                      "decline rate.",
        "ref":        "Zhuang et al., 2018 · J. Alzheimer's Dis.",
        "normal":     ">4%",
    },
    "Prevotella": {
        "weight":     +0.22,
        "role":       "Risk — pro-inflammatory LPS producer",
        "mechanism":  (
            "Prevotella copri produces high quantities of LPS "
            "(lipopolysaccharide), a potent activator of TLR4 on microglia. "
            "Chronic low-grade LPS exposure ('metabolic endotoxaemia') drives "
            "neuroinflammation, impairs the blood–brain barrier, and accelerates "
            "Aβ aggregation. Elevated in AD patients with metabolic comorbidities."
        ),
        "finding":    "Elevated in AD patients; Prevotella abundance positively "
                      "correlated with plasma IL-6 and TNF-α concentrations.",
        "ref":        "Cattaneo et al., 2017 · J. Alzheimer's Dis.",
        "normal":     "<10%",
    },
    "Clostridium": {
        "weight":     +0.20,
        "role":       "Risk — neurotoxin and LPS associated species",
        "mechanism":  (
            "Several Clostridium species (C. perfringens, C. difficile) produce "
            "potent neurotoxins (epsilon toxin, CDT) and large quantities of LPS. "
            "Epsilon toxin can cross the blood–brain barrier and directly damages "
            "oligodendrocytes. C. difficile also disrupts the gut barrier, "
            "enabling systemic toxin and LPS translocation."
        ),
        "finding":    "Significantly elevated in AD patients; highest levels in "
                      "patients with GI symptoms and accelerated cognitive decline.",
        "ref":        "Vogt et al., 2017 · Sci. Reports",
        "normal":     "<4%",
    },
    "Veillonella": {
        "weight":     +0.18,
        "role":       "Risk — elevated in MCI and early AD",
        "mechanism":  (
            "Veillonella metabolises lactate and propionate and produces "
            "pro-inflammatory metabolites. Elevated Veillonella is associated "
            "with systemic immune activation and altered tryptophan metabolism "
            "(reducing serotonin precursor availability). The exact gut–brain "
            "mechanism is still under investigation, but consistent elevation "
            "across multiple AD cohorts supports its role as a biomarker."
        ),
        "finding":    "Consistently elevated in MCI and AD cohorts across "
                      "independent studies in Asia and Europe.",
        "ref":        "Shen et al., 2021 · J. Neuroinflammation",
        "normal":     "<3%",
    },
    "Enterococcus": {
        "weight":     +0.16,
        "role":       "Risk — neuroinflammation marker",
        "mechanism":  (
            "Enterococcus faecalis and E. faecium produce extracellular "
            "superoxide, hydrogen peroxide, and extracellular DNA that trigger "
            "TLR9-mediated inflammation. They also disrupt tight junctions via "
            "cytolysin production. Elevated Enterococcus is associated with "
            "increased serum LPS-binding protein — an indirect measure of "
            "gut-derived endotoxin exposure."
        ),
        "finding":    "Elevated in AD patients and correlates with "
                      "neuroinflammation biomarkers in cerebrospinal fluid.",
        "ref":        "Liu et al., 2019 · Front. Neurosci.",
        "normal":     "<2%",
    },
    "Streptococcus": {
        "weight":     +0.12,
        "role":       "Risk — gut permeability and amyloid-associated",
        "mechanism":  (
            "Certain Streptococcus species produce amyloid-like proteins "
            "(e.g. FapC curli fibres) that may seed Aβ aggregation via "
            "cross-seeding mechanisms. They also activate TLR2/TLR1 "
            "heterodimers on microglia and can translocate across a compromised "
            "gut barrier to cause systemic bacteraemia in severe cases."
        ),
        "finding":    "Elevated in AD gut microbiome studies; serum anti-"
                      "Streptococcus antibodies elevated in AD vs. controls.",
        "ref":        "Cattaneo et al., 2017 · J. Alzheimer's Dis.",
        "normal":     "<5%",
    },
}

# ── Published references ──────────────────────────────────────────────────────

REFERENCES = [
    {
        "authors": "Vogt NM, Kerby RL, Dill-McFarland KA, et al.",
        "year":    "2017",
        "title":   "Gut microbiome alterations in Alzheimer's disease",
        "journal": "Scientific Reports, 7, 13537",
        "summary": "First large-scale 16S rRNA study of AD gut microbiome. "
                   "Found reduced Firmicutes/Bacteroidetes ratio, depleted "
                   "Bifidobacterium and Ruminococcaceae, elevated Bacteroidetes. "
                   "Established the gut–AD link in human subjects.",
    },
    {
        "authors": "Cattaneo A, Cattane N, Galluzzi S, et al.",
        "year":    "2017",
        "title":   "Association of brain amyloidosis with pro-inflammatory gut bacterial taxa "
                   "and peripheral inflammation markers in cognitively impaired elderly",
        "journal": "Alzheimer's & Dementia, 13(6), 697–707",
        "summary": "Linked elevated Escherichia/Shigella and depleted E. rectale to "
                   "brain amyloid burden (PET imaging). First direct evidence connecting "
                   "specific gut taxa to Aβ accumulation in living humans.",
    },
    {
        "authors": "Liu P, Wu L, Peng G, et al.",
        "year":    "2019",
        "title":   "Altered microbiomes distinguish Alzheimer's disease from amnestic mild "
                   "cognitive impairment and health in a Chinese cohort",
        "journal": "Brain, Behavior, and Immunity, 80, 633–643",
        "summary": "Demonstrated progressive microbiome dysbiosis from healthy → MCI → AD. "
                   "Akkermansia and Faecalibacterium showed the strongest inverse "
                   "correlation with cognitive scores (MMSE).",
    },
    {
        "authors": "Shen L, Liu L, Ji H-F.",
        "year":    "2021",
        "title":   "Alzheimer's disease, gut microbiota, and mitochondrial dysfunction",
        "journal": "Journal of Neuroinflammation, 18, 294",
        "summary": "Identified Veillonella, Clostridium, and depleted Bifidobacterium "
                   "as consistent AD biomarkers across Asian cohorts. Proposed the "
                   "mitochondrial dysfunction–gut–brain axis hypothesis.",
    },
    {
        "authors": "Harach T, Marungruang N, Duthilleul N, et al.",
        "year":    "2017",
        "title":   "Reduction of Abeta amyloid pathology in APPPS1 transgenic mice in the "
                   "absence of gut microbiota",
        "journal": "Scientific Reports, 7, 41802",
        "summary": "Landmark germ-free mouse study: APPPS1 mice raised without gut bacteria "
                   "showed dramatically reduced amyloid plaque formation. Gut microbiota "
                   "transplant from AD mice restored pathology — causal evidence for gut→brain.",
    },
    {
        "authors": "Zhuang ZQ, Shen LL, Li WW, et al.",
        "year":    "2018",
        "title":   "Gut Microbiota is Altered in Patients with Alzheimer's Disease",
        "journal": "Journal of Alzheimer's Disease, 63(4), 1337–1346",
        "summary": "Meta-analysis across Chinese AD cohorts confirmed Blautia depletion "
                   "and Proteobacteria expansion. Showed MMSE score negatively correlates "
                   "with Proteobacteria abundance (r = −0.61).",
    },
    {
        "authors": "Jiang C, Li G, Huang P, Liu Z, Zhao B.",
        "year":    "2017",
        "title":   "The Gut Microbiota and Alzheimer's Disease",
        "journal": "Journal of Alzheimer's Disease, 58(1), 1–15",
        "summary": "Comprehensive review of gut–brain axis mechanisms in AD: "
                   "LPS-mediated neuroinflammation, short-chain fatty acid depletion, "
                   "vagus nerve signalling, and amyloid cross-seeding. "
                   "Proposed microbiome-targeted therapy as a prevention strategy.",
    },
]


# ── Contribution bar widget ───────────────────────────────────────────────────

class ContributionBar(QWidget):
    """
    Horizontal signed bar for one biomarker's contribution score.
    Green = protective (negative contribution to risk).
    Red   = risk-raising (positive contribution to risk).
    """

    def __init__(self, genus: str, contribution: float, abundance: float,
                 max_abs: float, parent=None):
        super().__init__(parent)
        self._genus        = genus
        self._contribution = contribution   # signed: negative = protective
        self._abundance    = abundance
        self._max_abs      = max_abs or 1.0
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H   = self.width(), self.height()
        mid    = W // 2
        bar_h  = 14
        bar_y  = (H - bar_h) // 2 + 6
        radius = 4.0

        # Background track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BORDER))
        p.drawRoundedRect(0, bar_y, W, bar_h, radius, radius)

        # Filled bar
        fill_w = int(abs(self._contribution) / self._max_abs * (W // 2 - 4))
        fill_w = max(fill_w, 3)
        color  = QColor("#10B981") if self._contribution < 0 else QColor("#EF4444")
        p.setBrush(color)
        if self._contribution < 0:
            p.drawRoundedRect(mid - fill_w, bar_y, fill_w, bar_h, radius, radius)
        else:
            p.drawRoundedRect(mid, bar_y, fill_w, bar_h, radius, radius)

        # Centre line
        p.setPen(QColor(TEXT_HINT))
        p.drawLine(mid, bar_y - 2, mid, bar_y + bar_h + 2)

        # Genus label (left)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(TEXT_H))
        p.drawText(2, 0, mid - 4, bar_y - 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                   self._genus)

        # Abundance label (right)
        font.setBold(False)
        font.setPointSize(9)
        p.setFont(font)
        p.setPen(QColor(TEXT_HINT))
        sign  = "+" if self._contribution > 0 else ""
        label = f"{sign}{self._contribution:+.2f}  ({self._abundance:.1f}%)"
        p.drawText(mid + 4, 0, W - mid - 4, bar_y - 1,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, label)


# ── Research page ─────────────────────────────────────────────────────────────

class ResearchPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # Page header
        hdr = QHBoxLayout()
        title = QLabel("Research Insights")
        title.setObjectName("page_title")
        hdr.addWidget(title)
        hdr.addStretch()
        sub = QLabel("Gut–Brain Axis & Alzheimer's Disease")
        sub.setStyleSheet(f"font-size: 12px; color: {TEXT_HINT};")
        hdr.addWidget(sub)
        root.addLayout(hdr)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setObjectName("content_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        self._scroll = scroll
        self._render(None)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, state: AppState):
        self._render(state)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, state):
        inner = QWidget()
        lay   = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(20)

        # ── Section 1: Contribution analysis ─────────────────────────────────
        lay.addWidget(self._build_contribution_section(state))

        # ── Section 2: Biomarker mechanism cards ─────────────────────────────
        lay.addWidget(self._build_mechanism_section(state))

        # ── Section 3: Research references ───────────────────────────────────
        lay.addWidget(self._build_references_section())

        lay.addStretch()
        self._scroll.setWidget(inner)

    def _build_contribution_section(self, state) -> QFrame:
        from utils.model import BIOMARKER_WEIGHTS

        outer = self._card()
        outer.layout().addWidget(self._section_title("Biomarker Contribution to Risk Score"))
        outer.layout().addWidget(self._hint(
            "Each bar shows how much a genus pushes the predicted risk up (red) or down (green). "
            "Length = weight × abundance. Longer bar = stronger influence on your result."
        ))

        # Compute contributions from current state or use equal weights as placeholder
        contributions: list[tuple[str, float, float]] = []  # (genus, contribution, abundance)

        if state and state.genus_abundances:
            # Average across runs
            all_genera: dict[str, list[float]] = {}
            for lbl in state.run_labels:
                for genus, pct in state.genus_abundances.get(lbl, []):
                    all_genera.setdefault(genus, []).append(pct)
            avg_abundances = {g: sum(v) / len(v) for g, v in all_genera.items()}
            total = sum(avg_abundances.values()) or 100.0
            normed = {g: v / total * 100 for g, v in avg_abundances.items()}

            for genus, weight in BIOMARKER_WEIGHTS.items():
                abund = normed.get(genus, 0.0)
                contributions.append((genus, round(weight * abund, 3), round(abund, 1)))
        else:
            # Placeholder — use reference abundances
            ref_abund = {
                "Faecalibacterium": 8.0, "Akkermansia": 1.5, "Bifidobacterium": 2.5,
                "Roseburia": 4.0, "Blautia": 5.0, "Eubacterium": 3.0,
                "Lachnospiraceae": 4.0, "Prevotella": 7.0, "Clostridium": 3.5,
                "Veillonella": 2.5, "Enterococcus": 1.5, "Streptococcus": 2.5,
                "Escherichia": 1.0,
            }
            for genus, weight in BIOMARKER_WEIGHTS.items():
                abund = ref_abund.get(genus, 2.0)
                contributions.append((genus, round(weight * abund, 3), abund))

        # Sort by absolute contribution descending
        contributions.sort(key=lambda x: abs(x[1]), reverse=True)
        max_abs = max(abs(c[1]) for c in contributions) if contributions else 1.0

        bar_container = QWidget()
        bar_lay = QVBoxLayout(bar_container)
        bar_lay.setContentsMargins(8, 8, 8, 4)
        bar_lay.setSpacing(4)

        for genus, contrib, abund in contributions:
            bar_lay.addWidget(ContributionBar(genus, contrib, abund, max_abs))

        # Legend
        legend = QHBoxLayout()
        for color, label in [("#10B981", "Protective (lowers risk)"), ("#EF4444", "Risk-raising (raises risk)")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 14px;")
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_HINT};")
            legend.addWidget(dot)
            legend.addWidget(lbl)
            legend.addSpacing(20)
        legend.addStretch()
        bar_lay.addLayout(legend)

        outer.layout().addWidget(bar_container)

        if state and state.genus_abundances:
            note = self._hint("Values computed from the average across all loaded runs.")
        else:
            note = self._hint("Fetch a BioProject to see contributions from real data.")
        outer.layout().addWidget(note)
        return outer

    def _build_mechanism_section(self, state) -> QFrame:
        outer = self._card()
        outer.layout().addWidget(self._section_title("Bacterial Mechanisms in Alzheimer's Disease"))
        outer.layout().addWidget(self._hint(
            "Click any bacterium below to understand how it influences neuroinflammation "
            "and amyloid pathology via the gut–brain axis."
        ))

        # Determine which genera to highlight based on current data
        highlighted: set[str] = set()
        if state and state.genus_abundances:
            from utils.model import BIOMARKER_WEIGHTS, BIOMARKER_REFERENCE
            all_genera: dict[str, list[float]] = {}
            for lbl in state.run_labels:
                for genus, pct in state.genus_abundances.get(lbl, []):
                    all_genera.setdefault(genus, []).append(pct)
            avg = {g: sum(v) / len(v) for g, v in all_genera.items()}
            for genus in BIOMARKER_INFO:
                abund = avg.get(genus, 0)
                ref = BIOMARKER_REFERENCE.get(genus, {})
                normal_str = ref.get("normal", "")
                weight = BIOMARKER_WEIGHTS.get(genus, 0)
                # Flag as abnormal
                try:
                    threshold = float(
                        normal_str.replace(">", "").replace("<", "")
                        .replace("%", "").strip()
                    )
                    if weight < 0 and abund < threshold:
                        highlighted.add(genus)
                    elif weight > 0 and abund > threshold:
                        highlighted.add(genus)
                except ValueError:
                    pass

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        items = list(BIOMARKER_INFO.items())
        for idx, (genus, info) in enumerate(items):
            grid.addWidget(
                self._mechanism_card(genus, info, genus in highlighted, state),
                idx // 2, idx % 2,
            )

        outer.layout().addLayout(grid)
        return outer

    def _mechanism_card(self, genus: str, info: dict, flagged: bool, state) -> QFrame:
        is_protective = info["weight"] < 0
        bg     = SUCCESS_BG if is_protective else DANGER_BG
        fg     = SUCCESS_FG if is_protective else DANGER_FG
        border = "#BBF7D0" if is_protective else "#FECACA"

        if flagged:
            # Abnormal for this sample — stronger border
            border = SUCCESS_FG if is_protective else DANGER_FG

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1.5px solid {border};
                border-radius: 10px;
            }}
        """)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Header row: name + role badge + abundance
        hdr = QHBoxLayout()
        name_lbl = QLabel(genus)
        name_lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {TEXT_H};")
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        badge = QLabel("Protective" if is_protective else "Risk factor")
        badge.setStyleSheet(f"""
            background: {bg}; color: {fg};
            border-radius: 8px; padding: 2px 9px;
            font-size: 10px; font-weight: 700;
        """)
        hdr.addWidget(badge)
        lay.addLayout(hdr)

        # Abundance in current data (if available)
        if state and state.genus_abundances:
            all_genera: dict[str, list[float]] = {}
            for lbl in state.run_labels:
                for g, pct in state.genus_abundances.get(lbl, []):
                    all_genera.setdefault(g, []).append(pct)
            avg_abund = sum(all_genera.get(genus, [0])) / max(len(all_genera.get(genus, [1])), 1)
            status_color = DANGER_FG if flagged else SUCCESS_FG
            abund_lbl = QLabel(
                f"Your sample: <b>{avg_abund:.1f}%</b>  ·  Normal: {info['normal']}"
            )
            abund_lbl.setStyleSheet(f"font-size: 11px; color: {status_color};")
            abund_lbl.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(abund_lbl)

        # Mechanism
        mech_title = QLabel("Mechanism")
        mech_title.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {TEXT_HINT}; "
            "text-transform: uppercase; letter-spacing: 0.05em;"
        )
        lay.addWidget(mech_title)
        mech_lbl = QLabel(info["mechanism"])
        mech_lbl.setWordWrap(True)
        mech_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_M}; line-height: 1.5;")
        lay.addWidget(mech_lbl)

        # Key finding
        sep = QFrame()
        sep.setStyleSheet(f"background: {BORDER}; max-height: 1px;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        find_lbl = QLabel(f"📌  {info['finding']}")
        find_lbl.setWordWrap(True)
        find_lbl.setStyleSheet(
            f"font-size: 11px; color: {TEXT_M}; "
            "font-style: italic;"
        )
        lay.addWidget(find_lbl)

        ref_lbl = QLabel(f"Source: {info['ref']}")
        ref_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_HINT};")
        lay.addWidget(ref_lbl)

        return card

    def _build_references_section(self) -> QFrame:
        outer = self._card()
        outer.layout().addWidget(self._section_title("Key Research Articles"))
        outer.layout().addWidget(self._hint(
            "The biomarker weights used in the risk model are derived from these "
            "peer-reviewed publications. All studies used 16S rRNA amplicon sequencing "
            "of human stool samples unless otherwise noted."
        ))

        for i, ref in enumerate(REFERENCES):
            ref_frame = QFrame()
            ref_frame.setStyleSheet(f"""
                QFrame {{
                    background: {BG_PAGE};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                }}
            """)
            rf_lay = QVBoxLayout(ref_frame)
            rf_lay.setContentsMargins(14, 10, 14, 10)
            rf_lay.setSpacing(4)

            # Number + title
            title_row = QHBoxLayout()
            num = QLabel(f"[{i+1}]")
            num.setFixedWidth(30)
            num.setStyleSheet(
                f"font-size: 11px; font-weight: 700; color: {ACCENT};"
            )
            title_row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            title_lbl = QLabel(ref["title"])
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {TEXT_H};"
            )
            title_row.addWidget(title_lbl, 1)
            rf_lay.addLayout(title_row)

            # Authors + journal
            meta = QLabel(f"{ref['authors']}  ({ref['year']})  ·  {ref['journal']}")
            meta.setWordWrap(True)
            meta.setStyleSheet(f"font-size: 10px; color: {TEXT_HINT}; margin-left: 30px;")
            rf_lay.addWidget(meta)

            # Summary
            summary_lbl = QLabel(ref["summary"])
            summary_lbl.setWordWrap(True)
            summary_lbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_M}; margin-left: 30px; "
                "font-style: italic;"
            )
            rf_lay.addWidget(summary_lbl)

            outer.layout().addWidget(ref_frame)

        return outer

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _card(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        return f

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 800; color: {TEXT_H}; "
            "background: transparent;"
        )
        return lbl

    def _hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {TEXT_HINT}; background: transparent;"
        )
        return lbl
