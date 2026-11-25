"""Scientific chat figures made with ``mint.explain`` (all data synthetic).

Each example answers a question a researcher would ask an agent about their own
results: is the effect outside the noise, which candidate do I take forward,
where is the optimum, does the perturbation matter. They exercise the parts of
``mint.explain`` that scientific data needs: stated intervals, raw replicates,
log scales, very small numbers, Unicode units and one colour per entity across
panels. Run directly to write PNGs and their reproducible JSON specs to
``gallery/output/explain_science/``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import mintfig as mint

SOURCE = "synthetic example data"


def ablation() -> mint.Explanation:
    """Is the effect outside seed noise? Intervals that are named, then the curves."""
    rng = np.random.default_rng(7)
    steps = np.arange(0, 2001, 250)
    finals = {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69}
    curves, bands = {}, {}
    for name, final in finals.items():
        tau = 420.0 if name == "no fine-tuning" else 300.0
        mean = final * (1 - np.exp(-steps / tau))
        curves[name] = (mean + rng.normal(0, 0.003, steps.size)).round(3).tolist()
        bands[name] = 0.02
    return mint.explain(
        "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
        mint.compare(
            {**finals, "no augmentation": 0.80, "smaller encoder": 0.78},
            error={
                "full model": (0.80, 0.84),
                "no retrieval": (0.71, 0.77),
                "no fine-tuning": (0.66, 0.72),
                "no augmentation": (0.78, 0.82),
                "smaller encoder": (0.75, 0.81),
            },
            error_label="95% CI, 5 seeds",
            title="Both losses are outside seed noise",
            label="Test accuracy",
            highlight=["no retrieval", "no fine-tuning"],
        ),
        mint.trend(
            steps.tolist(),
            curves,
            band=bands,
            band_label="± 1 s.d.",
            title="The gap opens in the first 500 steps",
            label="Validation accuracy",
            x_label="Training step",
        ),
        source=SOURCE,
    )


def dose_response() -> mint.Explanation:
    """Which compound goes forward? Replicates on a log dose axis, same colours in both panels."""
    rng = np.random.default_rng(11)
    doses = [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30]
    compounds = {"BX-204": (0.011, 1.3, 0.9), "BX-101": (0.08, 1.1, 40.0), "BX-317": (0.9, 0.9, 500.0)}
    inhibition, viability = {}, {}
    for name, (ic50, hill, tox50) in compounds.items():
        inhibition[name] = [
            (100 / (1 + (ic50 / d) ** hill) + rng.normal(0, 4, 3)).round(1).tolist() for d in doses
        ]
        viability[name] = [
            (100 / (1 + (d / tox50) ** 1.5) + rng.normal(0, 3, 3)).round(1).tolist() for d in doses
        ]
    return mint.explain(
        "BX-204 inhibits the kinase near 10 nM, about 100x below the dose that kills cells",
        mint.trend(
            doses,
            points=inhibition,
            log_x=True,
            end_values=False,
            title="BX-204 is the most potent",
            label="Kinase inhibition",
            unit="%",
            x_label="Dose (µM)",
            highlight="BX-204",
            reference=(50, "half-maximal"),
        ),
        mint.trend(
            doses,
            points=viability,
            log_x=True,
            end_values=False,
            title="Its toxicity starts near 1 µM",
            label="Cell viability",
            unit="%",
            x_label="Dose (µM)",
            highlight="BX-204",
            reference=(50, "half dead"),
        ),
        subtitle="Triplicate wells at ten doses; lines are means, dots are wells",
        source=SOURCE,
    )


def doping_optimum() -> mint.Explanation:
    """Where is the optimum? Values spanning decades, small numbers, an inherent order."""
    k_b = 8.617e-5
    temps = np.array([80, 100, 120, 150, 180, 210, 240, 270, 300, 330], dtype=float)
    levels = {"0 at.%": (2e-2, 0.21), "0.5 at.%": (5e-2, 0.17), "1 at.%": (9e-2, 0.12),
              "2 at.%": (1.4e-1, 0.08), "4 at.%": (6e-2, 0.15)}  # fmt: skip
    sigma_300 = {name: s0 * np.exp(-ea / (k_b * 300.0)) for name, (s0, ea) in levels.items()}
    arrhenius = {
        name: (s0 * np.exp(-ea / (k_b * temps))).tolist() for name, (s0, ea) in levels.items()
    }
    return mint.explain(
        "Conductivity peaks at 2 at.% Li, three decades above the undoped film",
        mint.compare(
            sigma_300,
            log=True,
            sort=False,
            title="The optimum is at 2 at.%",
            label="Conductivity at 300 K",
            unit="S/cm",
            highlight="2 at.%",
        ),
        mint.trend(
            (1000.0 / temps).round(2).tolist(),
            arrhenius,
            log=True,
            end_values=False,
            title="Every film is thermally activated",
            label="Conductivity",
            unit="S/cm",
            x_label="1000/T (K⁻¹)",
            highlight="2 at.%",
        ),
        mint.compare(
            {name: ea * 1000 for name, (_, ea) in levels.items()},
            sort=False,
            title="The barrier is lowest there too",
            label="Activation energy",
            unit="meV",
            highlight="2 at.%",
        ),
        subtitle="Li-doped NiO films, four-probe conductivity, 80–330 K",
        source=SOURCE,
    )


def knockout() -> mint.Explanation:
    """Does the perturbation matter? Every observation at small n, then the mechanism."""
    rng = np.random.default_rng(3)
    groups = {
        "wild type": rng.normal(12.0, 1.6, 9).round(1).tolist(),
        "knockout": rng.normal(7.2, 1.8, 8).round(1).tolist(),
        "rescue": rng.normal(11.3, 1.7, 9).round(1).tolist(),
    }
    area, speed, label = [], [], []
    for name, slope in {"wild type": 0.030, "knockout": 0.004}.items():
        a = rng.uniform(180, 520, 14)
        area += a.round(0).tolist()
        speed += (2.0 + slope * a + rng.normal(0, 0.9, 14)).round(2).tolist()
        label += [name] * 14
    return mint.explain(
        "Knocking out the gene cuts migration distance by about 40%, and the rescue restores it",
        mint.distribution(
            groups,
            title="Each dot is one cell",
            label="Migration distance in 6 h",
            unit="µm",
            highlight="knockout",
        ),
        mint.relate(
            area,
            speed,
            groups=label,
            fit=True,
            x_label="Cell area (µm²)",
            y_label="Speed (µm/h)",
            title="Larger knockout cells do not speed up",
            highlight="knockout",
        ),
        source=SOURCE,
    )


def descriptor_correlations() -> mint.Explanation:
    """Which variables go together? A signed matrix with a number in every cell."""
    names = ["band gap", "formation energy", "density", "bulk modulus", "volume per atom"]
    corr = np.array(
        [
            [1.00, -0.42, -0.31, 0.12, 0.28],
            [-0.42, 1.00, 0.08, -0.36, 0.11],
            [-0.31, 0.08, 1.00, 0.74, -0.81],
            [0.12, -0.36, 0.74, 1.00, -0.66],
            [0.28, 0.11, -0.81, -0.66, 1.00],
        ]
    )
    return mint.explain(
        "Density and volume per atom carry the same information (r = −0.81)",
        mint.matrix(
            corr.tolist(),
            rows=names,
            cols=names,
            diverging=True,
            label="Pearson r across 412 compounds",
            fmt=".2f",
            highlight=("density", "volume per atom"),
        ),
        source=SOURCE,
    )


EXAMPLES = {
    "ablation": ablation,
    "dose_response": dose_response,
    "doping_optimum": doping_optimum,
    "knockout": knockout,
    "descriptor_correlations": descriptor_correlations,
}


def build() -> mint.Explanation:
    """Entry point for ``mintfig run gallery/explain_science_examples.py --journal screen``."""
    return ablation()


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "output" / "explain_science"
    for name, make in EXAMPLES.items():
        summary = make().save(out_dir / f"{name}.png", write_spec=True)
        print(f"{name}: ok={summary['ok']} {summary['size_px']} issues={summary['issues']}")
