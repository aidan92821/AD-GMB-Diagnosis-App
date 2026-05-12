import cobra
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

from src.services.assessment_service import get_genus_data
from src.pipeline.qiime2_runner import QiimeRunner


# load the western diet
DIET_PATH = str((Path(__file__).parent / "WesternDietAGORA2.tsv").resolve())
WESTERN_DIET = pd.read_csv(DIET_PATH, sep='\t')
WESTERN_DIET = WESTERN_DIET.set_index('metabolite')['flux'].to_dict()

# AGORA2 GEM models
AGORA2_ZIP = str((Path(__file__).parent / "AGORA2_SBML.zip").resolve())
AGORA2_DIR = str((Path(__file__).parent / "AGORA2_models").resolve())

SCFA_REACTIONS = {
    "butyrate":   "EX_2obut(e)",
    "acetate":    "EX_ac(e)",
    "propionate": "EX_pro_L(e)",
    "formate":    "EX_for(e)"
}

SCFA_NUTRIENTS = {
    "butyrate":   "2obut[e]",
    "acetate":    "ac[e]",
    "propionate": "pro_L[e]",
    "formate":    "for[e]"
}

TOTAL_BIOMASS = 1e-06

# # define broad and narrow spectrum antibiotics
# ANTIBIOTIC_SPECTRUM = {
#     "amoxicillin": {
#         "targets": ["Bacteroides", "Bifidobacterium", "Lactobacillus"],
#         "spares":  ["Akkermansia", "Ruminococcus"],
#         "type":    "bactericidal",
#     },
#     "ciprofloxacin": {
#         "targets": ["Bacteroides", "Faecalibacterium", "Ruminococcus"],
#         "spares":  ["Lactobacillus", "Bifidobacterium"],
#         "type":    "bactericidal",
#     },
#     "vancomycin": {
#         "targets": ["Bifidobacterium", "Lactobacillus"],  # gram-positives
#         "spares":  ["Bacteroides", "Faecalibacterium"],   # gram-negatives spared
#         "type":    "bactericidal",
#     }
# }


# apply user input to the diet
def apply_user_input(user_input: dict[str, float]) -> dict:
    '''
    translates user input into nutrient flux changes
    magnitude is 0 when no change, 1 when max increase
    '''
    modified = WESTERN_DIET.copy()

    # fiber
    modified["inulin[e]"] *= (1 + user_input['fiber'] * 2) # scale up inulin
    modified["arab_L[e]"] *= (1 + user_input['fiber'] * 1.5) # arabinoxylan

    # junk food 
    modified["glc_D[e]"] *= (1 + user_input['junk_food'])
    modified["fru[e]"] *= (1 + user_input['junk_food'] * 1.5)
    modified["glyc[e]"] *= (1 + user_input['junk_food'])
    modified["inulin[e]"] *= (1 - user_input['junk_food'] * 0.5) # less fiber
    
    return modified


# TODO
# # broad spectrum and narrow spectrum antibiotics case
# def apply_constraints(antibiotic: str, models: list):
#     spectrum = ANTIBIOTIC_SPECTRUM.get(antibiotic)

#     for model in models:
#         pass
    


# def apply_antibiotic_constraints(cobra_models: dict, genus: str, antibiotic: str, magnitude: float):
#     """
#     Apply antibiotic effect to a cobra model before wrapping in COMETS.
#     magnitude: 0.0 = no effect, 1.0 = full inhibition
#     """
#     spectrum = ANTIBIOTIC_SPECTRUM.get(antibiotic)
#     if not spectrum:
#         return cobra_model  # unknown antibiotic, no effect
    
#     if genus not in spectrum["targets"]:
#         return cobra_model  # this genus is not affected
    
#     biomass_rxns = [r for r in cobra_model.reactions if "biomass" in r.id.lower()]
#     if not biomass_rxns:
#         return cobra_model

#     biomass_rxn = biomass_rxns[0]

#     if spectrum["type"] == "bactericidal":
#         # kills the bacteria — zero out growth entirely
#         biomass_rxn.upper_bound = 0.0
#         biomass_rxn.lower_bound = 0.0
#     else:
#         # bacteriostatic — just slow it down
#         biomass_rxn.upper_bound *= (1 - magnitude)

#     return cobra_model
    



def find_genus_models(run_id: int, runner: QiimeRunner) -> str:

    print("[find_genus_models] function entry")
    # get the top 10 genus abundances and their genus names
    genera = get_genus_data(run_id=run_id)
    top10 = [
        (g["genus"], g["relative_abundance"])
        for g in sorted(genera, key=lambda x: x["relative_abundance"], reverse=True)[:10]
    ]

    print("[find_genus_models] got genus data")
    print(f"[find_genus_models] top10: {top10}")
    # load the AGORA2 sbml models (only unzip what i need)
    # choose the first species within the genus to be the representative
    # taxonomically similar species have similar model behavior so this is okay
    models = {} # genus_name: model_xml_path
    for genus in top10:
        model_file = runner.get_agora_models(genus=genus[0], zip_path=AGORA2_ZIP)
        print(f"[find_genus_models] found an agora model: {model_file}")
        if not model_file:
            print(f"No AGORA2 model found for genus: {genus[0]}") # TODO: temporary
            continue

        print(f"[find_genus_models] got AGORA2 model for genus {genus[0]}: {model_file}")
        filepath = os.path.join(AGORA2_DIR, model_file)
        print(f"[find_genus_models] got filepath for model in dir: {filepath}")

        # only extract if not already on disk
        if not os.path.exists(filepath):
            print(f"[find_genus_models] file does not exist yet! unzipping")
            runner.unzip_agora(zip_path=AGORA2_ZIP, model_file=model_file, dest_dir_path=AGORA2_DIR)

        print(f"[find_genus_models] unzipped that hoe")
        models[genus[0]] = filepath
        print(f"[find_genus_models] models[genus[0]] = filepath: {models[genus[0]]} = {filepath}")

    return models


# abundance = genus: relative abundance
def simulate(run_id: int, abundance: dict, user_diet: dict[str, float], runner: QiimeRunner, 
             antibiotic: str=None, n_steps: int=100, dt: float=1.0) -> dict:
    '''
    simplified community flux balance analysis (fba) with cobra (lots of trouble with COMETS)
    for each genus, run the fba with the diet as exchange bounds. growth rate can be used as proxy
    for competitive fitness. at the end, reweight relative abundances to reflect these changes
    '''
    history = {} # genus: list[dict[str: current val at step]]
    modified_diet = apply_user_input(user_diet)

    for m, d in modified_diet.items():
        print(f"{m}: {d}")

    # load AGORA models
    # find the genus models associated with the top 10 genus abundances for this run
    # simulate one model at a time with COBRA
    models = find_genus_models(run_id=run_id, runner=runner)
    for genus, model_path in models.items():
        # construct the cobra model
        model = cobra.io.read_sbml_model(model_path)

        # get initial conditions for this model
        nutrients = {k: abs(v) for k, v in modified_diet.items()}
        biomass = 1e-3
        history[genus] = []
        infeasible_steps = {}
    
        # TODO
        # # apply the antibiotics constraints
        # apply_constraints(antibiotic=antibiotic, models=cobra_models)


        # run the simulation (dynamic flux balance analysis dFBA)
        print(f"[simulate] running flux balance analysis for {model.id}..")
        for step in range(n_steps):
            with model:
                # set exchange bounds based on current nutrient concentrations
                # apply diet as upper bounds on exchange reactions
                for metabolite, conc in nutrients.items():
                    rxn_id = "EX_" + metabolite.replace("[e]", "(e)")
                    if rxn_id not in model.reactions:
                        continue
                    rxn = model.reactions.get_by_id(rxn_id)
                    if abs(conc) > 1e-10:
                        rxn.lower_bound = -abs(conc)  # always negative = uptake allowed
                    else:
                        rxn.lower_bound = 0  # nutrient exhausted


                # maximize the biomass objective for this genus with these nutrients
                solution = model.optimize()
                if step == 0:
                    print(f"[{genus}] step 0 growth rate: {solution.objective_value}")
                    print(f"[{genus}] step 0 status: {solution.status}")
                    # also check a few bounds that were set
                    for metabolite, conc in list(nutrients.items())[:5]:
                        rxn_id = "EX_" + metabolite.replace("[e]", "(e)")
                        if rxn_id in model.reactions:
                            rxn = model.reactions.get_by_id(rxn_id)
                            print(f"  {rxn_id}: conc={conc:.6f}, lb={rxn.lower_bound:.6f}")
                            print(f"  {rxn_id} flux: {solution.fluxes[rxn_id]:.6f}")

                if solution.status != 'optimal':
                    infeasible_steps[genus] = step
                    break

                if step in [0, 1, 2]:
                    for met_id, conc in list(nutrients.items())[:5]:
                        print(f"  step {step} {met_id}: {conc:.8f}")

                # get the short chain fatty acid production at this step
                scfa_production = {} # scfa: flux
                for scfa, rxn_id in SCFA_REACTIONS.items():
                    if rxn_id in model.reactions:
                        # positive flux = secretion = production!
                        scfa_production[scfa] = np.log1p(max(solution.fluxes[rxn_id], 0.0))
                    else:
                        scfa_production[scfa] = 0.0

                # get the growth rate for this genus
                growth_rate = solution.objective_value # TODO look more in metobolic research on possible caps for this??
                biomass *= (1 + growth_rate * dt)

                # deplete nutrients based on uptake fluxes
                for met_id in list(nutrients.keys()):
                    rxn_id = "EX_" + met_id.replace("[e]", "(e)")
                    if rxn_id in model.reactions:
                        flux = solution.fluxes[rxn_id]
                        nutrients[met_id] = max(nutrients[met_id] - abs(flux) * biomass * dt, 1e-10)



                history[genus].append({
                    "step": step,
                    "biomass": biomass,
                    "growth_rate": growth_rate,
                    "scfa_production": scfa_production,
                    **{f"conc_{k}": v for k, v in nutrients.items()}
                })

    # in case any model stopped at a certain step, lob off the excess from
    # the rest of the models' history. but if the step any failed at is
    # very small, just remove it
    if any(steps < 5 for steps in infeasible_steps.values()):
        broken_models = [g for g, steps in infeasible_steps.items() if steps < 5]
        for model in broken_models:
            if model in history:
                del history[model]
    else:
        for genus in history:
            history[genus] = history[genus][:n_steps]
    
    # get the final results from the dFBA for each genus
    growth_rates = {genus: record[-1]["growth_rate"] for genus, record in history.items() if record}
    scfa_production = {genus: record[-1]["scfa_production"] for genus, record in history.items() if record}
    final_biomass = { genus: record[-1]["biomass"] for genus, record in history.items() if record
}


    # calculate the new abundances for each simulated genus
    new_abundance = calc_new_abundance(abundance, final_biomass)

    results = {
        "new_abundance": new_abundance,
        "scfa_production": scfa_production,
        "history": history
    }

    return results


# uses the growth rate to estimate the new relative abundance
def calc_new_abundance(original_abundance: dict, final_biomass: dict) -> dict:
    '''
    this makes sure to only update the simulated genera's abundance using 
    their growth rates. the genera that were not simulated on keep their 
    original relative abundance because i cannot assume how they changed
    '''
    new_abundance = original_abundance.copy()

    # get the proportion of the total community that the simulated genera take up
    sim_prop = sum(original_abundance[genus] for genus in final_biomass)

    # use each genus' growth rate to recalculate its abundance by scaling its original
    scales = {}
    for genus, rate in final_biomass.items():
        scales[genus] = original_abundance[genus] * (1 + rate)

    # normalize within the scaled group only and redistribute to take up the same proportion as before
    total_sim_abun = sum(scales.values())
    if total_sim_abun > 0:
        for genus, abun in scales.items():
            new_abundance[genus] = (abun / total_sim_abun) * sim_prop

    return new_abundance


def plot_sim_results(results: dict, original_abundance: dict) -> dict:

    import matplotlib.cm as cm

    plots = {}

    # composition change (top 10)
    top10_old = {
        genus: abun
        for genus, abun in sorted(original_abundance.items(), key=lambda x: x[1], reverse=True)[:10]
    }
    top10_new = {
        genus: abun
        for genus, abun in sorted(results["new_abundance"].items(), key=lambda x: x[1], reverse=True)[:10]
    }
    top_genera = list(set(list(top10_old.keys()) + list(top10_new.keys())))
    n = len(top_genera)
    colors = [cm.tab20(i / max(n, 1)) for i in range(n)]
    genus_color_map = {genus: colors[i] for i, genus in enumerate(top_genera)}

    fig2, axes = plt.subplots(1, 2, figsize=(9, 4.5))
    _pie_kw = dict(autopct="%1.1f%%", pctdistance=0.78, startangle=90,
                   textprops={'fontsize': 7})
    if top10_old:
        axes[0].pie(top10_old.values(),
                    colors=[genus_color_map[g] for g in top10_old.keys()],
                    **_pie_kw)
    axes[0].set_title("Before Diet Change", fontsize=10, fontweight='bold', pad=8)
    if top10_new:
        axes[1].pie(top10_new.values(),
                    colors=[genus_color_map[g] for g in top10_new.keys()],
                    **_pie_kw)
    axes[1].set_title("After Diet Change (Predicted)", fontsize=10, fontweight='bold', pad=8)

    ncol = min(len(top_genera), 4)
    legend_handles = [
        plt.matplotlib.patches.Patch(color=genus_color_map[g], label=g)
        for g in top_genera
    ]
    fig2.legend(handles=legend_handles, loc="lower center", ncol=ncol,
                fontsize=8, frameon=True, bbox_to_anchor=(0.5, 0.0))
    fig2.subplots_adjust(top=0.88, bottom=0.22, left=0.02, right=0.98, wspace=0.08)
    plots['composition_shift'] = fig2

    # scfa production
    fig3, ax3 = plt.subplots(figsize=(8, 4), tight_layout=True)
    scfa_data = results.get('scfa_production', {})
    if scfa_data:
        scfa_df = pd.DataFrame(scfa_data).T
        scfa_df.plot(kind='bar', stacked=True, title="Predicted SCFA Production by Genus", ax=ax3)
        ax3.set_ylabel("log Flux (mmol/gDW/hr)")
        ax3.tick_params(axis='x', rotation=45)
    else:
        ax3.set_title("No SCFA data")
    plots['scfa'] = fig3

    # convert history to per-genus DataFrames
    dfs = {genus: pd.DataFrame(steps) for genus, steps in results["history"].items() if steps}

    # biomass over time
    fig4, ax4 = plt.subplots(figsize=(8, 4), tight_layout=True)
    for genus, df in dfs.items():
        ax4.plot(df["step"], df["biomass"], label=genus, alpha=0.5)
    ax4.set_xlabel("Time Step")
    ax4.set_ylabel("Biomass (gDW)")
    ax4.set_title("Predicted Biomass Over Time")
    if dfs:
        ax4.legend(fontsize=8)
    plots["dfba_biomass"] = fig4

    # Nutrient depletion: one subplot per nutrient, all genera on each subplot
    # This keeps it to a fixed 4 panels regardless of how many genera were simulated
    _NUTRIENT_LABELS = {
        "2obut[e]": "Butyrate",
        "ac[e]":    "Acetate",
        "pro_L[e]": "Propionate",
        "for[e]":   "Formate",
    }
    key_nutrients = list(SCFA_NUTRIENTS.values())
    genus_colors = {g: cm.tab10(i / max(len(dfs), 1)) for i, g in enumerate(dfs)}

    fig5, axes5 = plt.subplots(len(key_nutrients), 1, figsize=(8, 8), sharex=True)
    if len(key_nutrients) == 1:
        axes5 = [axes5]

    for ax, met in zip(axes5, key_nutrients):
        col = f"conc_{met}"
        has_data = False
        for genus, df in dfs.items():
            if col in df.columns:
                ax.plot(df["step"], df[col],
                        label=genus, color=genus_colors[genus],
                        linewidth=1.8, alpha=0.85)
                has_data = True
        nutrient_name = _NUTRIENT_LABELS.get(met, met)
        ax.set_title(nutrient_name, fontsize=10, fontweight='bold', loc='left', pad=4)
        ax.set_ylabel("Concentration\n(mmol)", fontsize=8)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.25, linestyle='--')
        ax.spines[['top', 'right']].set_visible(False)
        if has_data:
            ax.legend(fontsize=7, ncol=2, loc='upper right',
                      framealpha=0.7, edgecolor='#E2E8F0')
        else:
            ax.text(0.5, 0.5, "No data for this nutrient",
                    ha='center', va='center', transform=ax.transAxes,
                    color='#94A3B8', fontsize=9, style='italic')

    axes5[-1].set_xlabel("Time Step", fontsize=9)
    fig5.suptitle("Nutrient Depletion Over Simulation", fontsize=11,
                  fontweight='bold', y=0.98)
    fig5.tight_layout(rect=[0, 0, 1, 0.96])
    plots["dfba_nutrients"] = fig5

    return plots


# show this as a table on the simulation page
def get_abundance_shift_stats(abundance_old, abundance_new) -> pd.DataFrame:

    # the genera in this df are most likely a subset of the original genus list since
    # the simulation depends on matching the genera to AGORA2 GEMs
    results_new = pd.DataFrame(list(abundance_new.items()), columns=['genus', 'after'])
    results_old = pd.DataFrame(list(abundance_old.items()), columns=['genus', 'before'])
    results = results_new.merge(right=results_old, how='inner', on='genus')
    results['abs_change'] = results['after'] - results['before']
    results['pct_change'] = np.where(
        results['before'] != 0,
        (results['abs_change'] / results['before']) * 100,
        0
    )
    
    return results