import csv
import html
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import current_version, draft_or_404, user_names
from app.api.routes_workflow import history
from app.db import get_session
from app.deps import Principal, current_principal
from app.models import Finding, FindingDecision
from app.schemas.finding import sort_key

router = APIRouter(prefix="/api", tags=["export"])


async def _record(session: AsyncSession, p: Principal, draft_id: uuid.UUID):
    draft = await draft_or_404(session, p, draft_id)
    if draft.status != "approved":
        raise HTTPException(409, "Only approved drafts can be exported")
    version = await current_version(session, draft)
    findings = sorted((await session.scalars(select(Finding).where(Finding.draft_version_id == version.id))).all(),
                      key=sort_key)
    decisions = (await session.scalars(select(FindingDecision).where(
        FindingDecision.finding_id.in_([f.id for f in findings])).order_by(FindingDecision.created_at))).all()
    by_finding: dict = {}
    for d in decisions:
        by_finding.setdefault(d.finding_id, []).append(d)
    return draft, version, findings, by_finding, await user_names(session, p.org_id)


@router.get("/drafts/{draft_id}/export.csv")
async def export_csv(draft_id: uuid.UUID, p: Principal = Depends(current_principal),
                     session: AsyncSession = Depends(get_session)):
    draft, version, findings, by_finding, users = await _record(session, p, draft_id)
    hist = await history(draft_id, p, session)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "version", "lane", "severity", "code_or_label", "span", "message", "evidence",
                "status", "decision_by", "decision_reason", "timestamp"])
    w.writerow(["approved_copy", version.version_no, "", "", "", version.text, draft.title, "", draft.status, "", "", ""])
    for f in findings:
        ev = "; ".join(f"{e['fact_code']}: {e.get('quote') or ''}" for e in f.evidence or [])
        ds = by_finding.get(f.id, [])
        last = ds[-1] if ds else None
        w.writerow(["finding", version.version_no, f.lane, f.severity, f.rule_code or f.claim_label or f.criterion_code,
                    f.span_text, f.message, ev, f.status, (users.get(last.actor_id) or {}).get("name") if last else "",
                    last.reason if last else "", last.created_at.isoformat() if last else ""])
    for d in hist["decisions"]:
        w.writerow(["workflow", d["version_no"], "", "", d["decision"], "", "", "", "", (d["actor"] or {}).get("name"),
                    d["reason"] or "", d["created_at"]])
    w.writerow(["audit_chain", "", "", "", "verified" if hist["chain"]["ok"] else "BROKEN", "", "", "", "", "", "",
                hist["chain"].get("head", "")])
    buf.seek(0)
    name = "".join(c if c.isalnum() else "-" for c in draft.title.lower())[:50]
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="countersign-{name}.csv"'})


@router.get("/drafts/{draft_id}/record", response_class=HTMLResponse)
async def printable_record(draft_id: uuid.UUID, p: Principal = Depends(current_principal),
                           session: AsyncSession = Depends(get_session)):
    draft, version, findings, by_finding, users = await _record(session, p, draft_id)
    hist = await history(draft_id, p, session)
    e = html.escape
    rows = []
    for f in findings:
        ds = by_finding.get(f.id, [])
        dec = "<br>".join(f"{e(d.action)} by {e((users.get(d.actor_id) or {}).get('name', '?'))}"
                          + (f": {e(d.reason)}" if d.reason else "") for d in ds) or "-"
        ev = "<br>".join(f"<b>{e(x['fact_code'])}</b> “{e(x.get('quote') or '')}” ({e(x.get('owner') or '')})"
                         for x in f.evidence or [] if x.get("role", "cited") == "cited") or "-"
        rows.append(f"<tr><td>{e(f.lane)}</td><td>{e(f.severity)}</td><td>{e(f.rule_code or f.claim_label or f.criterion_code or '')}</td>"
                    f"<td>“{e(f.span_text)}”</td><td>{e(f.message)}</td><td>{ev}</td><td>{e(f.status)}</td><td>{dec}</td></tr>")
    flow = "".join(f"<li>{e(d['created_at'][:16].replace('T', ' '))} UTC: <b>{e(d['decision'])}</b> by "
                   f"{e((d['actor'] or {}).get('name', '?'))} (v{d['version_no']}){': ' + e(d['reason']) if d['reason'] else ''}</li>"
                   for d in hist["decisions"])
    chain = hist["chain"]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Review record: {e(draft.title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 16px;color:#1b1f1d}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
pre{{white-space:pre-wrap;background:#f6f6f2;padding:12px;border:1px solid #ddd}}.ok{{color:#14532d}}.bad{{color:#991b1b}}
@media print{{button{{display:none}}}}</style></head><body>
<button onclick="print()">Print / save as PDF</button>
<h1>Countersign review record</h1>
<p><b>{e(draft.title)}</b> &middot; {e(draft.channel)} &middot; purpose: {e(draft.purpose)}<br>
Approved version v{version.version_no} &middot; rulebook v{version.rulebook_version} &middot; facts v{version.facts_version}
&middot; text sha256 <code>{version.text_hash[:16]}&hellip;</code></p>
<h2>Approved copy</h2><pre>{e(version.text)}</pre>
<h2>Findings on the approved version</h2>
<table><tr><th>Lane</th><th>Severity</th><th>Code / label</th><th>Text</th><th>Finding</th><th>Evidence</th><th>Status</th><th>Decisions</th></tr>
{''.join(rows) or '<tr><td colspan=8>No findings</td></tr>'}</table>
<h2>Workflow</h2><ul>{flow}</ul>
<p class="{'ok' if chain['ok'] else 'bad'}">Audit chain: {'verified' if chain['ok'] else 'BROKEN'} ({chain['events']} events)</p>
</body></html>"""
    return HTMLResponse(page)
