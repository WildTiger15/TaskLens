# Using AI for a repetitive task, safely

A one page guide for anyone who wants to use Microsoft Copilot (or a similar AI assistant) to speed up a routine task, such as pulling the vendor, date and total out of an invoice.

## Good tasks for AI help

- The same steps every time, with a clear right answer you can check (copying fields, summarizing a form, reformatting a list).
- You can see the source next to the AI's answer, so checking takes seconds.
- A mistake would be caught before it matters.

Not a good fit: decisions about people, anything you cannot check, or anything involving data you are not allowed to share.

## A prompt template

Write the prompt once, save it, and reuse it word for word. The same prompt gives more consistent answers.

> From this **[document type]**, give me the **[field 1]**, the **[field 2] in [format]**, and the **[field 3] as [format]**. Reply with **[number] lines** only. If a field is missing or unclear, write "NOT FOUND" for that line instead of guessing.

Example:

> From this invoice, give me the vendor name, the invoice date in YYYY-MM-DD format, and the total as a number with two decimals. Reply with three lines only. If a field is missing or unclear, write "NOT FOUND" for that line instead of guessing.

## Do

- **Use the approved tool.** Use your organization's Copilot, signed in with your work account, so its data protections apply.
- **Remove what is not needed.** Paste only the part of the document the task needs.
- **Ask for a fixed format** (dates as YYYY-MM-DD, numbers without currency symbols), so answers are easy to check and paste.
- **Check every answer** against the source before you use it (see the checklist below).
- **Keep a short note** when the AI got something wrong. Patterns in the mistakes show where the prompt needs fixing.
- **Time yourself** for a week with and without AI before deciding it saves time.

## Do not

- Paste passwords, personal details (health, ID numbers, home addresses), or customer or financial data into a tool your organization has not approved.
- Copy an AI answer into a system of record without reading it.
- Let the AI fill in a value it could not find. A blank is better than a confident wrong answer.
- Assume it will be right next time because it was right last time.
- Use AI output as the only evidence for a decision about a person.

## Human review checklist

Before you submit anything the AI helped with:

- [ ] Every field matches the source document, character by character for names and numbers.
- [ ] Dates are in the right format and are real dates.
- [ ] Totals and amounts match the source exactly (watch for dropped digits, swapped decimals, or a subtotal used instead of the total).
- [ ] Nothing was added that is not in the source.
- [ ] Any "NOT FOUND" or unclear field was checked by hand.
- [ ] No private or confidential data was pasted into a tool that is not approved.
- [ ] If anything looked off, you fixed it and noted what went wrong.

You are responsible for what you submit, whether or not an AI helped write it.
