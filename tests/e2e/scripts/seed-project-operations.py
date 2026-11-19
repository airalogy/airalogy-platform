"""Local only; creates isolated synthetic fixtures through the Platform API."""

import json
import os
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

location = urlsplit(os.environ.get("DATABASE_URL", ""))
if location.hostname not in {"127.0.0.1", "localhost"} or location.path not in {
    "/platform_operations_demo",
    "/airalogy_e2e",
}:
    raise SystemExit("Source the local E2E or operations demo environment first.")
origin = "http://127.0.0.1:4100"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(method, url, token=None, data=None, allow=()):
    req = urllib.request.Request(
        origin + url,
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Auth-Token": token} if token else {}),
        },
    )
    try:
        with opener.open(req, timeout=90) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in allow:
            return None
        raise RuntimeError(f"{method} {url} {e.code}: {e.read().decode()[:300]}")


fixture = api("POST", "/dev/fixtures/quickstart")
accounts = {
    a["key"]: api(
        "POST",
        "/signin_by_email",
        data={"email": a["email"], "password": a["password"]},
    )["token"]
    for a in fixture["accounts"]
}
lead, finance, ceo = (accounts[k] for k in ("owner", "collaborator", "viewer"))
org = fixture["lab"]["id"]
members = api("GET", "/projects/" + fixture["project"]["id"] + "/users", lead)["users"]
uids = {u["username"]: u["id"] for u in members}
uid = "instrument_operations_demo"
project = api(
    "GET", "/projects/by_uid?lab_uid=dev_lab&project_uid=" + uid, lead, allow=(404,)
)
if project and project["name"] != "仪器数据接入（虚构验收）":
    raise SystemExit("A different project uses the demo ID")
if not project:
    project = api(
        "POST",
        "/projects",
        lead,
        {
            "uid": uid,
            "lab_id": org,
            "name": "仪器数据接入（虚构验收）",
            "type": 1,
            "description": "仅用于项目经营第 7 节的本地验收。",
        },
    )
pid = project["id"]
base = "/project-operations/projects/" + pid
orgpath = "/project-operations/organizations/" + org
existing = {u["id"] for u in api("GET", "/projects/" + pid + "/users", lead)["users"]}
for uname, role in [("dev_collaborator", 30), ("dev_viewer", 60)]:
    if uids[uname] not in existing:
        api(
            "POST",
            "/projects/" + pid + "/users",
            lead,
            {"user_id": uids[uname], "role": role},
        )
orgstate = api("GET", orgpath + "/access", lead)
if not orgstate["enabled"]:
    api(
        "PUT",
        orgpath,
        lead,
        {"enabled": True, "expected_revision": orgstate["revision"]},
    )
book = api("GET", base + "/settings", lead)
grants = {
    uids["dev_owner"]: "lead",
    uids["dev_collaborator"]: "finance",
    uids["dev_viewer"]: "viewer",
}
if not book["enabled"] or book["grants"] != grants:
    api(
        "PUT",
        base + "/settings",
        lead,
        {"enabled": True, "grants": grants, "expected_revision": book["revision"]},
    )


def identity(s):
    return str(uuid.uuid5(uuid.UUID(pid), s))


def post(key, who, name, kind, data, rev=0, action="save", reason=""):
    return api(
        "POST",
        base + "/entries",
        who,
        {
            "request_id": identity("request:" + key),
            "entry_id": identity(name),
            "expected_revision": rev,
            "action": action,
            "reason": reason,
            "data": {"kind": kind, **data} if data is not None else None,
        },
    )


c = {
    "title": "采集设备",
    "day": "2026-10-30",
    "category": "material",
    "direct": 600000,
    "payable": 600000,
}
post("equipment", lead, "equipment", "cost", c)
post("verify-equipment", finance, "equipment", "cost", None, 1, "verify")
post(
    "first-payment",
    finance,
    "payment1",
    "cash",
    {
        "title": "设备首付",
        "day": "2026-10-30",
        "direction": "out",
        "amount": 400000,
        "cost_id": identity("equipment"),
    },
)
a = {
    "title": "合同 A",
    "customer": "虚构客户",
    "state": "signed",
    "signed_date": "2026-11-01",
    "gross": 10600000,
    "net": 10000000,
}
post("contract-a", lead, "a", "contract", a)
post(
    "attribute-equipment",
    lead,
    "equipment",
    "cost",
    {**c, "contract_id": identity("a")},
    2,
    reason="签约前采购归入合同 A",
)
post(
    "forecast",
    lead,
    "forecast",
    "forecast",
    {"day": "2026-11-09", "remaining": 3400000, "basis": "剩余实施、调试及交付投入"},
)
post(
    "close",
    finance,
    "closing",
    "closing",
    {"day": "2026-11-11", "basis": "已核对本期设备与共用成本"},
)
post(
    "first-term",
    lead,
    "first",
    "installment",
    {
        "title": "首期",
        "contract_id": identity("a"),
        "amount": 5000000,
        "due": "2026-11-10",
    },
)
post(
    "final-term",
    lead,
    "tail",
    "installment",
    {
        "title": "尾款",
        "contract_id": identity("a"),
        "amount": 5600000,
        "condition": "客户签回验收单后 30 天",
    },
)
receipt = {
    "title": "首期回款",
    "direction": "in",
    "day": "2026-11-09",
    "amount": 3000000,
    "installment_id": identity("first"),
}
post("receipt", finance, "receipt", "cash", receipt)
post("receipt", finance, "receipt", "cash", receipt)
post(
    "second-payment",
    finance,
    "payment2",
    "cash",
    {
        "title": "设备余款",
        "direction": "out",
        "day": "2026-11-10",
        "amount": 200000,
        "cost_id": identity("equipment"),
    },
)
post(
    "contract-b",
    lead,
    "b",
    "contract",
    {**a, "title": "合同 B", "gross": 1000000, "net": 1000000},
)
post(
    "shared",
    lead,
    "shared",
    "cost",
    {**c, "title": "项目共用成本", "direct": 100000, "payable": 100000},
)
post("verify-shared", finance, "shared", "cost", None, 1, "verify")
s = api("GET", base + "?as_of=2026-11-11", ceo)["summary"]
assert [s[k] for k in ["gross", "direct", "net_cash", "overdue", "profit"]] == [
    11600000,
    700000,
    2400000,
    2000000,
    6900000,
]
print("Synthetic local book verified:", uid)
