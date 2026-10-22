"""The judge path end to end: submit -> findings -> fix -> countersign -> history -> export.

A scripted provider stands in for Gemini so the run is deterministic; everything else (rules, retrieval,
quote verification, labelling, number guard, re-check, workflow guards, audit chain) is the real code.
"""
import json
import re

import pytest

from app import worker
from app.llm import adapter
from tests.conftest import demo_client

pytestmark = pytest.mark.db

RIYA = ("Say hello to Aloe-Calm!!! Our 100% natural gel is clinically proven to clear acne in just 7 days. "
        "Made with 92% aloe vera and now 20% off. Grab yours today \U0001F33F #VerdantSkin")
CLAIMS = {
    "100% natural": ("environmental", "AloeCalm is 100% natural"),
    "100% plant-powered": ("environmental", "AloeCalm is 100% plant-powered"),
    "clinically proven to clear acne in just 7 days": ("health_benefit", "AloeCalm clinically clears acne in 7 days"),
    "92% aloe vera": ("numeric", "AloeCalm contains 92% aloe vera"),
    "20% off": ("price_offer", "AloeCalm is 20% off"),
    "68% saw fewer visible blemishes": ("numeric", "68% of AloeCalm users saw fewer visible blemishes in four weeks"),
}
VERDICTS = {  # atomic claim keyword -> (verdict, fact, quote)
    "clears acne": ("contradicts", "F-19", "68% saw fewer visible blemishes"),
    "92% aloe": ("supports", "F-12", "contains 92% aloe vera leaf juice"),
    "20% off": ("supports", "F-23", "20% off on verdantskin.in"),
    "fewer visible blemishes": ("supports", "F-19", "68% saw fewer visible blemishes"),
}


class ScriptedProvider:
    name, model = "scripted", "scripted-1"

    def __init__(self):
        self.prompts: list[str] = []

    async def complete_json(self, system: str, user: str) -> str:
        self.prompts.append(user)
        if "extract checkable marketing claims" in system:
            out = []
            for line in user.splitlines():
                m = re.match(r"\[(\d+)\] (.*)", line)
                if m:
                    out += [{"sentence_id": int(m.group(1)), "quote": q, "claim_type": t, "atomic_claim": a}
                            for q, (t, a) in CLAIMS.items() if q in m.group(2)]
            return json.dumps({"claims": out})
        if "judge marketing claims" in system:
            claims = json.loads(user.split("<claims>")[1].split("</claims>")[0])
            verdicts = []
            for c in claims:
                codes = {f["fact_code"] for f in c["candidates"]}
                hit = next((v for k, v in VERDICTS.items() if k in c["claim"]), None)
                if hit and hit[1] in codes:
                    verdicts.append({"claim_index": c["claim_index"], "verdict": hit[0], "fact_code": hit[1],
                                     "evidence_quote": hit[2], "explanation": "scripted"})
                else:
                    verdicts.append({"claim_index": c["claim_index"], "verdict": "insufficient"})
            return json.dumps({"verdicts": verdicts})
        if "brand voice rubric" in system:
            return json.dumps({"notes": [{"criterion_code": "V1", "quote": "Say hello to Aloe-Calm!!!",
                                          "note": "Too loud for the brand.", "suggestion": "Say hello to AloeCalm."}]})
        if "rewrite flagged spans" in system:
            items = json.loads(user.split("Findings to fix:\n")[1])
            fixes = []
            for it in items:
                span = it["flagged_span"]
                rep = None
                if span.startswith("clinically proven"):
                    rep = "shown to reduce visible blemishes for 68% of adults in a four-week study"
                elif span == "100% natural":
                    rep = "100% plant-powered"  # must be rejected by the claims re-check
                fixes.append({"finding_index": it["finding_index"], "replacement": rep,
                              "approach": None if rep else "Remove the expired offer."})
            return json.dumps({"fixes": fixes})
        if "keep the writer's purpose" in system:
            n = len(json.loads(user.split("<fixes>")[1].split("</fixes>")[0]))
            return json.dumps({"scores": [{"fix_index": i, "intent_score": 5} for i in range(n)]})
        raise AssertionError("unexpected prompt")


@pytest.fixture
def scripted():
    p = ScriptedProvider()
    adapter.override_providers = [p]
    yield p
    adapter.override_providers = None


async def _create(c, text, title="Launch", channel="instagram"):
    r = await c.post("/api/drafts", json={"title": title, "channel": channel,
                                          "purpose": "Announce the AloeCalm launch to followers", "text": text})
    assert r.status_code == 201, r.text
    await worker.drain()
    return r.json()


async def test_round1_example_end_to_end(client_factory, scripted):
    creator = await demo_client(client_factory, "creator")
    d = await _create(creator, RIYA)
    review = (await creator.get(f"/api/versions/{d['version_id']}/review")).json()
    assert review["job"]["status"] == "done" and not review["job"]["ai_degraded"]
    f = review["findings"]
    labels = {x["span"]["text"]: x["claim"]["label"] for x in f if x["lane"] == "claims"}
    assert labels == {"100% natural": "UNSUPPORTED", "clinically proven to clear acne in just 7 days": "CONTRADICTED",
                      "92% aloe vera": "SUPPORTED", "20% off": "EXPIRED"}
    rule_codes = sorted(x["rule"]["code"] for x in f if x["lane"] == "rules")
    assert {"R03", "R06", "R07"} <= set(rule_codes)
    assert any(x["lane"] == "voice" and x["severity"] == "advisory" for x in f)
    for x in f:  # every highlight points at the exact words
        assert RIYA[x["span"]["start"]:x["span"]["end"]] == x["span"]["text"]
    contradicted = next(x for x in f if x["claim"] and x["claim"]["label"] == "CONTRADICTED")
    assert contradicted["evidence"][0]["verified"] and contradicted["evidence"][0]["fact_code"] == "F-19"
    assert contradicted["suggestion"]["replacement"].startswith("shown to reduce")
    assert contradicted["suggestion"]["recheck"]["intent_score"] == 5
    natural = next(x for x in f if x["span"]["text"] == "100% natural")
    assert natural["suggestion"]["replacement"] is None  # "plant-powered" still unsupported -> rejected
    expired = next(x for x in f if x["claim"] and x["claim"]["label"] == "EXPIRED")
    assert "expired on 2026-10-15" in expired["message"]
    terminology = next(x for x in f if x["rule"] and x["rule"]["code"] == "R03")
    assert terminology["suggestion"] == {"replacement": "AloeCalm", "kind": "deterministic", "approach": None,
                                         "recheck": {"rules_ok": True, "claims_ok": None, "intent_score": None}}

    # cannot send while blocking findings are open
    assert (await creator.post(f"/api/drafts/{d['id']}/send-for-review")).status_code == 409

    v2 = ("Say hello to AloeCalm! Our gentle gel is made with 92% aloe vera. In a four-week study, "
          "68% saw fewer visible blemishes. Grab yours today \U0001F33F #VerdantSkin")
    r = await creator.post(f"/api/drafts/{d['id']}/versions", json={"text": v2})
    assert r.status_code == 201
    await worker.drain()
    review2 = (await creator.get(f"/api/versions/{r.json()['version_id']}/review")).json()
    blocking = [x for x in review2["findings"] if x["severity"] == "blocking"]
    assert blocking == [], blocking
    assert (await creator.post(f"/api/drafts/{d['id']}/send-for-review")).status_code == 200

    reviewer = client_factory()
    reviewer.cookies = creator.cookies
    assert (await reviewer.post("/api/demo/switch-role", json={"role": "reviewer"})).status_code == 200
    r = await reviewer.post(f"/api/drafts/{d['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 409 and "reviewed all" in r.json()["detail"]
    r = await reviewer.post(f"/api/drafts/{d['id']}/decision", json={"decision": "approve", "claims_reviewed": True})
    assert r.status_code == 200 and r.json()["status"] == "approved"

    hist = (await reviewer.get(f"/api/drafts/{d['id']}/history")).json()
    assert hist["chain"]["ok"]
    assert [x["decision"] for x in hist["decisions"]] == ["submitted", "approved"]
    csv = await reviewer.get(f"/api/drafts/{d['id']}/export.csv")
    assert csv.status_code == 200 and "approved_copy" in csv.text
    page = await reviewer.get(f"/api/drafts/{d['id']}/record")
    assert page.status_code == 200 and "Audit chain: verified" in page.text


async def test_pii_never_reaches_the_llm(client_factory, scripted):
    creator = await demo_client(client_factory, "creator")
    await _create(creator, "Questions? Call Riya on +91 98765 43210 or riya@example.com. AloeCalm is 92% aloe vera.")
    sent = "\n".join(scripted.prompts)
    assert "98765" not in sent and "riya@example.com" not in sent
    assert "AloeCalm" in sent


async def test_fallback_flags_claims_when_llm_is_down(client_factory):
    adapter.override_providers = []
    try:
        creator = await demo_client(client_factory, "creator")
        d = await _create(creator, "Our AloeCalm gel is clinically proven. Shop now.")
        review = (await creator.get(f"/api/versions/{d['version_id']}/review")).json()
    finally:
        adapter.override_providers = None
    assert review["job"]["ai_degraded"]
    claims = [x for x in review["findings"] if x["lane"] == "claims"]
    assert claims and all(x["source"] == "pattern" and x["claim"]["label"] == "UNSUPPORTED" for x in claims)


async def test_dismissal_needs_reason_and_reviewer_override(client_factory):
    adapter.override_providers = []
    try:
        creator = await demo_client(client_factory, "creator")
        d = await _create(creator, "Meet Aloe-Calm, a calm gel for long days. #VerdantSkin")
        f = (await creator.get(f"/api/versions/{d['version_id']}/review")).json()["findings"]
        term = next(x for x in f if x["rule"] and x["rule"]["code"] == "R03")
        r = await creator.post(f"/api/findings/{term['id']}/decision", json={"action": "dismiss"})
        assert r.status_code == 422
        r = await creator.post(f"/api/findings/{term['id']}/decision",
                               json={"action": "dismiss", "reason": "Legacy spelling in a quote"})
        assert r.status_code == 200 and r.json()["status"] == "dismissed"
        assert (await creator.post(f"/api/drafts/{d['id']}/send-for-review")).status_code == 200
        reviewer = client_factory()
        reviewer.cookies = creator.cookies
        await reviewer.post("/api/demo/switch-role", json={"role": "reviewer"})
        r = await reviewer.post(f"/api/drafts/{d['id']}/decision", json={"decision": "approve", "claims_reviewed": True})
        assert r.status_code == 409 and "Override" in r.json()["detail"]
        r = await reviewer.post(f"/api/findings/{term['id']}/decision", json={"action": "override", "reason": "Agreed"})
        assert r.status_code == 200
        r = await reviewer.post(f"/api/drafts/{d['id']}/decision", json={"decision": "approve", "claims_reviewed": True})
        assert r.status_code == 200
    finally:
        adapter.override_providers = None


async def test_seeded_sandbox_has_every_state(client_factory):
    c = await demo_client(client_factory, "reviewer")
    statuses = {d["status"] for d in (await c.get("/api/drafts")).json()}
    assert {"approved", "in_review", "changes_requested", "checked"} <= statuses
