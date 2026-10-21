#!/usr/bin/env python3
"""Plot median dynamic-SPARQL token usage from test_sparql_models_results.csv.

Place in tests/benchmarking/:
    python plot_sparql_tokens.py

Output: tests/benchmarking/benchmark_sparql_tokens.png
Bars and dots represent completed OK executions with valid token usage.
Labels show valid OK measurements / total attempts (n=5/6, for example).
"""

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "test_sparql_models_results.csv"
PNG_FILE = BASE_DIR / "benchmark_sparql_tokens.png"

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
                tokens = float(row["total_tokens"])
            except (TypeError, ValueError, KeyError):
                continue
            if math.isfinite(tokens) and tokens > 0:
                samples[key].append(tokens)

    # Match model order (and therefore colors) in plot_sparql_times.py.
    models = [m for m in MODEL_LABELS if m in present_models]
    models += sorted(present_models.difference(MODEL_LABELS))
    values = [v for group in samples.values() for v in group]
    if not values:
        raise ValueError("No completed SPARQL benchmark token measurements in CSV")

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
                    ax.text(x, max(values) / 1000 * 0.035,
                            f"0/{attempts[key]}\nvalid", ha="center",
                            va="bottom", fontsize=8)
                continue

            med = median(group) / 1000
            ax.bar(x, med, width=bar_width * 0.91, color=color, zorder=2)

            for j, point in enumerate(sorted(group)):
                jitter = (j - (len(group) - 1) / 2) * min(0.027, bar_width / 6)
                ax.scatter(x + jitter, point / 1000, s=23, marker="o",
                           facecolor="white", edgecolor=color,
                           linewidth=1.1, zorder=4)

            # Above the highest observation, keeping labels clear of data points.
            ax.annotate(f"{med:.1f}k\n(n={len(group)}/{attempts[key]})",
                        (x, max(group) / 1000), xytext=(0, 8),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=8, zorder=5)

    ax.set_ylim(0, max(values) / 1000 * 1.43)
    ax.set_ylabel("Median total tokens (thousands)")
    ax.set_xticks(range(len(TESTS)), [name for _, name in TESTS])
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)

    handles = [
        Patch(facecolor=model_colors[i % len(model_colors)],
              label=MODEL_LABELS.get(model, model))
        for i, model in enumerate(models)
    ]
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
            value = (f"median={median(group):.0f} total tokens"
                     if group else "no valid OK token measurements")
            print(f"  {test_id:<20} {model:<23} {value}; OK with tokens={len(group)}/{total}")


if __name__ == "__main__":
    main()
