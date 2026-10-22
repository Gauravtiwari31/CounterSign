"""Judge-path smoke test against a live deployment: python scripts/smoke.py https://your-app.example

Creator submits the Round 1 example -> findings arrive -> fixed version -> send for countersign ->
reviewer approves -> history chain verifies -> export works. Exits non-zero on the first failure.
"""
import sys
import time

import httpx

URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
FIXED = ("Say hello to AloeCalm! Our gentle gel is made with 92% aloe vera. In a four-week study, 68% saw fewer "
         "visible blemishes. Grab yours today #VerdantSkin")


def step(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        sys.exit(1)


def wait_review(c, vid, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"{URL}/api/versions/{vid}/review").json()
        if r["job"]["status"] in ("done", "failed"):
            return r, time.time() - t0
        time.sleep(1)
    step("review finished", False, f"timeout after {timeout}s")


with httpx.Client(timeout=90) as c:
    step("health", c.get(f"{URL}/api/health").status_code == 200)
    t = time.time()
    step("demo session", c.post(f"{URL}/api/demo/session", json={"role": "creator"}).status_code == 200,
         f"{time.time() - t:.1f}s")
    sample = c.get(f"{URL}/api/demo/sample").json()
    d = c.post(f"{URL}/api/drafts", json={k: sample[k] for k in ("title", "channel", "purpose", "text")}).json()
    review, secs = wait_review(c, d["version_id"])
    labels = sorted({f["claim"]["label"] for f in review["findings"] if f["claim"]})
    step("round 1 example reviewed", len(review["findings"]) >= 5, f"{len(review['findings'])} findings in {secs:.1f}s, "
         f"labels {labels}, ai_degraded={review['job']['ai_degraded']}")
    v = c.post(f"{URL}/api/drafts/{d['id']}/versions", json={"text": FIXED}).json()
    review2, _ = wait_review(c, v["version_id"])
    for f in review2["findings"]:
        if f["severity"] == "blocking" and f["status"] == "open":
            c.post(f"{URL}/api/findings/{f['id']}/decision", json={"action": "dismiss", "reason": "smoke test"})
    step("send for countersign", c.post(f"{URL}/api/drafts/{d['id']}/send-for-review").status_code == 200)
    c.post(f"{URL}/api/demo/switch-role", json={"role": "reviewer"})
    for f in c.get(f"{URL}/api/versions/{v['version_id']}/review").json()["findings"]:
        if f["severity"] == "blocking" and f["status"] == "dismissed":
            c.post(f"{URL}/api/findings/{f['id']}/decision", json={"action": "override", "reason": "smoke test"})
    r = c.post(f"{URL}/api/drafts/{d['id']}/decision", json={"decision": "approve", "claims_reviewed": True})
    step("approve", r.status_code == 200, r.text[:120])
    h = c.get(f"{URL}/api/drafts/{d['id']}/history").json()
    step("audit chain verified", h["chain"]["ok"], f"{h['chain']['events']} events")
    step("export csv", c.get(f"{URL}/api/drafts/{d['id']}/export.csv").status_code == 200)
print("Smoke test passed")
