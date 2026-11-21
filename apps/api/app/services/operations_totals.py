"""One calculation for the project, portfolio and their drill-downs."""

from datetime import date


def summarize(records, today: date):
    active = [r for r in records if r["status"] != "void"]
    contracts = {r["id"]: r for r in active if r["kind"] == "contract"}
    signed = {i: r for i, r in contracts.items() if r["data"]["state"] == "signed"}
    dues = {r["id"]: r for r in active if r["kind"] == "installment"}
    costs = [r for r in active if r["kind"] == "cost"]
    cash = [r for r in active if r["kind"] == "cash" and r["status"] == "verified"]
    verified = [r for r in costs if r["status"] == "verified"]
    pending = [r for r in costs if r["status"] != "verified"]
    forecast = next((r for r in active if r["kind"] == "forecast"), None)
    closing = next((r for r in active if r["kind"] == "closing"), None)
    received = [r for r in cash if r["data"]["direction"] == "in"]
    paid = [r for r in cash if r["data"]["direction"] == "out"]

    def ids(rows):
        return [r["id"] for r in rows]

    def total(rows, key):
        return sum(r["data"][key] for r in rows)

    def contract_of(row):
        data = row["data"]
        term = dues.get(data.get("installment_id"))
        return term["data"]["contract_id"] if term else None

    verified_cost_ids = set(ids(verified))
    unpaid = total(verified, "payable") - total(
        [r for r in paid if r["data"]["cost_id"] in verified_cost_ids], "amount"
    )
    gross = total(signed.values(), "gross")
    direct = total(verified, "direct")
    closing_day = closing["data"]["day"] if closing else None
    remaining = forecast["data"]["remaining"] if forecast else None
    needs_review = (
        not closing_day
        or bool(pending)
        or any(r["data"]["day"] > closing_day for r in verified)
    )
    known = (
        bool(signed)
        and remaining is not None
        and not needs_review
        and all(r["data"]["net"] is not None for r in signed.values())
    )
    profit = total(signed.values(), "net") - direct - remaining if known else None
    by_term = {}
    cutoff = today.isoformat()
    overdue_ids = []
    overdue = 0
    for i, r in dues.items():
        matched = [c for c in received if c["data"]["installment_id"] == i]
        data = r["data"]
        balance = data["amount"] - total(matched, "amount")
        past = (
            data["contract_id"] in signed
            and signed[data["contract_id"]]["data"]["signed_date"] <= cutoff
            and data["due"]
            and data["due"] < cutoff
        )
        matched_on_date = [c for c in matched if c["data"]["day"] <= cutoff]
        open_on_date = data["amount"] - total(matched_on_date, "amount")
        late = max(open_on_date, 0) if past else 0
        if late:
            overdue += late
            overdue_ids.extend([i, *ids(matched_on_date)])
        by_term[i] = {
            "balance": balance,
            "overdue": late,
            "matched": ids(matched),
            "conditional": data["due"] is None,
        }
    by_contract = {}
    for i, r in contracts.items():
        matched = [c for c in received if contract_of(c) == i]
        scheduled = [v for v in dues.values() if v["data"]["contract_id"] == i]
        assigned = [c for c in verified if c["data"]["contract_id"] == i]
        by_contract[i] = {
            "outstanding": r["data"]["gross"] - total(matched, "amount")
            if i in signed
            else None,
            "unscheduled": r["data"]["gross"] - total(scheduled, "amount"),
            "cost": total(assigned, "direct"),
            "entries": [i, *ids(scheduled), *ids(matched), *ids(assigned)],
        }
    unmatched = [
        r
        for r in received
        if not r["data"]["installment_id"]
        and r["data"].get("receipt_purpose") != "other_income"
    ]
    shared = [r for r in verified if not r["data"]["contract_id"]]
    sources = {
        "gross": ids(signed.values()),
        "received": ids(received),
        "paid": ids(paid),
        "net_cash": ids(cash),
        "direct": ids(verified),
        "overdue": overdue_ids,
        "unpaid": ids(verified)
        + ids([r for r in paid if r["data"]["cost_id"] in verified_cost_ids]),
        "profit": ids(signed.values())
        + ids(costs)
        + ids([r for r in (forecast, closing) if r]),
        "unmatched": ids(unmatched),
        "pending": ids(pending),
        "shared": ids(shared),
    }
    return {
        "gross": gross,
        "received": total(received, "amount"),
        "paid": total(paid, "amount"),
        "net_cash": total(received, "amount") - total(paid, "amount"),
        "direct": direct,
        "profit": profit,
        "overdue": overdue,
        "unpaid": unpaid,
        "unmatched": total(unmatched, "amount"),
        "pending": len(pending),
        "shared": total(shared, "direct"),
        "estimate_date": forecast["data"]["day"] if forecast else None,
        "verified_through": closing_day,
        "needs_review": needs_review,
        "contracts": by_contract,
        "installments": by_term,
        "sources": sources,
    }
