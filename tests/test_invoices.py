"""Checks that the dummy invoices are reproducible and their totals add up."""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tasks" / "invoice_entry"))
import generate_invoices  # noqa: E402


def test_invoices_are_reproducible_and_totals_add_up():
    generate_invoices.main()
    key_file = generate_invoices.OUT_DIR / "invoices.json"
    first = json.loads(key_file.read_text(encoding="utf-8"))

    generate_invoices.main()
    second = json.loads(key_file.read_text(encoding="utf-8"))

    assert first == second
    assert len(first) == 20
    assert len({inv["vendor"] for inv in first}) == 20
    for inv in first:
        assert Decimal(inv["total"]) == sum(Decimal(item["amount"]) for item in inv["items"])
        assert (generate_invoices.OUT_DIR / inv["file"]).exists()
