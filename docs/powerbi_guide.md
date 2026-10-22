# Building the TaskLens dashboard in Power BI Desktop

This guide rebuilds the charts from `outputs/tasklens_dashboard.xlsx` in Power BI Desktop (Windows, free). It takes about 20 minutes.

First run the pipeline up to the dashboard step, so the CSVs exist:

```bash
python src/segment.py
python src/evaluate.py
python src/dashboard.py
```

## The tables

All files are in `outputs/powerbi/`. Each has one header row, plain column names, times in seconds, and no totals rows.

| File | One row per | Columns |
|---|---|---|
| `runs.csv` | run | run, cycle_s, touch_s, wait_s, unclear_s, rework_s, fix_error_count, fix_error_s, repeat_step_count, repeat_step_s |
| `step_times.csv` | run and step | run, step, seconds (0 when the step did not happen in that run) |
| `steps.csv` | step | step, n_runs, runs_with_step, mean_s, sd_s, min_s, max_s, is_bottleneck |
| `evaluation.csv` | model and run | model, run, frame accuracy, cycle time error, step order distance, cost_usd and more |

## 1. Load the data

1. Open Power BI Desktop and choose **Get data > Text/CSV**.
2. Pick `runs.csv` and click **Load**. Repeat for `step_times.csv`, `steps.csv` and `evaluation.csv`.
3. If numbers load as text or the decimals look wrong (common when Windows uses a comma as the decimal mark): click **Transform data**, select the column, then **Data type > Using locale... > Decimal number, English (United States)**. Then **Close & Apply**.

## 2. Connect the tables

Open the **Model** view (left side bar). Power BI usually finds these on its own. If not, drag to create them:

- `runs[run]` to `step_times[run]` (one to many)
- `steps[step]` to `step_times[step]` (one to many)

Now picking a run filters the step chart, and picking a step filters the run charts.

## 3. Build the charts

Go back to the **Report** view. For each chart, click the visual in the **Visualizations** pane, then drag the fields into place.

**Cycle time split per run** (same as the Runs sheet)
- Visual: Stacked column chart
- X-axis: `runs[run]`
- Y-axis: `runs[touch_s]`, `runs[wait_s]`, `runs[unclear_s]`
- Each column adds up to that run's cycle time.

**Mean seconds per step, with the bottleneck flagged** (same as the Steps sheet)
- Visual: Clustered column chart
- X-axis: `steps[step]`
- Y-axis: `steps[mean_s]` (set it to **Don't summarize** or **Sum**; there is one row per step)
- To color the bottleneck, create a measure (**Modeling > New measure**):

  ```
  Bar color = IF ( MAX ( steps[is_bottleneck] ), "#E0A100", "#6C8EBF" )
  ```

  Then select the chart, go to **Format > Columns > Color**, click **fx**, set **Format style** to **Field value**, and pick `Bar color`.
- Sort by `mean_s`, largest first (the **...** menu on the chart > Sort axis).

**Cycle time per run** (same as the Variation sheet)
- Visual: Line chart
- X-axis: `runs[run]`
- Y-axis: `runs[cycle_s]` (Sum)

**Spread of cycle time**
Create these measures and show each in a **Card** visual:

```
Runs (n) = COUNTROWS ( runs )
Mean cycle (s) = AVERAGE ( runs[cycle_s] )
SD cycle (s) = STDEV.S ( runs[cycle_s] )
CV cycle (%) = DIVIDE ( [SD cycle (s)], [Mean cycle (s)] ) * 100
```

**Model accuracy and cost** (same as the Evaluation sheet)
- Visual: Table
- Columns: `evaluation[model]`, then `frame_accuracy`, `cycle_abs_error_s`, `order_distance`, `cost_usd`, all set to **Average**
- Add a count of `evaluation[run]` so n shows next to each model.

## 4. Finish

- Add a **Text box** at the top: "TaskLens time study, n = {runs} runs, dummy invoice data".
- Put the `Runs (n)` card next to every chart that shows a mean, so n is always visible.
- **File > Save** as `outputs/tasklens_dashboard.pbix`, and export a screenshot for the README.

When the CSVs change, click **Home > Refresh** to update every chart.
