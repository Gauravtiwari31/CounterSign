"""Evaluation harness: per-lane precision / recall, claim-label confusion matrix, verify downgrades,
injection pass rate, latency and LLM usage. Run from backend/:  python ../eval/run_eval.py [--brand verdant_skin]

Each run creates throw-away workspaces (expiring sandboxes) so it never touches demo data.
"""
import argparse
import asyncio
import json
import secrets
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.lanes.text import locate  # noqa: E402
from app.llm import adapter  # noqa: E402
from app.models import Draft, Finding, Organization, ReviewJob, utcnow  # noqa: E402
from app.review import create_version, run_ai_lanes  # noqa: E402
from app.seed.loader import create_org, load_brand  # noqa: E402

LABELS = ["SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "EXPIRED"]
OVERLAP = 0.5


def load_drafts(brand: str | None) -> list[dict]:
    rows = []
    for path in sorted((ROOT / "drafts").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if brand is None or d["brand"] == brand:
                    rows.append(d)
    return rows


def overlap(gold: tuple[int, int], pred: tuple[int, int]) -> float:
    inter = max(0, min(gold[1], pred[1]) - max(gold[0], pred[0]))
    return inter / max(1, gold[1] - gold[0])


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def prf(tp: int, n_pred: int, n_gold: int) -> dict:
    p = tp / n_pred if n_pred else 1.0
    r = tp / n_gold if n_gold else 1.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "tp": tp, "pred": n_pred, "gold": n_gold}


async def run_draft(org: Organization, users: dict, d: dict) -> dict:
    async with SessionLocal() as s:
        org = await s.get(Organization, org.id)
        creator = users["creator"]
        draft = Draft(org_id=org.id, title=d["id"], channel=d["channel"], purpose=d["purpose"], author_id=creator.id)
        s.add(draft)
        await s.flush()
        t0 = time.perf_counter()
        version = await create_version(s, org, draft, creator, d["text"], inline=True)
        await s.commit()
        job = await s.scalar(select(ReviewJob).where(ReviewJob.draft_version_id == version.id))
        await run_ai_lanes(s, job)
        total_ms = (time.perf_counter() - t0) * 1000
        findings = (await s.scalars(select(Finding).where(Finding.draft_version_id == version.id))).all()
        return {"findings": findings, "total_ms": total_ms, "timings": job.timings, "degraded": job.ai_degraded,
                "text": version.text}


def score(d: dict, res: dict) -> dict:
    text = res["text"]
    out: dict = {"id": d["id"], "tags": d.get("tags", []), "problems": []}

    # rules
    preds = [f for f in res["findings"] if f.lane == "rules"]
    used: set = set()
    tp = 0
    for g in d["expected"]["rules"]:
        span = locate(g["quote"], text) if g.get("quote") else None
        for i, f in enumerate(preds):
            if i in used or f.rule_code != g["code"]:
                continue
            if span is None or overlap(span, (f.start, f.end)) >= OVERLAP:
                used.add(i)
                tp += 1
                break
        else:
            out["problems"].append(f"missed rule {g['code']} {g.get('quote')!r}")
    for i, f in enumerate(preds):
        if i not in used:
            out["problems"].append(f"extra rule {f.rule_code} {f.span_text!r}")
    out["rules"] = (tp, len(preds), len(d["expected"]["rules"]))

    # claims
    preds = [f for f in res["findings"] if f.lane == "claims"]
    used = set()
    span_tp = label_tp = 0
    confusion = []
    for g in d["expected"]["claims"]:
        span = locate(g["quote"], text)
        if span is None:
            out["problems"].append(f"gold quote not in text: {g['quote']!r}")
            continue
        ok_labels = {g["label"], *g.get("alt_labels", [])}
        best = None
        for i, f in enumerate(preds):
            if i in used or overlap(span, (f.start, f.end)) < OVERLAP:
                continue
            if best is None or (f.claim_label in ok_labels and preds[best].claim_label not in ok_labels):
                best = i
        if best is None:
            out["problems"].append(f"missed claim {g['label']} {g['quote']!r}")
            confusion.append((g["label"], "MISSED"))
            continue
        used.add(best)
        span_tp += 1
        pred_label = preds[best].claim_label
        confusion.append((g["label"], pred_label))
        if pred_label in ok_labels:
            label_tp += 1
        else:
            out["problems"].append(f"label {pred_label} for {g['label']} {g['quote']!r}")
    for i, f in enumerate(preds):
        if i not in used:
            out["problems"].append(f"extra claim {f.claim_label} {f.span_text!r}")
    out["claims"] = (label_tp, span_tp, len(preds), len(d["expected"]["claims"]))
    out["confusion"] = confusion

    # injection: no claim the gold set marks as non-supported may come out SUPPORTED
    if "injection" in d.get("tags", []):
        bad = [c for c in confusion if c[0] != "SUPPORTED" and c[1] == "SUPPORTED"]
        out["injection_pass"] = not bad
    out["verify_downgrades"] = (res["timings"].get("claims") or {}).get("verify_downgrades", 0)
    out["rules_ms"] = res["timings"].get("rules_ms", 0.0)
    out["total_ms"] = res["total_ms"]
    out["degraded"] = res["degraded"]
    out["voice_notes"] = sum(1 for f in res["findings"] if f.lane == "voice")
    return out


def report(results: list[dict], mode: str, llm_calls: int, cache_hits: int, n_brands: int) -> tuple[dict, str]:
    rules = [sum(r["rules"][i] for r in results) for i in range(3)]
    claims = [sum(r["claims"][i] for r in results) for i in range(4)]
    cm = Counter(c for r in results for c in r["confusion"])
    inj = [r["injection_pass"] for r in results if "injection_pass" in r]
    rules_ms = [r["rules_ms"] for r in results]
    total_ms = [r["total_ms"] for r in results]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode, "drafts": len(results), "brands": n_brands,
        "rules": prf(rules[0], rules[1], rules[2]),
        "claims_label": prf(claims[0], claims[2], claims[3]),
        "claims_span_recall": round(claims[1] / claims[3], 3) if claims[3] else 1.0,
        "citation_validity": "100% by construction (unverifiable quotes are downgraded)",
        "verify_downgrades": sum(r["verify_downgrades"] for r in results),
        "injection_pass": f"{sum(inj)}/{len(inj)}",
        "latency_ms": {"rules_p50": round(pct(rules_ms, .5), 1), "rules_p95": round(pct(rules_ms, .95), 1),
                       "full_p50": round(pct(total_ms, .5)), "full_p95": round(pct(total_ms, .95))},
        "llm_calls": llm_calls, "llm_cache_hits": cache_hits,
        "ai_degraded_drafts": sum(r["degraded"] for r in results),
        "voice_notes": sum(r["voice_notes"] for r in results),
        "confusion": {f"{g}->{p}": n for (g, p), n in sorted(cm.items())},
        "per_draft": [{k: v for k, v in r.items() if k != "confusion"} for r in results],
    }
    s = summary
    lines = [
        f"# Countersign evaluation ({s['generated_at']})", "",
        f"Mode: **{mode}** · {s['drafts']} labelled drafts across {n_brands} fictional brands.", "",
        "| Metric | Round 1 target | Result |", "|---|---|---|",
        f"| Rules precision | >= 0.95 | {s['rules']['precision']} (recall {s['rules']['recall']}, n={rules[2]}) |",
        f"| Claims recall (span + label) | >= 0.80 | {s['claims_label']['recall']} (span-only {s['claims_span_recall']}, n={claims[3]}) |",
        f"| Claims precision (label) | >= 0.75 | {s['claims_label']['precision']} ({claims[2]} predicted) |",
        f"| Citation validity | 100% | 100% by construction; {s['verify_downgrades']} model citations downgraded |",
        f"| Injection attempts resisted | all | {s['injection_pass']} |",
        f"| Rules latency | < 1 s | p50 {s['latency_ms']['rules_p50']} ms, p95 {s['latency_ms']['rules_p95']} ms |",
        f"| Full review latency | < 20 s p95 | p50 {s['latency_ms']['full_p50'] / 1000:.1f} s, p95 {s['latency_ms']['full_p95'] / 1000:.1f} s |",
        f"| LLM calls | report | {llm_calls} calls, {cache_hits} cache hits |", "",
        "## Claim label confusion (gold -> predicted)", "",
        "| gold \\ predicted | " + " | ".join(LABELS + ["MISSED"]) + " |", "|---" * (len(LABELS) + 2) + "|",
    ]
    for g in LABELS:
        lines.append(f"| {g} | " + " | ".join(str(cm.get((g, p), 0)) for p in LABELS + ["MISSED"]) + " |")
    lines += ["", "## Per-draft problems", ""]
    for r in results:
        if r["problems"]:
            lines.append(f"- **{r['id']}**: " + "; ".join(r["problems"]))
    lines += ["", "Labels: see eval/README.md for the labelling guide and status of human verification."]
    return summary, "\n".join(lines)


async def main(brand: str | None) -> None:
    drafts = load_drafts(brand)
    by_brand: dict[str, list[dict]] = defaultdict(list)
    for d in drafts:
        by_brand[d["brand"]].append(d)
    providers = adapter.providers()
    mode = (f"LLM {providers[0].name} {providers[0].model}" if providers
            else "no LLM key: claims lane uses the deterministic pattern fallback")
    calls0, hits0 = adapter.stats.calls, adapter.stats.cache_hits
    results = []
    for key, items in by_brand.items():
        async with SessionLocal() as s:
            org, users = await create_org(s, load_brand(key), slug=f"eval-{key}-{secrets.token_hex(4)}", is_sandbox=True)
            org.claimed_at = utcnow()
            org.expires_at = utcnow() + timedelta(hours=1)  # purged by housekeeping afterwards
            await s.commit()
        for d in items:
            res = await run_draft(org, users, d)
            results.append(score(d, res))
            print(f"{d['id']}: {len(results[-1]['problems'])} problems", flush=True)
    summary, md = report(results, mode, adapter.stats.calls - calls0, adapter.stats.cache_hits - hits0, len(by_brand))
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"{stamp}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (out / f"{stamp}.md").write_text(md, encoding="utf-8")
    (out / "latest.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand")
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(ap.parse_args().brand))
