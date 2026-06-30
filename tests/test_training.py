from services.learning.capture import record_disposition
from services.training import registry, trainer


def _flag():
    from libs.common import db
    return dict(db.query_one("SELECT * FROM flags LIMIT 1"))


def test_initial_champion_registered():
    c = registry.champion()
    assert c and c["status"] == "champion" and c["version"] == "qwen-offline-v1"


def test_eval_metrics_from_dispositions():
    f = _flag()
    record_disposition(f["id"], f["invoice_id"], "kyle-hq", "reject",
                       model_version=f["model_version"])
    ev = trainer.eval_metrics()
    assert ev["labels"] == 1 and ev["confirmed"] == 1
    assert ev["per_type"].get(f["anomaly_type"]) == 1.0


def test_dismiss_is_a_false_positive_label():
    # A reviewer disagreeing ("not an anomaly") teaches the model the flag was wrong.
    f = _flag()
    record_disposition(f["id"], f["invoice_id"], "kyle-hq", "dismiss",
                       model_version=f["model_version"])
    ev = trainer.eval_metrics()
    assert ev["false_positives"] >= 1
    assert ev["per_type"].get(f["anomaly_type"]) == 0.0


def test_approve_is_neutral_not_a_false_positive():
    # Approving a flagged invoice means "pay it" — ambiguous, so it must NOT count against
    # the flag's precision (the flag may have been correct; the reviewer just accepts it).
    f = _flag()
    record_disposition(f["id"], f["invoice_id"], "kyle-hq", "approve",
                       model_version=f["model_version"])
    ev = trainer.eval_metrics()
    assert ev["labels"] == 1                       # captured as a label
    assert ev["false_positives"] == 0              # but not a false positive
    assert ev["confirmed"] == 0                    # and not a confirmation
    assert ev["per_type"].get(f["anomaly_type"]) is None


def test_finetune_promotes_when_it_beats_champion_and_clears_bar():
    f = _flag()
    # a batch of confirmations → enough uplift to clear the bar
    for _ in range(30):
        record_disposition(f["id"], f["invoice_id"], "kyle-hq", "reject",
                           model_version=f["model_version"])
    res = trainer.run_finetune()
    assert res["precision"] >= res["bar"]
    assert res["promoted"] is True
    assert registry.champion()["version"] == res["candidate"]


def test_rollback_restores_previous_champion():
    before = registry.champion()["version"]
    for _ in range(30):
        f = _flag()
        record_disposition(f["id"], f["invoice_id"], "kyle-hq", "hold",
                           model_version=f["model_version"])
    promoted = trainer.run_finetune()
    assert registry.champion()["version"] == promoted["candidate"]
    rb = registry.rollback()
    assert rb["rolled_back"] is True
    assert registry.champion()["version"] == before
