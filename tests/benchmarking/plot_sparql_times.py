#!/usr/bin/env python3
"""Plot median dynamic-SPARQL agent times from test_sparql_models_results.csv.

Place in tests/benchmarking/ and run:
    python plot_sparql_times.py

Bars and dots represent completed OK executions. Labels show OK/total attempts.
"""

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "test_sparql_models_results.csv"
PNG_FILE = BASE_DIR / "benchmark_sparql_times.png"

TESTS = [
    ("geolocated_images", "Images in Duisburg"),
    ("geolocated_counts", "Counts by dataset"),
]
MODEL_LABELS = {
    "qwen3.5-397b-a17b": "Qwen 3.5 (397B)",
    "qwen3-coder-next": "Qwen Coder Next",
    "qwen3.6-35b-a3b": "Qwen 3.6 (35B)",
}


def main():
    if not CSV_FILE.is_file():
        raise FileNotFoundError(f"Missing benchmark file: {CSV_FILE}")

    samples = defaultdict(list)
    attempts = defaultdict(int)
    recognized_tests = dict(TESTS)
    present_models = set()

    with CSV_FILE.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            test_id = row.get("test_id", "")
            model = row.get("model", "")
            if test_id not in recognized_tests or not model:
                continue
            present_models.add(model)
            key = (model, test_id)
            attempts[key] += 1
            if row.get("status") != "OK":
                continue
            try:
                seconds = float(row["elapsed_seconds"])
            except (TypeError, ValueError, KeyError):
                continue
            if math.isfinite(seconds) and seconds > 0:
                samples[key].append(seconds)

    # Stable model order, also showing models with no successful runs.
    models = [m for m in MODEL_LABELS if m in present_models]
    models += sorted(present_models.difference(MODEL_LABELS))
    values = [v for group in samples.values() for v in group]
    if not values:
        raise ValueError("No successful SPARQL benchmark timings in CSV")

    fig, ax = plt.subplots(figsize=(10.0, 4.8))
    bar_width = 0.74 / len(models)
    model_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    for mi, model in enumerate(models):
        color = model_colors[mi % len(model_colors)]
        for ti, (test_id, _) in enumerate(TESTS):
            key = (model, test_id)
            group = samples[key]
            x = ti + (mi - (len(models) - 1) / 2) * bar_width
            if not group:
                if attempts[key]:
                    ax.text(x, 1.4, f"0/{attempts[key]}\nOK", ha="center",
                            va="bottom", fontsize=8)
                continue

            med = median(group)
            ax.bar(x, med - 1, bottom=1, width=bar_width * 0.91,
                   color=color, zorder=2)
            for j, point in enumerate(sorted(group)):
                jitter = (j - (len(group) - 1) / 2) * min(0.027, bar_width / 6)
                ax.scatter(x + jitter, point, s=23, marker="o",
                           facecolor="white", edgecolor=color,
                           linewidth=1.1, zorder=4)
            # Place label above the highest observation to avoid obscuring dots.
            ax.annotate(f"{med:.1f}s\n(n={len(group)}/{attempts[key]})",
                        (x, max(group)), xytext=(0, 8), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8, zorder=5)

    ax.set_yscale("log")
    ax.set_ylim(1, max(values) * 1.85)
    ax.set_yticks([y for y in [2, 5, 10, 20, 50, 100, 300] if y < max(values) * 1.85])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, pos: f"{y:g}"))
    ax.set_ylabel("Median agent execution time (seconds, log scale)")
    ax.set_xticks(range(len(TESTS)), [name for _, name in TESTS])
    ax.grid(axis="y", which="both", alpha=0.22)
    ax.set_axisbelow(True)
    handles = [Patch(facecolor=model_colors[i % len(model_colors)],
                     label=MODEL_LABELS.get(model, model)) for i, model in enumerate(models)]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.19),
              frameon=False, ncol=len(models), fontsize=9)
    fig.tight_layout(pad=1.0)
    fig.savefig(PNG_FILE, dpi=220, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved {PNG_FILE}")
    for test_id, _ in TESTS:
        for model in models:
            group = samples[model, test_id]
            total = attempts[model, test_id]
            if not total:
                continue
            value = f"median={median(group):.1f}s" if group else "no completed timings"
            print(f"  {test_id:<20} {model:<23} {value}; OK={len(group)}/{total}")


if __name__ == "__main__":
    main()
