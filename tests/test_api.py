from fastapi.testclient import TestClient

from services.dashboard_api.app import app

client = TestClient(app)


def test_me_and_dashboard():
    me = client.get("/api/me").json()
    assert me["role"]["id"] == "kyle-hq" and me["roles"]
    d = client.get("/api/dashboard").json()
    assert d["scope"] == "All brands"
    assert d["kpis"]["filed"] > 0 and d["kpis"]["flagged"] > 0
    assert d["category_spend"] and d["anomalies"]


def test_ui_served():
    r = client.get("/")
    assert r.status_code == 200 and "Invoice Auditor" in r.text


def test_region_scoping_filters_everything():
    full = client.get("/api/dashboard").json()["kpis"]["filed"]
    client.post("/api/role", json={"role": "rp-gulf"})
    gulf = client.get("/api/dashboard").json()
    assert gulf["scope"] == "Gulf"
    assert gulf["kpis"]["filed"] < full
    # a Gulf RP cannot open a Mountain West invoice
    assert client.get("/api/invoices/INV-44871").status_code == 403 or \
        client.get("/api/invoices/INV-44871").status_code == 404
    client.post("/api/role", json={"role": "kyle-hq"})


def test_invoice_detail_has_agent_and_audit():
    d = client.get("/api/invoices/INV-45121").json()  # GreenScape duplicate
    assert d["flag"]["anomaly_type"] == "Duplicate"
    assert d["agent"]["gate"] is True and d["agent"]["model_version"]
    assert any(e["actor"] == "agent" for e in d["audit"])


def test_disposition_records_label_and_updates_status():
    inv = "INV-45120"
    out = client.post(f"/api/invoices/{inv}/disposition", json={"action": "reject"}).json()
    assert out["status"] == "rejected"
    assert out["labels"].get("reject", 0) >= 1
    det = client.get(f"/api/invoices/{inv}").json()
    assert det["flag"]["status"] == "rejected"


def test_dismiss_records_false_positive_with_reason():
    # The reviewer disagrees with the flag ("not an anomaly") and gives a reason.
    inv = "INV-44871"  # Summit duplicate flag
    out = client.post(f"/api/invoices/{inv}/disposition",
                      json={"action": "dismiss",
                            "note": "pre-approved capital project — not a duplicate"}).json()
    assert out["status"] == "cleared"
    assert out["labels"].get("dismiss", 0) >= 1
    det = client.get(f"/api/invoices/{inv}").json()
    # the reviewer's reason is captured in the immutable audit trail
    assert any((e.get("after") or {}).get("note") for e in det["audit"])


def test_paid_invoice_blocks_reject_allows_recover():
    # INV-44871 is a flagged invoice that was already paid -> recovery path only.
    det = client.get("/api/invoices/INV-44871").json()
    assert det["invoice"]["paid"] is True
    # reject / hold are blocked once the money has gone out the door
    assert client.post("/api/invoices/INV-44871/disposition",
                       json={"action": "reject"}).status_code == 409
    assert client.post("/api/invoices/INV-44871/disposition",
                       json={"action": "hold"}).status_code == 409
    # recover opens a clawback case (and is captured as a label)
    out = client.post("/api/invoices/INV-44871/disposition",
                      json={"action": "recover", "note": "duplicate already paid"}).json()
    assert out["status"] == "recovery"
    assert out["labels"].get("recover", 0) >= 1


def test_unpaid_invoice_blocks_recover():
    # INV-45120 has not been paid -> nothing to claw back.
    assert client.get("/api/invoices/INV-45120").json()["invoice"]["paid"] is False
    assert client.post("/api/invoices/INV-45120/disposition",
                       json={"action": "recover"}).status_code == 409


def test_flags_expose_paid_flag():
    flags = client.get("/api/flags").json()["flags"]
    assert any(f["paid"] for f in flags) and any(not f["paid"] for f in flags)


def test_vendors_notifications_autonomy():
    v = client.get("/api/vendors").json()
    assert v["vendors"] and 0 <= v["off_contract_pct"] <= 100
    n = client.get("/api/notifications").json()
    assert n["items"]
    a = client.get("/api/autonomy").json()
    assert any(x["level"].startswith("L3") for x in a["autonomy"])
    assert a["guardrails"]
