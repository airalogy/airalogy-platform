from datetime import date

from app.services.operations_totals import summarize


def row(key, kind, **data):
    return {"id": key, "status": "verified", "kind": kind, "data": data}


def test_overdue_drilldown_uses_only_payments_received_by_the_selected_day():
    entries = [
        row(
            "contract",
            "contract",
            state="signed",
            signed_date="2026-11-01",
            gross=5000000,
            net=5000000,
        ),
        row(
            "term",
            "installment",
            contract_id="contract",
            due="2026-11-10",
            amount=5000000,
        ),
        row(
            "early",
            "cash",
            direction="in",
            day="2026-11-09",
            amount=3000000,
            installment_id="term",
        ),
        row(
            "cutoff",
            "cash",
            direction="in",
            day="2026-11-11",
            amount=500000,
            installment_id="term",
        ),
        row(
            "later",
            "cash",
            direction="in",
            day="2026-11-12",
            amount=1500000,
            installment_id="term",
        ),
    ]
    for day, amount, sources in [
        (10, 0, []),
        (11, 1500000, ["term", "early", "cutoff"]),
        (12, 0, []),
    ]:
        result = summarize(entries, date(2026, 11, day))
        assert result["overdue"] == amount
        assert result["sources"]["overdue"] == sources
        assert result["received"] == 5000000
        assert result["installments"]["term"]["balance"] == 0

    entries[0]["data"]["signed_date"] = "2026-11-12"
    result = summarize(entries, date(2026, 11, 11))
    assert result["overdue"] == 0
    assert result["sources"]["overdue"] == []


def test_remaining_is_per_signed_contract_and_draft_receipts_are_cash_only():
    def receipt(key, contract, amount):
        return row(
            key, "cash", direction="in", receipt_purpose="customer_receipt",
            installment_id=None, contract_id=contract, amount=amount,
        )

    entries = [
        row("a", "contract", state="signed", gross=10000, net=9000),
        row("b", "contract", state="signed", gross=6000, net=5500),
        row("draft", "contract", state="draft", gross=2000, net=None),
        receipt("payment-a", "a", 11000),
        receipt("advance", "draft", 1500),
        receipt("unallocated", None, 1000),
    ]
    result = summarize(entries, date(2026, 11, 21))
    assert result["gross"] == 16000
    assert result["received"] == 13500
    assert result["contract_received"] == 11000
    assert result["contract_remaining"] == 6000
    assert result["contracts"]["draft"]["received"] is None
    assert result["sources"]["contract_received"] == ["payment-a"]
    assert set(result["sources"]["contract_remaining"]) == {"a", "b", "payment-a"}
