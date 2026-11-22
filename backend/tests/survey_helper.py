"""Fill in a complete site survey the way a technician would (required fields + photos)."""
import pytest

H = {"X-SunPower": "1"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

REQUIRED = {
    "property_type": "house", "ownership": "owned", "roof_condition": "good", "roof_height_m": 6,
    "phase": "single", "sanctioned_load_kw": 5, "net_meter_space": True, "db_condition": "good", "db_spare_way": True,
    "inverter_location": "indoor_wall", "dc_cable_m": 15, "ac_cable_m": 8, "earth_cable_m": 10,
    "mounting_type": "ballasted", "access": "stairs", "declaration": True,
}


def fill_survey(client, sid, kw, area=300, photos=True, **details):
    r = client.patch("/api/staff/surveys/%s" % sid, headers=H, json={
        "roof_type": "rcc", "roof_direction": "S", "usable_area_sqft": area, "recommended_kw": kw,
        "result": details.pop("result", "feasible"), "details": {**REQUIRED, **details}})
    assert r.status_code == 200, r.text
    if photos:
        for cat in ("roof", "shadow_free", "meter", "db", "inverter_spot"):
            r = client.post("/api/staff/surveys/%s/photos" % sid, headers=H, data={"category": cat},
                            files={"file": ("%s.png" % cat, PNG, "image/png")})
            assert r.status_code == 200, r.text


@pytest.fixture
def payments_on():
    """Payment step switched on for one test (it's off by default while the gateway is being set up)."""
    from app.db import session
    with session() as db:
        db.set_setting("payment_required", "1")
    yield
    with session() as db:
        db.set_setting("payment_required", "0")
