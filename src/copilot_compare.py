"""Compare manual and AI assisted invoice entry times.

Reads data/copilot_timing.csv (run_id, condition, total_seconds, errors).
Condition is "manual" or the assisted tool ("copilot", or "claude" if Copilot was not available).
Each assisted condition is compared with manual.

For each condition: n, mean, median and standard deviation of total_seconds, and mean errors.
For each comparison: difference in mean seconds (assisted minus manual) and a bootstrap 95%
confidence interval. If the interval includes zero, the result says there is no clear difference.

Usage: python src/copilot_compare.py
Output: outputs/copilot_comparison.md
"""

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

TIMING_FILE = config.ROOT / "data" / "copilot_timing.csv"
BOOTSTRAP_SAMPLES = 10_000
SEED = 42
MIN_RUNS = 8


def load_timings(path=TIMING_FILE):
    return clean_timings(pd.read_csv(path))


def clean_timings(data):
    """Lowercase condition names so "Copilot" and "copilot " count as the same."""
    data = data.copy()
    data["condition"] = data["condition"].str.strip().str.lower()
    return data


def describe(values):
    """n, mean, median and sample standard deviation of a list of numbers."""
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def bootstrap_ci(assisted, manual, samples=BOOTSTRAP_SAMPLES, seed=SEED):
    """95% interval for mean(assisted) - mean(manual): resample each group with replacement."""
    rng = np.random.default_rng(seed)
    assisted, manual = np.asarray(assisted, float), np.asarray(manual, float)
    assisted_means = rng.choice(assisted, (samples, len(assisted))).mean(axis=1)
    manual_means = rng.choice(manual, (samples, len(manual))).mean(axis=1)
    low, high = np.percentile(assisted_means - manual_means, [2.5, 97.5])
    return float(low), float(high)


def conclusion(name, difference, low, high):
    """Plain sentence that does not oversell a small sample."""
    if low <= 0 <= high:
        return (f"No clear difference: the 95% interval ({low:+.1f} to {high:+.1f} s) includes zero, "
                f"so this sample cannot tell whether {name} is faster or slower than manual entry.")
    direction = "faster" if difference < 0 else "slower"
    return (f"{name.capitalize()} assisted runs were {abs(difference):.1f} s {direction} on average than manual "
            f"(95% interval {abs(high if difference < 0 else low):.1f} to {abs(low if difference < 0 else high):.1f} s "
            f"{direction}). With a sample this small, treat this as a first signal, not a firm result.")


def compare(data):
    """Stats per condition and one comparison per assisted condition."""
    if "manual" not in set(data["condition"]):
        raise SystemExit("No manual runs in the timing file.")
    stats = {}
    for condition, group in data.groupby("condition"):
        stats[condition] = {**describe(group["total_seconds"].tolist()),
                            "mean_errors": float(group["errors"].mean())}

    manual = data.loc[data["condition"] == "manual", "total_seconds"].tolist()
    comparisons = []
    for condition in sorted(c for c in stats if c != "manual"):
        assisted = data.loc[data["condition"] == condition, "total_seconds"].tolist()
        difference = statistics.mean(assisted) - statistics.mean(manual)
        low, high = bootstrap_ci(assisted, manual)
        comparisons.append({"condition": condition, "difference": difference, "low": low, "high": high,
                            "conclusion": conclusion(condition, difference, low, high)})
    return stats, comparisons


def write_report(stats, comparisons, path):
    lines = ["# Manual vs AI assisted invoice entry", "",
             "Times from data/copilot_timing.csv, one row per timed run. "
             "This is a small study: read every number with its n.", "",
             "| Condition | n | Mean (s) | Median (s) | SD (s) | Mean errors per run |",
             "|---|---|---|---|---|---|"]
    for condition, s in sorted(stats.items(), key=lambda item: item[0] != "manual"):
        lines.append(f"| {condition} | {s['n']} | {s['mean']:.1f} | {s['median']:.1f} | {s['sd']:.1f} "
                     f"| {s['mean_errors']:.2f} |")
    lines.append("")

    for c in comparisons:
        lines += [f"## {c['condition']} vs manual", "",
                  f"- Difference in means ({c['condition']} minus manual): {c['difference']:+.1f} s",
                  f"- Bootstrap 95% confidence interval: {c['low']:+.1f} to {c['high']:+.1f} s "
                  f"({BOOTSTRAP_SAMPLES:,} resamples, seed {SEED})",
                  f"- n = {stats[c['condition']]['n']} {c['condition']} runs and {stats['manual']['n']} manual runs",
                  "", c["conclusion"], ""]
        if c["condition"] == "claude":
            lines += ["Note: Microsoft Copilot was not available, so Claude was used as the assistant.", ""]

    small = [name for name, s in stats.items() if s["n"] < MIN_RUNS]
    if small:
        lines += [f"Warning: fewer than {MIN_RUNS} runs for {', '.join(small)}. The interval is very rough.", ""]

    lines += ["## How it was measured", "",
              "Stopwatch from opening the invoice to the green Saved message, including error fixes. "
              "Errors are the number of red error messages in a run. Dummy invoices only. "
              "Full protocol: docs/copilot_protocol.md.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compare manual and AI assisted entry times.")
    parser.add_argument("--file", default=str(TIMING_FILE))
    args = parser.parse_args()

    data = load_timings(args.file)
    if data.empty:
        raise SystemExit(f"{args.file} has no runs yet. See docs/copilot_protocol.md.")
    stats, comparisons = compare(data)
    out_path = config.OUTPUTS_DIR / "copilot_comparison.md"
    write_report(stats, comparisons, out_path)

    for condition, s in stats.items():
        print(f"{condition}: n = {s['n']}, mean {s['mean']:.1f} s, median {s['median']:.1f} s, SD {s['sd']:.1f} s")
    for c in comparisons:
        print(c["conclusion"])
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
