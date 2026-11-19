from datetime import date

from app.services.operations_totals import summarize


def test_overdue_drilldown_uses_only_payments_received_by_the_selected_day():
    def row(key, kind, **data):
        return {"id": key, "status": "verified", "kind": kind, "data": data}

    entries = [
        row("contract", "contract", state="signed", gross=5000000, net=5000000),
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
