"""Create 20 dummy invoice PDFs plus an answer key (invoices.json).

All data is fake (Faker with a fixed seed), so the output is the same on every run.
Usage: python tasks/invoice_entry/generate_invoices.py
"""

import json
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from faker import Faker
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SEED = 42
INVOICE_COUNT = 20
OUT_DIR = Path(__file__).resolve().parent / "invoices"

PRODUCTS = [
    ("Printer paper (box)", Decimal("42.50")),
    ("Toner cartridge", Decimal("89.99")),
    ("Desk chair", Decimal("215.00")),
    ("USB-C cable", Decimal("12.75")),
    ("Whiteboard markers (pack)", Decimal("9.40")),
    ("Monitor stand", Decimal("64.20")),
    ("Filing cabinet", Decimal("189.00")),
    ("Notebook (pack of 10)", Decimal("23.60")),
    ("Wireless mouse", Decimal("31.15")),
    ("Cleaning service (hour)", Decimal("38.00")),
]


def money(value):
    """Round a Decimal to cents."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def make_invoice(number, fake, rng, used_vendors):
    """Build one invoice as a plain dict."""
    vendor = fake.company()
    while vendor in used_vendors:  # each vendor appears once, so the form can look it up
        vendor = fake.company()
    used_vendors.add(vendor)

    invoice_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 270))

    items = []
    for name, unit_price in rng.sample(PRODUCTS, rng.randint(2, 5)):
        quantity = rng.randint(1, 8)
        items.append({
            "description": name,
            "quantity": quantity,
            "unit_price": str(unit_price),
            "amount": str(money(unit_price * quantity)),
        })
    total = money(sum(Decimal(item["amount"]) for item in items))

    return {
        "file": f"invoice_{number:02d}.pdf",
        "invoice_number": f"INV-{rng.randint(10000, 99999)}",
        "vendor": vendor,
        "vendor_address": fake.address().replace("\n", ", "),
        "date": invoice_date.isoformat(),
        "items": items,
        "total": str(total),
    }


def draw_invoice(invoice, path):
    """Write one invoice to a PDF file."""
    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(72, height - 80, "INVOICE")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, height - 120, invoice["vendor"])
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, height - 136, invoice["vendor_address"])

    pdf.setFont("Helvetica", 12)
    pdf.drawString(360, height - 120, f"Invoice #: {invoice['invoice_number']}")
    pdf.drawString(360, height - 138, f"Date: {invoice['date']}")

    # Line item table
    y = height - 200
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, y, "Description")
    pdf.drawString(320, y, "Qty")
    pdf.drawString(380, y, "Unit price")
    pdf.drawString(470, y, "Amount")
    pdf.line(72, y - 6, 540, y - 6)

    pdf.setFont("Helvetica", 11)
    for item in invoice["items"]:
        y -= 22
        pdf.drawString(72, y, item["description"])
        pdf.drawString(320, y, str(item["quantity"]))
        pdf.drawString(380, y, f"${item['unit_price']}")
        pdf.drawString(470, y, f"${item['amount']}")

    pdf.line(72, y - 12, 540, y - 12)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(380, y - 34, "TOTAL")
    pdf.drawString(470, y - 34, f"${invoice['total']}")

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(72, 50, "Dummy data generated for the TaskLens study. Not a real invoice.")
    pdf.save()


def main():
    fake = Faker("en_CA")
    Faker.seed(SEED)
    rng = random.Random(SEED)
    OUT_DIR.mkdir(exist_ok=True)

    used_vendors = set()
    invoices = []
    for number in range(1, INVOICE_COUNT + 1):
        invoice = make_invoice(number, fake, rng, used_vendors)
        draw_invoice(invoice, OUT_DIR / invoice["file"])
        invoices.append(invoice)

    # Answer key, used by form.html to check the total
    with open(OUT_DIR / "invoices.json", "w", encoding="utf-8") as f:
        json.dump(invoices, f, indent=2)

    print(f"Wrote {len(invoices)} invoices to {OUT_DIR}")


if __name__ == "__main__":
    main()
