# Project Plan: TaskLens, an AI assisted time study from screen recordings

## Why this exists (read first)

I am applying to the Mitacs "Intern, AI and Industrial Engineering Co op" (Spring 2027, fully remote). The application deadline is November 4, 2026 at 11:00 AM, and it needs a resume, cover letter and transcript. This project is the main proof of fit for the application. The posting asks for two things, and this project covers both in one build:

1. AI enablement: document AI use cases (problem, solution, benefits, risks, steps, success measures), write practical guides and training material, and evaluate Microsoft Copilot and similar tools responsibly.
2. Operational analytics: time studies, cycle, touch, wait and rework times, process variation, Excel or Power BI dashboards, and "evaluating AI assisted approaches to extract insights from operational data and screen recordings."

The project: record a repeatable admin task on screen, use a vision model to break each recording into steps with timestamps, measure how accurate that is against hand labels, turn the results into a time study dashboard, and compare doing the task manually versus with Copilot help.

## Ground rules for Claude Code (follow these strictly)

* Work one milestone at a time. Finish it, run it, show me the output, then wait for me to say continue.
* Never invent numbers. Every metric in the README, docs or resume bullets must come from a real run of the code on my real recordings. If a number does not exist yet, leave a clear placeholder in curly braces.
* Always report the sample size (n) next to any metric. This is a small study, so say so plainly.
* Use dummy data only. No real personal, financial or confidential information anywhere. Record only my own screen.
* Keep the code simple and readable. Plain variable names, small functions, short comments. No clever tricks. Prefer the standard library and a few well known packages.
* Cache every API result on disk so reruns cost nothing. Before any run that could make more than 100 API calls, tell me the estimated call count first and wait for approval.
* Never hardcode an API key. Read ANTHROPIC_API_KEY from the environment.
* Commit after each milestone with a clear message.
* If something in this plan is unclear or a better choice exists, ask me before building.

## Tech choices

* Python 3.11 or newer, cross platform (I may be on Mac or Windows).
* Packages: opencv_python, anthropic, pandas, numpy, openpyxl, reportlab, faker, pytest.
* Vision model: Claude API with images. Put the model name in one constant called MODEL in config.py. Default to claude-sonnet-5-5, and test claude-haiku-5-5 as a cheaper option, reporting the accuracy difference.
* Dashboard: Excel via openpyxl with native charts, plus Power BI (required) fed from clean CSV exports.

## The task being studied

A self contained invoice data entry task, so I can record it repeatedly with no real data:

* tasks/invoice_entry/generate_invoices.py creates 20 dummy invoice PDFs (vendor, date, invoice number, line items, total) using reportlab and faker. Use a fixed random seed so they are reproducible.
* tasks/invoice_entry/form.html is a small local web form (vendor, date, total, submit) served with python's built in http.server. The form validates input and shows an error on a bad date format or a mismatched total, so natural rework happens.
* The task: open an invoice PDF, read the vendor, date and total, switch to the form, type the three fields, submit, and fix an error if one appears.

## Step vocabulary (steps.json)

Use exactly these labels, so predictions and my hand labels match:

* open_invoice
* read_fields
* switch_to_form
* type_vendor
* type_date
* type_total
* submit
* fix_error
* idle
* unclear

## Folder structure

```
tasklens/
  PLAN.md
  README.md
  config.py
  steps.json
  requirements.txt
  tasks/invoice_entry/        generate_invoices.py, form.html
  data/recordings/            run_01.mp4 ... (I record these, gitignored)
  data/labels/                run_01.csv ... (my hand labels)
  data/frames/                sampled frames (gitignored)
  data/predictions/           model output per run
  data/cache/                 cached API responses (gitignored)
  src/
    frames.py
    classify.py
    segment.py
    evaluate.py
    dashboard.py
    copilot_compare.py
  tests/
  outputs/                    metrics csv, dashboard xlsx, charts
  docs/
    use_case.md
    enablement_guide.md
```

## Milestones

### Milestone 1: scaffold and the task (target Oct 22)

* Create the folder structure, requirements.txt, config.py, steps.json and a .gitignore that excludes recordings, frames, cache and any key files.
* Build generate_invoices.py and form.html. Run them and show me the form working.
* Write a labeling template: data/labels/TEMPLATE.csv with the columns step,start_s,end_s.
* Done when: I can open an invoice, fill the form, trigger an error on purpose, and see the dummy PDFs generated.

### Milestone 2: frame sampling (target Oct 23)

* src/frames.py: given a video path, sample one frame every N seconds (default 2, set in config.py) with OpenCV, downscale to about 1024 pixels wide, save as JPEG, and write a frames.csv with the frame file name and timestamp in seconds.
* Add a pytest that checks frame count and timestamps on a short test video.
* Done when: running it on one of my recordings produces frames and an accurate timestamp file.

My manual work for this milestone: record 12 to 15 runs of the task (about 60 to 120 seconds each), including a few where I make real mistakes. Then hand label every run in data/labels using the template, with start and end seconds for each step. This is the ground truth, so be careful and consistent. Expect about 2 hours.

### Milestone 3: model classification (target Oct 24 to 27)

* src/classify.py: send frames in batches of about 8, each with its timestamp, to the vision model. The prompt must include the allowed step vocabulary, require JSON output only, and ask for a step label and a confidence from 0 to 1 per frame. Use temperature 0. Include the last label of the previous batch as context for continuity.
* Use prompt caching for the fixed instructions, run batches in parallel with a thread pool, retry failed calls, and cache every response on disk by a hash of the frames plus the model name.
* Save predictions to data/predictions/run_XX.csv with the columns t, step, confidence.
* Handle malformed JSON safely (retry once, then mark the batch unclear and log it).
* Done when: I can run it on one recording and see predictions next to my labels, and the total API call count is reported.

### Milestone 4: segmentation and time metrics (target Oct 27)

* src/segment.py turns per frame labels into segments:
  * Smooth single frame flips with a small majority window.
  * Merge segments shorter than 2 seconds into their neighbor.
  * Output per run: steps in order with start, end and duration.
* Compute these time study metrics per run:
  * Cycle time: first frame to last frame.
  * Touch time: time spent in every step except idle and unclear.
  * Wait time: total idle time.
  * Rework: the number and total time of fix_error segments, plus any step that reappears after a later step began.
* Flag any frame with confidence below 0.6 for human review, and write those to a review list.
* Done when: segments and metrics are written for all runs to outputs/.

### Milestone 5: evaluation against my labels (target Oct 28)

* src/evaluate.py compares predictions to my hand labels on a one second grid and reports:
  * Frame accuracy: share of seconds where the predicted step equals my step.
  * Per step duration error: mean absolute error in seconds.
  * Cycle time error: mean absolute error in seconds and as a percent.
  * Step order agreement: normalized edit distance between predicted and true step sequences.
* Run the whole evaluation for both models (sonnet and haiku) and compare accuracy against cost per run.
* Write outputs/metrics.csv and outputs/evaluation_summary.md with n, the numbers, and a short plain description of the failure cases (which steps get confused and why, using real examples).
* Done when: I can read the real accuracy numbers and see where the model fails.

### Milestone 6: dashboard (target Oct 29)

* src/dashboard.py builds outputs/tasklens_dashboard.xlsx with openpyxl and native Excel charts:
  * Runs sheet: cycle, touch, wait and rework time per run.
  * Steps sheet: mean, standard deviation, minimum and maximum per step, with a bar chart of mean time per step and a clear flag on the bottleneck step.
  * Variation: a chart of cycle time per run, and a simple note on the spread.
  * Evaluation sheet: the metrics from Milestone 5.
* Power BI (required): also export clean, tidy CSV tables that load straight into Power BI Desktop with no cleanup: outputs/powerbi/runs.csv, outputs/powerbi/steps.csv and outputs/powerbi/evaluation.csv (one header row, plain snake_case column names, numbers in seconds, no merged cells or totals rows).
* docs/powerbi_guide.md: a short step by step guide to loading those CSVs into Power BI Desktop and building the same charts as the Excel workbook (cycle time per run, mean time per step with the bottleneck flagged, the evaluation table).
* Done when: the workbook opens cleanly in Excel, charts render, the CSVs load into Power BI Desktop without edits, and every number traces back to a CSV.

### Milestone 7: Copilot comparison (target Oct 29 to 30)

* Create data/copilot_timing.csv with the columns run_id, condition, total_seconds, errors. Condition is manual or copilot.
* My manual work: time at least 8 runs of each condition. In the copilot condition, I use Microsoft Copilot Chat (if my UVic Microsoft account provides it) to help extract fields from the invoice text, using dummy data only, and I still review everything before submitting. If I do not have Copilot access, say so in the docs and compare against Claude instead, labeled honestly.
* src/copilot_compare.py reports n, mean, median and standard deviation per condition, the difference in means, and a bootstrap 95 percent confidence interval of the difference.
* In the output, if the interval includes zero, say there is no clear difference. Do not oversell a small sample.
* Done when: outputs/copilot_comparison.md exists with real numbers and an honest conclusion.

### Milestone 8: documents and packaging (target Oct 30 to 31)

* docs/use_case.md in exactly the format the posting asks for, with these headings: Problem statement, Proposed solution, Benefits, Risks, Implementation steps, Success measures. Fill it with the real project and real results.
* The Risks section must cover privacy, confidentiality, model errors, and the need for human review, including how low confidence frames are flagged for a person to check. Be specific about what data was sent to the API (dummy data only, my own screen).
* docs/enablement_guide.md: a one page practical guide for a non technical staff member on using AI for a repetitive task safely. Include a short prompt template, a do and do not list, and a human review checklist.
* README.md: what it is, how to run each step, folder map, the real results table with n, honest limitations, and a link to the dashboard screenshot.
* Done when: a stranger could clone the repo and reproduce the pipeline from the README.

### Milestone 9: application materials (target Nov 1 to 3)

* Add one resume project entry using only real measured numbers, action first, in this style (fill the curly braces from outputs only, never guess):
  * Built a pipeline that uses a vision model to split screen recordings of an invoice entry task into timed steps, reaching {frame accuracy}% step accuracy against hand labels on {n} recordings
  * Produced an Excel dashboard of cycle, touch, wait and rework times that identified {bottleneck step} as the main bottleneck at {mean seconds} seconds per run
  * Compared manual and Copilot assisted runs ({n} each) and found {result with confidence interval}
  * Documented the use case, risks and a one page enablement guide following a standard AI use case template
* Draft a cover letter that leads with this project, connects each part to the two initiatives in the posting, and states the honest limitations. I will edit it before sending.
* Submit by November 3, not on the morning of the deadline.

## Definition of done

* The pipeline runs from the README commands on my recordings.
* Real accuracy numbers with n are reported, including where the model fails.
* The dashboard opens in Excel with working charts.
* The Copilot comparison reports an honest conclusion with a confidence interval.
* The use case document, enablement guide and README are complete.
* No fabricated numbers anywhere, and no real personal data anywhere.

## Cut order if time runs out

If I fall behind, cut in this order and tell me what was cut so I do not claim it on the resume: the haiku versus sonnet comparison, the Copilot comparison, then the enablement guide polish. Never cut the hand labeled evaluation, because it is the strongest part of the project.

## Things I must do myself (Claude Code cannot do these)

* Record the screen videos and run the task.
* Hand label every recording.
* Time the manual and Copilot runs.
* Record a 3 minute demo video.
* Review everything before it goes into the application.
