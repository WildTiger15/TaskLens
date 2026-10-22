# TaskLens

AI assisted time study from screen recordings.

TaskLens takes screen recordings of a repeatable office task, uses a Claude vision model to split each recording into timed steps, checks that against hand labels, and turns the result into a time study: cycle, touch, wait and rework time per run, with Excel and Power BI dashboards.

**Status: in progress.** The pipeline code, tests and write ups are in place. Recordings, hand labels and timings are being collected, so the results below are still placeholders. Each will be filled in with its sample size (n) from real runs.

## The task being studied

A self contained invoice data entry task with dummy data only:

1. Open a generated invoice PDF and read the vendor, date and total.
2. Switch to a small local web form and type the three fields.
3. Submit, and fix the form if it shows an error (bad date format, wrong total).

Step labels are fixed in [steps.json](steps.json): `open_invoice`, `read_fields`, `switch_to_form`, `type_vendor`, `type_date`, `type_total`, `submit`, `fix_error`, `idle`, `unclear`.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Make the dummy task | `tasks/invoice_entry/generate_invoices.py`, `form.html` | 20 invoice PDFs and a local form |
| 2. Sample frames | `src/frames.py` | one frame every 2 s, with timestamps |
| 3. Classify frames | `src/classify.py` | a step label and confidence per frame |
| 4. Segment and measure | `src/segment.py` | step segments, time study metrics, low confidence review list |
| 5. Evaluate | `src/evaluate.py` | accuracy against hand labels, per model |
| 6. Dashboard | `src/dashboard.py` | Excel workbook and Power BI ready CSVs |
| 7. Manual vs AI assisted | `src/copilot_compare.py` | timing comparison with a bootstrap 95% interval |

## How to run

Python 3.11 or newer. Steps 3 and later need an Anthropic API key in the `ANTHROPIC_API_KEY` environment variable. Steps 1, 2 and the tests do not.

```bash
git clone https://github.com/WildTiger15/TaskLens.git
cd TaskLens
pip install -r requirements.txt

# 1. Dummy invoices and the form (open http://localhost:8000/form.html)
python tasks/invoice_entry/generate_invoices.py
python -m http.server 8000 --directory tasks/invoice_entry

# 2. Frames from your recordings in data/recordings/run_01.mp4, run_02.mp4, ...
python src/frames.py --all

# 3. Classify (needs ANTHROPIC_API_KEY; responses are cached in data/cache)
python src/classify.py --all
python src/classify.py --all --model claude-haiku-5-5

# 4. Segments and time study metrics
python src/segment.py

# 5. Evaluation against hand labels in data/labels/run_01.csv, ...
python src/evaluate.py --check-labels
python src/evaluate.py

# 6. Dashboard (Power BI steps in docs/powerbi_guide.md)
python src/dashboard.py

# 7. Manual vs AI assisted timing (protocol in docs/copilot_protocol.md)
python src/copilot_compare.py

# Tests
python -m pytest
```

Settings such as the model, frame interval and confidence threshold are in [config.py](config.py).

## Folder map

```
config.py, steps.json      settings and the step vocabulary
tasks/invoice_entry/       dummy invoice generator and the entry form
src/                       pipeline scripts
tests/                     pytest checks
data/labels/               hand labels (TEMPLATE.csv shows the format)
data/recordings, frames, cache    local only, not in the repo
outputs/                   metrics, dashboard and Power BI CSVs
docs/                      use case, guides
```

## Data and privacy

All invoices are generated with Faker from a fixed seed. Recordings show only the author's own screen doing the dummy task, and they stay local (recordings, frames and API cache are excluded from the repo). No API keys are stored in the code; the Claude client reads `ANTHROPIC_API_KEY` from the environment.

## Results

Numbers in curly braces are filled in from the files named in each row after real runs. Every number comes from running this code on the author's recordings.

| Result | Value | n | Source |
|---|---|---|---|
| Step accuracy, Claude Sonnet 5.5 | {X}% of seconds | {n} recordings | outputs/evaluation_summary.md |
| Step accuracy, Claude Haiku 5.5 | {X}% of seconds | {n} recordings | outputs/evaluation_summary.md |
| Cycle time error (Sonnet) | {X} s ({X}%) | {n} recordings | outputs/evaluation_summary.md |
| Cost per recording | {Sonnet} / {Haiku} | {n} recordings | outputs/evaluation_summary.md |
| Mean cycle time | {X} s (SD {X} s) | {n} runs | dashboard, Variation sheet |
| Bottleneck step | {step}, {X} s per run | {n} runs | dashboard, Steps sheet |
| Frames flagged for review | {X} of {Y} | {n} recordings | outputs/claude-sonnet-5-5/review_list.csv |
| Copilot vs manual task time | {difference} s (95% CI {low} to {high}) | {n} runs each | outputs/copilot_comparison.md |

Dashboard: `outputs/tasklens_dashboard.xlsx` (Excel) and `outputs/powerbi/` (Power BI, see [docs/powerbi_guide.md](docs/powerbi_guide.md)).

{Dashboard screenshot: save as docs/dashboard.png after real runs and show it here with `![Dashboard](docs/dashboard.png)`.}

Write ups: [AI use case](docs/use_case.md), [enablement guide](docs/enablement_guide.md), [timing protocol](docs/copilot_protocol.md).

## Limitations

- **Small study.** One person, one task, {n} recordings. The results show the method works here; they do not show how well it works on other tasks or people.
- **Same person recorded and labeled.** The hand labels are careful but not checked by a second labeler, so the ground truth has its own error.
- **2 second sampling.** Steps shorter than about 2 seconds (a quick submit click) can be missed or cut short. Sampling every second would help, at twice the API cost.
- **No fixed temperature.** The models used do not accept a custom temperature. Results are made repeatable by caching every answer on disk, not by the model itself.
- **Costs are estimates.** Cost per recording uses real token counts but list prices from October 2026 (config.py); some cache prices use standard multipliers.
- **Timing comparison.** Manual and Copilot runs were timed with a stopwatch by the same person. Practice effects are reduced by alternating conditions, not removed.
- **Dummy task.** The invoices and form are simple and clean. Real documents and real systems are messier.
