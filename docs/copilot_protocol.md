# Timing protocol: manual vs AI assisted invoice entry

How to time the runs for `data/copilot_timing.csv`, so the comparison is fair.

## Conditions

- **manual**: read the vendor, date and total off the invoice PDF yourself and type them into the form.
- **copilot**: paste the invoice text into Microsoft Copilot Chat, ask it for the three fields, check its answer against the PDF, then type or paste them into the form. You still review everything before submitting.

If Copilot Chat is not available on your account, use Claude instead, record the condition as `claude`, and say so in the write up. Do not label Claude runs as Copilot.

Prompt to use every time (keep it identical across runs):

> From this invoice text, give me the vendor name, the invoice date in YYYY-MM-DD format, and the total as a number with two decimals. Reply with three lines only.

## Doing the runs

1. Do at least 8 runs of each condition. More is better; the result will be uncertain with only 8.
2. Use different invoices for each run, and give both conditions a similar mix (for example odd invoice numbers manual, even ones assisted, then swap halfway).
3. Alternate the conditions (manual, assisted, manual, ...) instead of doing all of one first, so practice and tiredness affect both equally.
4. Start the stopwatch when you open the invoice. Stop it when the form shows the green "Saved" message.
5. `total_seconds` is the stopwatch time, including any time spent fixing errors.
6. `errors` is the number of times the form showed a red error message in that run.
7. Write each run straight into the CSV:

```
run_id,condition,total_seconds,errors
t01,manual,74.2,0
t02,copilot,81.5,1
```

Use dummy invoices only. Never paste real invoices or personal data into Copilot or Claude.

## Then run

```bash
python src/copilot_compare.py
```

It writes `outputs/copilot_comparison.md` with n, mean, median and standard deviation per condition, the difference in means, and a bootstrap 95 percent confidence interval.
