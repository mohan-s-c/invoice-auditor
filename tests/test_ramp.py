from libs.ap_client.ramp import RampAPClient


def test_ramp_falls_back_to_seed_without_credentials():
    # No RAMP_CLIENT_ID/SECRET in the test env -> adapter must not break, it serves the seed.
    invs = RampAPClient().invoices()
    assert invs and any(i.id == "INV-44871" for i in invs)


def test_ramp_maps_a_bill_payload():
    bill = {
        "invoice_number": "RB-1", "vendor": {"name": "Acme", "id": "v1"},
        "amount": {"amount": 1234.5}, "category": "Maintenance & repairs",
        "brand": "Stay Montana", "region": "Mountain West",
        "paid": True, "paid_at": "2026-06-20",
        "line_items": [{"memo": "Labor", "quantity": 2,
                        "unit_price": {"amount": 95.0}, "amount": {"amount": 190.0}}],
    }
    inv = RampAPClient._map_bill(bill)
    assert inv.id == "RB-1" and inv.vendor == "Acme" and inv.paid is True
    assert inv.amount == 1234.5 and inv.region == "Mountain West"
    assert inv.lines[0].item == "Labor" and inv.lines[0].amount == 190.0
