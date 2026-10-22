"""Compare model predictions with hand labels.

Everything is compared on a one second grid (the middle of each second).
Metrics per run:
  - frame accuracy: share of seconds where the predicted step equals the hand label.
    Reported for the raw frame labels and for the smoothed segments from segment.py.
  - per step duration error: |predicted seconds - true seconds| for each step.
  - cycle time error: in seconds and as a percent of the true cycle time.
  - step order distance: edit distance between the predicted and true step sequences,
    divided by the longer sequence (0 = same order, 1 = nothing in common).
    idle and unclear are left out of the sequences.

Usage:
  python src/evaluate.py --check-labels       # check hand label files for mistakes
  python src/evaluate.py                      # evaluate every model that has predictions
Output: outputs/metrics.csv, outputs/step_errors.csv, outputs/confusions.csv,
        outputs/evaluation_summary.md
"""

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import classify  # noqa: E402
import segment  # noqa: E402

STEPS = json.loads(config.STEPS_FILE.read_text(encoding="utf-8"))
LEFT_OUT_OF_ORDER = {"idle", "unclear"}


# ---------- hand labels ----------

def read_hand_labels(path):
    """Hand label segments sorted by start, as dicts with step, start_s, end_s."""
    with open(path, encoding="utf-8") as f:
        rows = [{"step": r["step"].strip(), "start_s": float(r["start_s"]), "end_s": float(r["end_s"])}
                for r in csv.DictReader(f)]
    return sorted(rows, key=lambda r: r["start_s"])


def check_hand_labels(segments):
    """List of problems in one label file: unknown steps, empty segments, overlaps, gaps."""
    problems = []
    for i, s in enumerate(segments, start=1):
        if s["step"] not in STEPS:
            problems.append(f"row {i}: unknown step {s['step']!r}")
        if s["end_s"] <= s["start_s"]:
            problems.append(f"row {i}: end_s ({s['end_s']}) is not after start_s ({s['start_s']})")
    for a, b in zip(segments, segments[1:]):
        if b["start_s"] < a["end_s"] - 1e-9:
            problems.append(f"{a['step']} ending {a['end_s']} overlaps {b['step']} starting {b['start_s']}")
        elif b["start_s"] > a["end_s"] + 1e-9:
            problems.append(f"gap from {a['end_s']} to {b['start_s']} has no label")
    return problems


# ---------- one second grid ----------

def step_at(segments, t):
    """Step whose segment contains time t, or '' if none does."""
    for s in segments:
        if s["start_s"] <= t < s["end_s"]:
            return s["step"]
    return ""


def raw_segments(rows):
    """Unsmoothed predictions as segments (each frame lasts until the next one)."""
    times = [r["t"] for r in rows]
    return segment.to_segments(times, [r["step"] for r in rows], segment.frame_interval(times))


def grid_pairs(true_segments, predicted_segments):
    """(time, true step, predicted step) at the middle of every hand-labeled second."""
    start = true_segments[0]["start_s"]
    end = true_segments[-1]["end_s"]
    pairs = []
    t = int(start) + 0.5
    while t < end:
        true_step = step_at(true_segments, t)
        if true_step:  # skip seconds without a hand label
            pairs.append((t, true_step, step_at(predicted_segments, t)))
        t += 1
    return pairs


def accuracy(pairs):
    return sum(true == pred for _, true, pred in pairs) / len(pairs) if pairs else 0.0


# ---------- other metrics ----------

def step_durations(segments):
    totals = defaultdict(float)
    for s in segments:
        totals[s["step"]] += s["end_s"] - s["start_s"]
    return totals


def edit_distance(a, b):
    """Levenshtein distance between two lists."""
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (item_a != item_b)))
        previous = current
    return previous[-1]


def order_distance(true_segments, predicted_segments):
    true_order = [s["step"] for s in true_segments if s["step"] not in LEFT_OUT_OF_ORDER]
    pred_order = [s["step"] for s in predicted_segments if s["step"] not in LEFT_OUT_OF_ORDER]
    longest = max(len(true_order), len(pred_order))
    return edit_distance(true_order, pred_order) / longest if longest else 0.0


def evaluate_run(true_segments, prediction_rows):
    """All metrics for one run. Returns (metrics dict, per step errors, grid pairs)."""
    predicted = segment.segment_predictions(prediction_rows)
    pairs = grid_pairs(true_segments, predicted)

    true_cycle = segment.run_metrics(true_segments)["cycle_s"]
    pred_cycle = segment.run_metrics(predicted)["cycle_s"]
    cycle_error = abs(pred_cycle - true_cycle)

    true_durations = step_durations(true_segments)
    pred_durations = step_durations(predicted)
    step_errors = {step: abs(pred_durations.get(step, 0) - true_durations.get(step, 0))
                   for step in set(true_durations) | set(pred_durations)}

    metrics = {
        "seconds_compared": len(pairs),
        "frame_accuracy_raw": round(accuracy(grid_pairs(true_segments, raw_segments(prediction_rows))), 4),
        "frame_accuracy": round(accuracy(pairs), 4),
        "true_cycle_s": round(true_cycle, 3),
        "pred_cycle_s": round(pred_cycle, 3),
        "cycle_abs_error_s": round(cycle_error, 3),
        "cycle_pct_error": round(100 * cycle_error / true_cycle, 2) if true_cycle else "",
        "step_duration_mae_s": round(statistics.mean(step_errors.values()), 3) if step_errors else 0,
        "order_distance": round(order_distance(true_segments, predicted), 4),
    }
    return metrics, step_errors, pairs


# ---------- confusions ----------

def confusion_examples(pairs_by_run):
    """For each (true, predicted) mismatch: total seconds and the time spans where it happened."""
    seconds = Counter()
    spans = defaultdict(list)
    for run, pairs in pairs_by_run.items():
        for t, true, pred in pairs:
            if true == pred:
                continue
            key = (true, pred or "(no prediction)")
            seconds[key] += 1
            span_list = spans[key]
            if span_list and span_list[-1][0] == run and abs(span_list[-1][2] - (t - 0.5)) < 1e-9:
                span_list[-1][2] = t + 0.5
            else:
                span_list.append([run, t - 0.5, t + 0.5])
    return seconds, spans


def frame_files_in(run, start, end):
    """Frame images that fall inside a time span, so the failure can be looked at."""
    files = segment.frame_file_lookup(run)
    return [path for t, path in sorted(files.items()) if start <= t < end]


# ---------- whole study ----------

def models_with_predictions():
    if not config.PREDICTIONS_DIR.exists():
        return []
    return sorted(p.name for p in config.PREDICTIONS_DIR.iterdir() if p.is_dir() and any(p.glob("run_*.csv")))


def evaluate_model(model):
    """Evaluate every run that has both hand labels and predictions for this model."""
    rows, step_rows, pairs_by_run = [], [], {}
    for pred_path in sorted((config.PREDICTIONS_DIR / model).glob("run_*.csv")):
        label_path = config.LABELS_DIR / pred_path.name
        if not label_path.exists():
            continue
        true_segments = read_hand_labels(label_path)
        problems = check_hand_labels(true_segments)
        if problems:
            print(f"Skipping {label_path.name}: fix the label file first ({problems[0]})")
            continue

        metrics, step_errors, pairs = evaluate_run(true_segments, segment.read_predictions(pred_path))
        pairs_by_run[pred_path.stem] = pairs

        frames_dir = config.FRAMES_DIR / pred_path.stem
        usage = classify.run_usage(model, frames_dir) if (frames_dir / "frames.csv").exists() else None
        cost = round(classify.usage_cost(model, usage), 5) if usage and model in config.PRICES else ""

        rows.append({"model": model, "run": pred_path.stem, **metrics, "cost_usd": cost})
        step_rows += [(model, pred_path.stem, step, round(err, 3)) for step, err in sorted(step_errors.items())]
    return rows, step_rows, pairs_by_run


def mean_of(rows, key):
    values = [r[key] for r in rows if r[key] != ""]
    return statistics.mean(values) if values else None


def fmt(value, digits=1, suffix=""):
    return "{n/a}" if value is None else f"{value:.{digits}f}{suffix}"


def write_summary(all_rows, all_step_rows, confusions_by_model, path):
    """Markdown summary with n next to every number."""
    lines = ["# Evaluation summary", "",
             "Predictions compared with hand labels on a one second grid. "
             "This is a small study: read every number together with its n.", ""]

    lines += ["## Models", "",
              "| Model | n runs | Seconds compared | Accuracy (raw frames) | Accuracy (smoothed) "
              "| Cycle time MAE | Cycle time MAE % | Step duration MAE | Step order distance | Cost per run |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for model, rows in all_rows.items():
        cost = mean_of(rows, "cost_usd")
        lines.append(
            f"| {model} | {len(rows)} | {sum(r['seconds_compared'] for r in rows)} "
            f"| {fmt(100 * mean_of(rows, 'frame_accuracy_raw'), 1, '%')} "
            f"| {fmt(100 * mean_of(rows, 'frame_accuracy'), 1, '%')} "
            f"| {fmt(mean_of(rows, 'cycle_abs_error_s'), 1, ' s')} "
            f"| {fmt(mean_of(rows, 'cycle_pct_error'), 1, '%')} "
            f"| {fmt(mean_of(rows, 'step_duration_mae_s'), 1, ' s')} "
            f"| {fmt(mean_of(rows, 'order_distance'), 3)} "
            f"| {'{n/a}' if cost is None else f'${cost:.4f}'} |")
    lines += ["", "Accuracy is the mean over runs. MAE means mean absolute error. "
              "Step order distance runs from 0 (same order) to 1.", ""]

    for model, step_rows in all_step_rows.items():
        by_step = defaultdict(list)
        for _, _, step, err in step_rows:
            by_step[step].append(err)
        lines += [f"## Duration error per step: {model}", "",
                  "| Step | n runs | MAE (s) |", "|---|---|---|"]
        for step in STEPS:
            if step in by_step:
                lines.append(f"| {step} | {len(by_step[step])} | {statistics.mean(by_step[step]):.1f} |")
        lines.append("")

    for model, (seconds, spans) in confusions_by_model.items():
        lines += [f"## Most common confusions: {model}", "",
                  "| True step | Predicted as | Seconds | Example (run, time) |", "|---|---|---|---|"]
        for (true, pred), count in seconds.most_common(8):
            run, start, end = max(spans[(true, pred)], key=lambda s: s[2] - s[1])
            lines.append(f"| {true} | {pred} | {count} | {run}, {start:.0f} to {end:.0f} s |")
        lines += ["", "Frames for each example are listed in outputs/confusions.csv.", ""]

    lines += ["## Why the model fails", "",
              "{To be written after looking at the example frames above. "
              "Describe which steps get confused and why, using the real examples.}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_evaluation():
    models = models_with_predictions()
    if not models:
        raise SystemExit("No predictions found. Run src/classify.py first.")

    all_rows, all_step_rows, confusions_by_model, confusion_rows = {}, {}, {}, []
    for model in models:
        rows, step_rows, pairs_by_run = evaluate_model(model)
        if not rows:
            print(f"{model}: no runs with both predictions and hand labels")
            continue
        all_rows[model], all_step_rows[model] = rows, step_rows
        seconds, spans = confusion_examples(pairs_by_run)
        confusions_by_model[model] = (seconds, spans)
        for (true, pred), count in seconds.most_common():
            for run, start, end in spans[(true, pred)]:
                confusion_rows.append((model, true, pred, count, run, start, end,
                                       " ".join(frame_files_in(run, start, end))))

    if not all_rows:
        raise SystemExit("Nothing to evaluate yet.")

    out = config.OUTPUTS_DIR
    out.mkdir(exist_ok=True)
    flat = [r for rows in all_rows.values() for r in rows]
    segment.write_csv(out / "metrics.csv", list(flat[0].keys()), [list(r.values()) for r in flat])
    segment.write_csv(out / "step_errors.csv", ["model", "run", "step", "abs_error_s"],
                      [r for rows in all_step_rows.values() for r in rows])
    segment.write_csv(out / "confusions.csv", ["model", "true_step", "predicted_step", "total_seconds",
                                                "run", "span_start_s", "span_end_s", "frame_files"],
                      confusion_rows)
    write_summary(all_rows, all_step_rows, confusions_by_model, out / "evaluation_summary.md")

    for model, rows in all_rows.items():
        print(f"{model}: n = {len(rows)} runs, accuracy {100 * mean_of(rows, 'frame_accuracy'):.1f}% "
              f"(raw {100 * mean_of(rows, 'frame_accuracy_raw'):.1f}%), "
              f"cycle time MAE {mean_of(rows, 'cycle_abs_error_s'):.1f} s")
    print(f"Wrote metrics.csv, step_errors.csv, confusions.csv and evaluation_summary.md to {out}")


def check_all_labels():
    files = sorted(config.LABELS_DIR.glob("run_*.csv"))
    if not files:
        print("No label files yet (expected data/labels/run_01.csv and so on).")
    for path in files:
        try:
            problems = check_hand_labels(read_hand_labels(path))
        except (KeyError, ValueError) as error:
            problems = [f"could not read file: {error}"]
        print(f"{path.name}: " + ("OK" if not problems else ""))
        for problem in problems:
            print(f"  - {problem}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate predictions against hand labels.")
    parser.add_argument("--check-labels", action="store_true", help="only check the hand label files")
    args = parser.parse_args()
    if args.check_labels:
        check_all_labels()
    else:
        run_evaluation()


if __name__ == "__main__":
    main()
