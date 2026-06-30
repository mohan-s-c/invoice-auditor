from libs.common import db


def test_taxonomy_covered():
    types = {r["anomaly_type"] for r in db.query("SELECT anomaly_type FROM flags")}
    assert {"Duplicate", "Off-contract", "Threshold gaming", "Price overage",
            "Qty outlier"} <= types


def test_no_benchmark_false_positive_on_oneoff_line():
    # BrightElectric's $3,300 panel upgrade must NOT be a price overage (no item benchmark);
    # it should fall to a vendor rate-variance flag.
    f = db.query_one("SELECT anomaly_type FROM flags WHERE vendor='BrightElectric'")
    assert f["anomaly_type"] == "Rate variance"


def test_clean_invoices_auto_cleared():
    cleared = db.query_one("SELECT COUNT(*) c FROM invoices WHERE status='cleared'")["c"]
    flagged = db.query_one("SELECT COUNT(*) c FROM invoices WHERE status='pending'")["c"]
    assert cleared > 0 and flagged > 0


def test_flag_carries_reason_and_model_version():
    f = db.query_one("SELECT * FROM flags LIMIT 1")
    assert f["model_version"]
    assert db.loads(f["rationale"])  # non-empty rationale list


def test_duplicate_detected_between_identical_invoices():
    f = db.query_one("SELECT anomaly_type FROM flags WHERE invoice_id='INV-45121'")
    assert f and f["anomaly_type"] == "Duplicate"
