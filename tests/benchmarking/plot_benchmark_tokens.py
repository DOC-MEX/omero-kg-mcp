#!/usr/bin/env python3
"""Plot median predefined MCP test token usage from the benchmark CSV.

Place in tests/benchmarking/ and run:
    python plot_benchmark_tokens.py

Output: tests/benchmarking/benchmark_tokens.png
"""

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "test_mcp_models_results.csv"
PNG_FILE = BASE_DIR / "benchmark_tokens.png"

TESTS = [
    ("native", "Native"),
    ("combined", "Combined"),
]
MODEL_LABELS = {
    "qwen3.5-397b-a17b": "Qwen 3.5 (397B)",
    "qwen3-coder-next": "Qwen Coder Next",
    "qwen3.6-35b-a3b": "Qwen 3.6 (35B)",
    "deepseek-v4-flash-0731": "DeepSeek V4 Flash",
}


def main():
    if not CSV_FILE.is_file():
        raise FileNotFoundError(f"Missing benchmark file: {CSV_FILE}")

    samples = defaultdict(list)
    attempts = defaultdict(int)
    present_models = set()
    recognized_tests = dict(TESTS)

    with CSV_FILE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
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
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(tokens) and tokens > 0:
                samples[key].append(tokens)

    # Same model ordering as plot_benchmark_times.py; new models are appended.
    models = [m for m in MODEL_LABELS if m in present_models]
    models += sorted(present_models.difference(MODEL_LABELS))
    values = [value for group in samples.values() for value in group]
    if not values:
        raise ValueError("No completed MCP benchmark token measurements in CSV")

    fig, ax = plt.subplots(figsize=(10.0, 4.8))
    bar_width = 0.78 / len(models)
    model_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    maximum = max(values) / 1000.0

    for mi, model in enumerate(models):
        color = model_colors[mi % len(model_colors)]
        for ti, (test_id, _) in enumerate(TESTS):
            key = (model, test_id)
            group = samples[key]
            x = ti + (mi - (len(models) - 1) / 2) * bar_width
            if not group:
                if attempts[key]:
                    ax.text(x, maximum * 0.04, f"0/{attempts[key]}\nOK",
                            ha="center", va="bottom", fontsize=8)
                continue

            med = median(group) / 1000.0
            ax.bar(x, med, width=bar_width * 0.91,
                   color=color, zorder=2)

            for j, point in enumerate(sorted(group)):
                jitter_step = min(0.025, 0.65 * bar_width / max(1, len(group) - 1))
                jitter = (j - (len(group) - 1) / 2) * jitter_step
                ax.scatter(x + jitter, point / 1000.0, s=23, marker="o",
                           facecolor="white", edgecolor=color,
                           linewidth=1.1, zorder=4)

            ax.annotate(f"{med:.1f}k\n(n={len(group)}/{attempts[key]})",
                        (x, max(group) / 1000.0), xytext=(0, 8),
                        textcoords="offset points", ha="center",
                        va="bottom", fontsize=8, zorder=5)

    ax.set_ylim(0, maximum * 1.35)
    ax.set_ylabel("Median total tokens (thousands)")
    ax.set_xticks(range(len(TESTS)), [label for _, label in TESTS])
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)

    handles = [
        Patch(facecolor=model_colors[i % len(model_colors)],
              label=MODEL_LABELS.get(model, model))
        for i, model in enumerate(models)
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.19),
              frameon=False, ncol=min(len(models), 4), fontsize=9)
    fig.tight_layout(pad=1.0)
    fig.savefig(PNG_FILE, dpi=220, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved {PNG_FILE}")
    for test_id, _ in TESTS:
        for model in models:
            total = attempts[model, test_id]
            if not total:
                continue
            group = samples[model, test_id]
            result = (f"median={median(group):.0f} tokens" if group
                      else "no completed token measurements")
            print(f"  {test_id:<13} {model:<23} {result}; OK={len(group)}/{total}")


if __name__ == "__main__":
    main()
