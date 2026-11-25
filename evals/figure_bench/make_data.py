"""Generate the data for the 10 figure-bench tasks and the hidden answer key.

Deterministic (fixed seeds): re-running rewrites identical CSVs and answers.json.
Needs numpy and mintfig (task 06 ships a figure the assistant "sent" earlier).

    python evals/figure_bench/make_data.py
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
HELDOUT = HERE / "heldout"  # never shown to anyone tuning mintfig or SKILL.md
ANSWERS: dict[str, dict] = {}


def _write(task: str, name: str, header: list[str], rows: list[list]) -> None:
    out = (HELDOUT if task.startswith("h") else TASKS) / task / "data"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / name, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else (round(v, 6) if isinstance(v, float) else v) for v in row])


def _answer(task: str, what: str, values: list[float], *, rel: float = 0.0, abs_: float = 0.0) -> None:
    ANSWERS[task] = {"what": what, "accept": [float(v) for v in values], "rel_tol": rel, "abs_tol": abs_}


# 01 ML ablation ------------------------------------------------------------- #
def ablation() -> None:
    rng = np.random.default_rng(101)
    means = {"full model": 82.4, "no retrieval": 74.1, "no reranker": 80.9,
             "no fine-tuning": 77.6, "smaller encoder": 81.7}
    rows = [[v, s, float(m + rng.normal(0, 0.9))] for v, m in means.items() for s in range(5)]
    _write("01_ablation", "ablation_runs.csv", ["variant", "seed", "accuracy_pct"], rows)
    latency = {"full model": 412.0, "no retrieval": 188.0, "no reranker": 291.0,
               "no fine-tuning": 405.0, "smaller encoder": 352.0}
    _write("01_ablation", "variant_latency.csv", ["variant", "p50_latency_ms", "gpu_cost_per_1k_usd"],
           [[v, ms, round(ms * 0.0021, 3)] for v, ms in latency.items()])
    acc = {v: np.mean([r[2] for r in rows if r[0] == v]) for v in means}
    # The thread asks about the reranker and the bigger encoder (retrieval is settled).
    rerank = acc["full model"] - acc["no reranker"]
    encoder = acc["full model"] - acc["smaller encoder"]
    _answer("01_ablation", "accuracy cost (points) of dropping the reranker or the bigger encoder",
            [rerank, encoder, acc["no reranker"]], abs_=0.3)


# 02 A/B latency ------------------------------------------------------------- #
def ab_latency() -> None:
    rng = np.random.default_rng(202)
    rows = []
    for arm, mu in (("control", np.log(420)), ("new flow", np.log(352))):
        for i in range(400):
            rows.append([arm, f"s{arm[0]}{i:03d}", float(rng.lognormal(mu, 0.45))])
    _write("02_ab_latency", "checkout_sessions.csv", ["arm", "session", "latency_ms"], rows)
    med = {a: np.median([r[2] for r in rows if r[0] == a]) for a in ("control", "new flow")}
    diff = med["control"] - med["new flow"]
    pct = 100 * diff / med["control"]
    _answer("02_ab_latency", "median latency saving (ms or %), or the two medians",
            [diff, pct, med["new flow"], med["control"]], rel=0.06)


# 03 dose response ----------------------------------------------------------- #
def dose_response() -> None:
    rng = np.random.default_rng(303)
    conc = [0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000, 3000]  # nM
    ic50 = {"CPD-7": 12.0, "CPD-2": 140.0, "CPD-9": 900.0, "CPD-4": None}
    rows = []
    for cpd, c50 in ic50.items():
        for c in conc:
            for rep in range(3):
                if c50 is None:  # inactive: never reaches 50%
                    y = 14 / (1 + (400 / c)) + rng.normal(0, 3.0)
                else:
                    y = 100 / (1 + (c50 / c) ** 1.1) + rng.normal(0, 3.0)
                rows.append([cpd, c, rep + 1, float(y)])
    _write("03_dose_response", "inhibition.csv", ["compound", "conc_nM", "replicate", "inhibition_pct"], rows)
    # IC50 as the log-interpolated 50% crossing of the replicate means (what facts report)
    xs = np.log10(conc)
    means = [np.mean([r[3] for r in rows if r[0] == "CPD-7" and r[1] == c]) for c in conc]
    k = next(i for i in range(len(means) - 1) if (means[i] - 50) * (means[i + 1] - 50) <= 0)
    t = (50 - means[k]) / (means[k + 1] - means[k])
    est = 10 ** (xs[k] + t * (xs[k + 1] - xs[k]))
    _answer("03_dose_response", "IC50 of the most potent compound (nM)", [est, 12.0], rel=0.3)


# 04 battery fade ------------------------------------------------------------ #
def battery() -> None:
    rng = np.random.default_rng(404)
    cycles = list(range(0, 801, 50))
    k = {"baseline": 0.00049, "additive FEC": 0.00031, "additive VC": 0.00036}
    rows = []
    for el, kk in k.items():
        for cell in range(4):
            kc = kk * rng.lognormal(0, 0.06)
            tag = {"baseline": "BL", "additive FEC": "FEC", "additive VC": "VC"}[el]
            for c in cycles:
                v = 100 * np.exp(-kc * c) + rng.normal(0, 0.3)
                if tag == "VC" and cell == 2 and c >= 200:  # crimping defect: sudden fade
                    v *= np.exp(-0.004 * (c - 200))
                rows.append([el, f"{tag}-{cell + 1}", c, float(v)])
    _write("04_battery_fade", "cycling.csv", ["electrolyte", "cell", "cycle", "retention_pct"], rows)
    base = [np.mean([r[3] for r in rows if r[0] == "baseline" and r[2] == c]) for c in cycles]
    i = next(j for j in range(len(base) - 1) if base[j] >= 80 > base[j + 1])
    cross = cycles[i] + (base[i] - 80) / (base[i] - base[i + 1]) * (cycles[i + 1] - cycles[i])
    _answer("04_battery_fade", "cycle at which the baseline reaches 80% retention", [cross], rel=0.08)


# 05 building retrofit ------------------------------------------------------- #
def retrofit() -> None:
    rng = np.random.default_rng(505)
    start = date(2026, 6, 1)
    days = [start + timedelta(d) for d in range(120)]
    retro = date(2026, 7, 16)
    base = {"Library": 2400.0, "Lab annex": 5200.0, "Gym": 1700.0}
    cut = {"Library": 0.18, "Lab annex": 0.27, "Gym": 0.0}
    rows = []
    for b, kwh in base.items():
        for d in days:
            weekend = d.weekday() >= 5
            v = kwh * (0.72 if weekend else 1.0) * (1 - cut[b] if d >= retro else 1.0)
            v *= rng.lognormal(0, 0.06)
            if b == "Gym" and date(2026, 8, 3) <= d <= date(2026, 8, 6):
                v = None  # meter outage
            rows.append([d.isoformat(), b, v])
    _write("05_retrofit", "daily_energy.csv", ["date", "building", "kwh"], rows)
    lab_before = np.median([r[2] for r in rows if r[1] == "Lab annex" and r[0] < retro.isoformat()])
    lab_after = np.median([r[2] for r in rows if r[1] == "Lab annex" and r[0] >= retro.isoformat()])
    pct = 100 * (1 - lab_after / lab_before)
    _answer("05_retrofit", "Lab annex median daily drop after retrofit (%), or kWh saved per day",
            [pct, lab_before - lab_after], rel=0.12)


# 06 energy mix -------------------------------------------------------------- #
def energy_mix() -> None:
    twh = {"natural gas": 182.0, "coal": 61.5, "nuclear": 94.0, "wind": 88.3, "solar": 57.9,
           "hydro": 31.2, "biomass": 9.4, "oil": 2.1}
    rows = [[k, v] for k, v in twh.items()]
    _write("06_energy_mix", "generation_2025.csv", ["source", "twh"], rows)
    total = sum(twh.values())
    ren = 100 * (twh["wind"] + twh["solar"] + twh["hydro"]) / total
    ren_bio = 100 * (twh["wind"] + twh["solar"] + twh["hydro"] + twh["biomass"]) / total
    _answer("06_energy_mix", "renewable share of generation without biomass (%)", [ren], abs_=1.0)
    _sent_figure(twh, ren_bio)


def _sent_figure(twh: dict[str, float], ren_bio: float) -> None:
    """The figure the assistant sent earlier in the thread (biomass wrongly counted)."""
    import mintfig as mint

    ren_names = ["wind", "solar", "hydro", "biomass"]
    fig = mint.explain(
        f"Renewables supplied {ren_bio:.0f}% of the region's electricity in 2025",
        mint.compare(twh, highlight=["wind", "solar", "hydro"], label="Annual generation", unit="TWh",
                   title="Wind is now the third-largest source"),
        mint.share({"renewable (wind, solar, hydro, biomass)": sum(twh[k] for k in ren_names),
                  "fossil (gas, coal, oil)": twh["natural gas"] + twh["coal"] + twh["oil"],
                  "nuclear": twh["nuclear"]},
                 highlight="renewable (wind, solar, hydro, biomass)", label="Generation",
                 title="About a third of generation is renewable"),
        subtitle="Regional grid, annual generation by source, 2025",
        source="data/generation_2025.csv",
    )
    fig.save(TASKS / "06_energy_mix" / "data" / "sent_figure.png")


# 07 gene expression change -------------------------------------------------- #
def gene_change() -> None:
    rng = np.random.default_rng(707)
    fold = {"CDKN1A": 6.2, "MDM2": 3.1, "GADD45A": 2.4, "BAX": 1.8, "TP53I3": 2.9, "SESN1": 2.1,
            "MYC": 0.42, "CCND1": 0.61, "E2F1": 0.55, "MKI67": 0.48, "CDK1": 0.52, "CCNB1": 0.58,
            "GAPDH": 1.02, "ACTB": 0.98, "TBP": 1.04, "HPRT1": 0.97,
            "TP53": 1.1, "VEGFA": 1.3, "HIF1A": 0.9, "STAT3": 1.15, "NFKB1": 1.2, "EGFR": 0.85,
            "SOX2": 1.05, "KRAS": 0.95}
    base = {g: float(rng.uniform(20, 400)) for g in fold}
    rows = []
    for g in fold:  # noqa: PLC0206 - two dicts share the gene keys
        for rep in range(3):
            rows.append([g, "vehicle", rep + 1, float(base[g] * rng.lognormal(0, 0.08))])
            rows.append([g, "drug 24h", rep + 1, float(base[g] * fold[g] * rng.lognormal(0, 0.08))])
    _write("07_gene_change", "expression_tpm.csv", ["gene", "condition", "replicate", "tpm"], rows)
    groups = {**dict.fromkeys(["CDKN1A", "MDM2", "GADD45A", "BAX", "TP53I3", "SESN1"], "p53 target"),
              **dict.fromkeys(["MYC", "CCND1", "E2F1", "MKI67", "CDK1", "CCNB1"], "proliferation"),
              **dict.fromkeys(["GAPDH", "ACTB", "TBP", "HPRT1"], "housekeeping")}
    _write("07_gene_change", "gene_groups.csv", ["gene", "group"],
           [[g, groups.get(g, "other")] for g in fold])
    m = {(g, c): np.mean([r[3] for r in rows if r[0] == g and r[1] == c]) for g in fold
         for c in ("vehicle", "drug 24h")}
    fc = {g: m[(g, "drug 24h")] / m[(g, "vehicle")] for g in fold}
    p53 = float(np.median([fc[g] for g in fold if groups.get(g) == "p53 target"]))
    prolif = float(np.median([fc[g] for g in fold if groups.get(g) == "proliferation"]))
    # The thread asks for groups first, then the biggest single mover (CDKN1A).
    _answer("07_gene_change", "CDKN1A fold change, or the p53-target / proliferation group medians (×)",
            [fc["CDKN1A"], p53, prolif], rel=0.12)


# 08 Hall-Petch -------------------------------------------------------------- #
def hall_petch() -> None:
    rng = np.random.default_rng(808)
    alloys = {"Al-Mg": (90.0, 210.0), "Cu-Zn": (70.0, 330.0), "Ni-Cr": (150.0, 520.0)}
    rows = []
    for a, (s0, k) in alloys.items():
        for i in range(12):
            d = float(np.exp(rng.uniform(np.log(2), np.log(80))))  # µm
            y = s0 + k / np.sqrt(d) + rng.normal(0, 12)
            rows.append([a, f"{a}-{i + 1:02d}", d, float(y)])
    _write("08_hall_petch", "tensile.csv", ["alloy", "specimen", "grain_size_um", "yield_mpa"], rows)
    cu = [r for r in rows if r[0] == "Cu-Zn"]
    x = np.array([r[2] ** -0.5 for r in cu])
    y = np.array([r[3] for r in cu])
    slope = np.polyfit(x, y, 1)[0]
    r_inv = np.corrcoef(x, y)[0, 1]
    r_log = np.corrcoef(np.log10([r[2] for r in cu]), y)[0, 1]
    _answer("08_hall_petch", "Cu-Zn Hall-Petch slope (MPa·µm^½) or its r",
            [slope, r_inv, abs(r_log)], rel=0.06)


# 09 eval matrix ------------------------------------------------------------- #
def eval_matrix() -> None:
    rng = np.random.default_rng(909)
    langs = ["English", "Spanish", "Hindi", "Swahili", "Japanese", "Arabic"]
    tasks = ["QA", "summarise", "translate", "code", "math"]
    base = {"English": 88, "Spanish": 85, "Hindi": 76, "Swahili": 66, "Japanese": 80, "Arabic": 74}
    tadj = {"QA": 0, "summarise": -2, "translate": -4, "code": 1, "math": -6}
    rows = []
    worst = (None, 999.0)
    for lg in langs:
        for t in tasks:
            v = base[lg] + tadj[t] + rng.normal(0, 1.5)
            if lg == "Swahili" and t == "math":
                v -= 14
            rows.append([lg, t, round(float(v), 1)])
            if v < worst[1]:
                worst = ((lg, t), round(float(v), 1))
    _write("09_eval_matrix", "eval_accuracy.csv", ["language", "task", "accuracy_pct"], rows)
    prev_rows = []
    for lg, t, v in rows:
        drop = 16.5 if (lg, t) == ("Swahili", "math") else (5.0 if lg == "Swahili" else 1.5)
        prev_rows.append([lg, t, round(float(v - drop + rng.normal(0, 0.8)), 1)])
    _write("09_eval_matrix", "eval_accuracy_previous.csv", ["language", "task", "accuracy_pct"], prev_rows)
    prev_sw_math = next(v for lg, t, v in prev_rows if (lg, t) == ("Swahili", "math"))
    _answer("09_eval_matrix", "Swahili × math now (%), its gain over the previous checkpoint, or before",
            [worst[1], worst[1] - prev_sw_math, prev_sw_math], abs_=1.0)


# 10 incident ---------------------------------------------------------------- #
def incident() -> None:
    rng = np.random.default_rng(1010)
    start = date(2026, 11, 1)
    services = {"auth": 2e-5, "search": 3e-4, "payments": 8e-5, "uploads": 1.2e-3, "notifications": 4e-4}
    rows = []
    for svc, rate in services.items():
        for d in range(21):
            day = start + timedelta(d)
            v = rate * rng.lognormal(0, 0.25)
            if svc == "payments" and d in (12, 13):
                v = rate * (260 if d == 12 else 40) * rng.lognormal(0, 0.1)
            rows.append([day.isoformat(), svc, float(v)])
    _write("10_incident", "error_rates.csv", ["date", "service", "error_rate"], rows)
    pay = [r[2] for r in rows if r[1] == "payments"]
    before = np.median(pay[:12])
    peak = max(pay)
    _answer("10_incident", "payments peak error rate, or its ratio to the usual rate",
            [peak, peak / before, 100 * peak], rel=0.2)


# Held-out tasks ------------------------------------------------------------ #
def h_survey() -> None:
    rng = np.random.default_rng(1101)
    depts = {"Engineering": 0.71, "Sales": 0.58, "Support": 0.39, "Finance": 0.66,
             "Marketing": 0.62, "Operations": 0.55, "Legal": 0.74}
    levels = ["very dissatisfied", "dissatisfied", "neutral", "satisfied", "very satisfied"]
    rows, pct = [], {}
    for d, p_sat in depts.items():
        n = int(rng.integers(40, 160))
        probs = np.array([(1 - p_sat) * 0.45, (1 - p_sat) * 0.35, (1 - p_sat) * 0.20,
                          p_sat * 0.6, p_sat * 0.4])
        counts = rng.multinomial(n, probs / probs.sum())
        for lv, c in zip(levels, counts):
            rows.append([d, lv, int(c)])
        pct[d] = 100 * (counts[3] + counts[4]) / n
    _write("h1_survey", "engagement_survey.csv", ["department", "response", "count"], rows)
    _answer("h1_survey", "Support's share satisfied or very satisfied (%)", [pct["Support"]], abs_=2.0)


def h_spectra() -> None:
    rng = np.random.default_rng(1102)
    wl = np.arange(400, 701, 5)
    peaks = {"reference": 520.0, "annealed 200 °C": 523.0, "annealed 400 °C": 541.0}
    rows = []
    for s_, mu in peaks.items():
        y = np.exp(-((wl - mu) / 28) ** 2) * (0.9 if s_ == "reference" else 0.8) + 0.04
        y = y + rng.normal(0, 0.006, wl.size)
        rows += [[s_, int(w), float(v)] for w, v in zip(wl, y)]
    _write("h2_spectra", "absorbance.csv", ["sample", "wavelength_nm", "absorbance"], rows)
    meas = {}
    for s_ in peaks:
        ys = [r[2] for r in rows if r[0] == s_]
        meas[s_] = wl[int(np.argmax(ys))]
    shift = meas["annealed 400 °C"] - meas["reference"]
    _answer("h2_spectra", "red shift of the 400 °C sample's peak (nm), or its peak position",
            [shift, meas["annealed 400 °C"]], abs_=5.0)


def h_wait_times() -> None:
    rng = np.random.default_rng(1103)
    rows = []
    med = {}
    for hosp, scale in (("North", 1.0), ("South", 1.45)):
        for level, base in (("1 resuscitation", 4), ("2 emergent", 14), ("3 urgent", 38),
                            ("4 less urgent", 70), ("5 non-urgent", 95)):
            n = int(rng.integers(60, 140))
            waits = rng.lognormal(np.log(base * (scale if level[0] in "345" else 1.0)), 0.5, n)
            rows += [[hosp, level, float(w)] for w in waits]
            med[(hosp, level)] = float(np.median(waits))
    _write("h3_wait_times", "ed_waits.csv", ["hospital", "triage_level", "wait_min"], rows)
    gap = med[("South", "3 urgent")] - med[("North", "3 urgent")]
    _answer("h3_wait_times", "South−North median wait gap at triage level 3 (min), or the two medians",
            [gap, med[("South", "3 urgent")], med[("North", "3 urgent")]], rel=0.15)


def h_scaling() -> None:
    rng = np.random.default_rng(1104)
    compute = np.logspace(18, 22, 9)
    fams = {"dense": (-0.050, 3.9), "mixture-of-experts": (-0.062, 4.3), "recurrent": (-0.031, 3.2)}
    rows = []
    for f, (alpha, a) in fams.items():
        for c in compute:
            loss = a * (c / 1e18) ** alpha * rng.lognormal(0, 0.01)
            rows.append([f, float(c), float(loss)])
    _write("h4_scaling", "loss_vs_compute.csv", ["family", "train_flops", "eval_loss"], rows)
    moe = [r for r in rows if r[0] == "mixture-of-experts"]
    slope = np.polyfit(np.log10([r[1] for r in moe]), np.log10([r[2] for r in moe]), 1)[0]
    _answer("h4_scaling", "mixture-of-experts scaling exponent (log-log slope)", [slope, abs(slope)],
            abs_=0.008)


def h_budget() -> None:
    rng = np.random.default_rng(1105)
    depts = ["Parks", "Libraries", "Roads", "Transit", "Police", "Fire", "Housing",
             "Health", "Schools", "Water", "IT", "Admin"]
    rows = []
    change = {}
    for d in depts:
        before = float(rng.uniform(8, 120))
        pct = {"Libraries": -18.0, "Parks": -11.0, "Housing": 14.0}.get(d, float(rng.normal(2, 2)))
        after = before * (1 + pct / 100)
        rows.append([d, round(before, 1), round(after, 1)])
        change[d] = 100 * (round(after, 1) / round(before, 1) - 1)
    _write("h5_budget", "budget_musd.csv", ["department", "fy2025", "fy2026"], rows)
    _answer("h5_budget", "Libraries' cut (%)", [change["Libraries"]], abs_=1.0)


def main() -> None:
    for fn in (ablation, ab_latency, dose_response, battery, retrofit, energy_mix,
               gene_change, hall_petch, eval_matrix, incident,
               h_survey, h_spectra, h_wait_times, h_scaling, h_budget):
        fn()
    (HERE / "answers.json").write_text(json.dumps(ANSWERS, indent=2) + "\n")
    print(f"wrote data for {len(ANSWERS)} tasks and answers.json")


if __name__ == "__main__":
    main()
