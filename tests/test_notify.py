from fastapi.testclient import TestClient

from libs.notify import get_notifier
from libs.notify.offline import OfflineNotifier
from services.dashboard_api.app import app
from services.notify import dispatch, policy

client = TestClient(app)


def test_policy_threshold_and_severity():
    # high severity always notifies, regardless of amount
    ok, _ = policy.should_notify(
        {"severity": "high", "amount": 10, "category": "Linens", "region": "Gulf"})
    assert ok
    # medium below the category threshold does not
    ok, _ = policy.should_notify(
        {"severity": "medium", "amount": 100, "category": "Linens", "region": "Gulf"})
    assert not ok
    # medium above the category threshold ($750 for Linens) does
    ok, _ = policy.should_notify(
        {"severity": "medium", "amount": 900, "category": "Linens", "region": "Gulf"})
    assert ok


def test_recipients_route_to_rp_and_cc_ops_on_critical():
    to = policy.recipients({"region": "Gulf", "severity": "high"})
    assert to[0]["kind"] == "to" and to[0]["email"] == policy.REGION_CONTACTS["Gulf"]["email"]
    crit = policy.recipients({"region": "Gulf", "severity": "critical"})
    assert any(x["kind"] == "cc" and x["email"] == policy.OPS_HEAD["email"] for x in crit)


def test_offline_notifier_is_default_and_queues():
    n = get_notifier()
    assert isinstance(n, OfflineNotifier)


def test_seed_populates_outbox_and_dispatch_is_idempotent():
    # conftest's seed_all already ran dispatch -> outbox populated, all queued (offline)
    items = dispatch.outbox()
    assert items and all(i["status"] == "queued" for i in items)
    before = len(items)
    res = dispatch.dispatch_notifications()        # running again adds nothing new
    assert res["skipped_already_notified"] >= 1
    assert len(dispatch.outbox()) == before


def test_outbox_api_is_region_scoped_and_dispatch_is_hq_only():
    full = client.get("/api/notify/outbox").json()["count"]
    client.post("/api/role", json={"role": "rp-gulf"})
    gulf = client.get("/api/notify/outbox").json()
    assert all(i["region"] == "Gulf" for i in gulf["items"])
    assert gulf["count"] <= full
    assert client.post("/api/notify/dispatch").status_code == 403   # RP can't dispatch
    client.post("/api/role", json={"role": "kyle-hq"})
