# AI use case: time studies from screen recordings

Numbers in curly braces are filled in only from the project's outputs (named next to each one) after real runs. Each comes with its sample size (n).

## Problem statement

Time studies of office work show where effort goes, how much a process varies, and where rework happens. Done by hand, someone watches a person work (or watches a recording) with a stopwatch and notes when each step starts and ends. That takes roughly as long as the work itself, or longer, so studies stay small, happen rarely, and are hard to repeat after a process change.

This project tests whether a vision model can do the first pass: watch screen recordings of a repeatable admin task (invoice data entry), split them into timed steps, and produce cycle, touch, wait and rework times, with a person checking the uncertain parts.

## Proposed solution

A small Python pipeline, run on recordings of one person doing a dummy invoice entry task:

1. **Sample frames.** Take one frame every 2 seconds from each recording (OpenCV), shrunk to about 1024 pixels wide.
2. **Classify.** Send frames in batches of 8 to a Claude vision model, which labels each frame with one step from a fixed list (open invoice, read fields, switch to form, type vendor, type date, type total, submit, fix error, idle, unclear) and a confidence from 0 to 1. The output format is enforced as JSON, and every answer is cached so reruns cost nothing.
3. **Segment and measure.** Smooth one-frame flips, join frames into timed steps, and compute cycle, touch, wait and rework time per run.
4. **Flag for review.** Any frame with confidence below 0.6 goes on a review list with a link to the image.
5. **Check accuracy.** Compare against hand labels of the same recordings, second by second, for two models (Claude Sonnet 5.5 and the cheaper Claude Haiku 5.5).
6. **Report.** An Excel workbook with charts and the same tables as CSVs for Power BI.
7. **Compare assistance.** Separately, time the task done manually and with Microsoft Copilot Chat helping to extract the fields.

## Benefits

- **Speed.** A recording is labeled in about {minutes per recording, from a timed classify run} instead of the recording's full length or more by hand. Cost is about {cost per run} per recording (outputs/evaluation_summary.md).
- **Repeatable.** The same recordings always give the same result (cached answers, fixed step list), so a study can be rerun after a process change and compared fairly.
- **More data.** Cheap labeling makes it practical to study more runs, which shows variation that a few stopwatch runs miss. In this study, cycle time ranged from {min} to {max} s across {n} runs (dashboard Variation sheet).
- **Finds the bottleneck.** The dashboard flags the step that takes the most time: {bottleneck step} at {mean} s per run, n = {n} (dashboard Steps sheet).
- **Shows rework.** Error fixing and repeated steps are measured, not just noticed: {rework seconds} s per run on average (outputs/claude-sonnet-5-5/run_metrics.csv).

## Risks

**Privacy.** Screen recordings capture whatever is on screen: names, emails, chat pop-ups, other windows. In this project only the author's own screen was recorded, only the dummy task was open, and notifications were turned off. In real use, recordings must be made with the person's informed consent, with other apps closed, and kept only as long as needed.

**Confidentiality.** The frames are sent to an outside AI service (the Anthropic API). Here that meant only screenshots of dummy invoices made by Faker and a local web form. No real invoices, customer data or company systems were recorded. Recordings, frames and cached answers stay on the author's computer and are excluded from the public repository. In real use, check the provider's data retention and training terms, and get approval from whoever owns the data before sending any screenshots.

**Model errors.** The model mislabels some frames. Measured accuracy is {frame accuracy}% of seconds against hand labels on {n} recordings, and the most common confusion is {true step} labeled as {predicted step} (outputs/evaluation_summary.md). Steps that look alike on screen, or that last less than the 2 second sampling gap (such as a quick submit click), are the hardest. Cycle time is off by {cycle MAE} s on average. These numbers come from one person doing one task, so they will not carry over to other tasks without checking again.

**Need for human review.** The output is a first draft of a time study, not a final one. Three safeguards keep a person in charge:
- Every frame with confidence below 0.6 is written to a review list (outputs/<model>/review_list.csv) with the exact image to look at. In this study that was {review count} of {total frames} frames.
- A batch the model fails to answer properly is marked "unclear" rather than guessed, and logged.
- Accuracy is measured against hand labels before any number is reported, and every reported number states its n.

**Over-reading small samples.** With {n} runs, differences between people, days or tools can easily be noise. The Copilot comparison reports a confidence interval and says "no clear difference" when the interval includes zero.

## Implementation steps

1. Pick one repeatable task and write a fixed list of steps with a short description of what each looks like on screen.
2. Record 12 to 15 runs with consent, with other apps closed. Use test data where possible.
3. Hand label a set of runs (start and end of each step). This is the ground truth.
4. Run the pipeline: frames, classify, segment, evaluate. Look at the confusions and the review list.
5. If accuracy is too low, improve the step descriptions in the prompt or sample frames more often, then measure again.
6. Build the dashboard, check the bottleneck and the variation, and review flagged frames before sharing.
7. Repeat after any process change, using the same steps and settings, to measure the effect.

## Success measures

| Measure | How it is measured | Result |
|---|---|---|
| Step accuracy | share of seconds where model and hand labels agree | {frame accuracy}%, n = {n} recordings |
| Cycle time error | mean absolute error against hand labels | {cycle MAE} s ({cycle MAE %}%) |
| Step order | normalized edit distance of step sequences (0 is perfect) | {order distance} |
| Cost | API cost per recording from token counts | {cost per run} (Sonnet), {cost per run} (Haiku) |
| Cheaper model | accuracy of Haiku against Sonnet | {haiku accuracy}% vs {sonnet accuracy}% |
| Review load | frames under 0.6 confidence | {review count} of {total frames} |
| AI assistance | difference in task time, Copilot minus manual, with 95% interval | {difference} s ({low} to {high}), n = {n} each |
