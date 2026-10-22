import pytest

from app.lanes.rules.engine import validate_rule
from app.seed.loader import brand_keys, load_brand


@pytest.mark.parametrize("key", brand_keys())
def test_brand_files_are_valid(key):
    brand = load_brand(key)
    codes = [r["code"] for r in brand["rules"]]
    assert len(codes) == len(set(codes))
    for r in brand["rules"]:
        assert validate_rule(r["type"], r.get("params", {})) == [], r["code"]
    fact_codes = {f["code"] for f in brand["facts"]}
    for f in brand["facts"]:
        assert f.get("superseded_by") in (None, *fact_codes)
    assert {u["role"] for u in brand["users"]} == {"admin", "reviewer", "creator"}
