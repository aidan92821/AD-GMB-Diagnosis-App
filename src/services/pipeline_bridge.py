# src/services/pipeline_bridge.py
#
# After the QIIME2 pipeline completes and results are stored in the DB,
# this module reloads them into the live AppState so every page updates.

from __future__ import annotations

from models.app_state import AppState


def load_pipeline_results(state: AppState) -> list[str]:
    """
    Pull the QIIME2 pipeline results that were just written to the DB and
    populate *state* in-place.

    Returns a list of warning strings (non-fatal issues). Empty = all good.
    """
    from services.assessment_service import (
        get_genus_data,
        get_feature_counts,
        list_runs_for_project,
    )

    warnings: list[str] = []

    try:
        # Find the DB project that matches this BioProject
        from src.db.database import SessionLocal
        from src.db.repository import get_run_by_srr

        session = SessionLocal()
        try:
            for run_state in state.runs:
                srr = run_state.accession
                db_run = get_run_by_srr(session, srr)
                if db_run is None:
                    warnings.append(f"{srr}: not found in DB after pipeline")
                    continue

                run_id = db_run.run_id
                lbl    = run_state.label

                # ── Genus abundances ──────────────────────────────────────────
                genera = get_genus_data(run_id)
                if genera:
                    state.genus_abundances[lbl] = [
                        (g["genus"], g["relative_abundance"])
                        for g in genera
                    ]
                else:
                    warnings.append(f"{srr}: no genus data in DB")

                # ── ASV feature counts ────────────────────────────────────────
                feat_counts = get_feature_counts(run_id)
                if feat_counts:
                    state.asv_features[lbl] = [
                        {
                            "id":    fc["feature_id"],
                            "genus": fc.get("taxonomy", ""),
                            "count": fc["count"],
                            "pct":   0.0,   # raw count — pct not stored
                        }
                        for fc in feat_counts[:50]   # cap at 50 for UI
                    ]

                run_state.uploaded = True

        finally:
            session.close()

    except Exception as exc:
        warnings.append(f"DB load error: {exc}")

    # Recompute derived metrics from the newly loaded genus data
    if state.genus_abundances:
        labels = state.run_labels
        try:
            from ui.main_window import _AnalysisWorker
            _AnalysisWorker._fill_alpha(state, labels)
            _AnalysisWorker._fill_beta(state, labels, len(labels))
            _AnalysisWorker._fill_pcoa(state, labels, len(labels))
            _AnalysisWorker._fill_risk(state)
        except Exception as exc:
            warnings.append(f"Metric recompute error: {exc}")

        state.asv_count   = sum(len(f) for f in state.asv_features.values())
        state.genus_count = len({
            g for genera in state.genus_abundances.values()
            for g, _ in genera
        })

    return warnings
