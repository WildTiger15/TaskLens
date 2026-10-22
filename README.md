# TaskLens

AI assisted time study from screen recordings.

TaskLens takes screen recordings of a repeatable office task, uses a Claude vision model to split each recording into timed steps, checks that against hand labels, and turns the result into a time study: cycle, touch, wait and rework time per run, with Excel and Power BI dashboards.

**Status: in progress.** The pipeline code and tests are in place. Recordings, hand labels and results are being collected, so there are no measured numbers yet. Results will be added here, each with its sample size (n), once they come from real runs.

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

## How to run

Python 3.11 or newer.

```bash
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

# 6. Dashboard
python src/dashboard.py

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

{Results table with n, added after real runs.}
