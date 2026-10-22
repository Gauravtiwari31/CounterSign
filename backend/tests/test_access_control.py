"""Walks the FastAPI route table: org B can never reach org A's resources (404), and role-restricted routes
return 403 for the wrong role. This is the Round 1 "isolation proven by automated tests" commitment."""
import re

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.models import Draft, DraftVersion, Fact, Finding, Rule, VoiceCriterion
from tests.conftest import demo_client

pytestmark = pytest.mark.db

RULE_BODY = {"code": "Z99", "type": "all_caps", "params": {}, "severity": "warning", "title": "t"}
FACT_BODY = {"code": "F-99", "statement": "A test statement here."}
BODIES = {
    ("POST", "/api/drafts/{draft_id}/versions"): {"text": "hello"},
    ("POST", "/api/drafts/{draft_id}/decision"): {"decision": "approve", "claims_reviewed": True},
    ("POST", "/api/drafts/{draft_id}/comments"): {"body": "hi"},
    ("POST", "/api/findings/{finding_id}/decision"): {"action": "dismiss", "reason": "r"},
    ("PUT", "/api/rules/{rule_id}"): RULE_BODY,
    ("PUT", "/api/facts/{fact_id}"): FACT_BODY,
    ("PUT", "/api/voice-criteria/{criterion_id}"): {"code": "V9", "title": "t"},
}
PUBLIC = {"/api/health", "/api/health/deep", "/api/auth/login", "/api/auth/logout", "/api/demo/session"}


async def _org_a_ids(session_factory, org_slug_client) -> dict:
    me = (await org_slug_client.get("/api/me")).json()
    org_id = me["org"]["id"]
    async with session_factory() as s:
        draft = await s.scalar(select(Draft).where(Draft.org_id == org_id).limit(1))
        version = await s.scalar(select(DraftVersion).where(DraftVersion.draft_id == draft.id).limit(1))
        finding = await s.scalar(select(Finding).join(DraftVersion).join(Draft).where(Draft.org_id == org_id).limit(1))
        return {
            "draft_id": draft.id, "version_id": version.id, "finding_id": finding.id, "n": 1,
            "rule_id": await s.scalar(select(Rule.id).where(Rule.org_id == org_id).limit(1)),
            "fact_id": await s.scalar(select(Fact.id).where(Fact.org_id == org_id).limit(1)),
            "criterion_id": await s.scalar(select(VoiceCriterion.id).where(VoiceCriterion.org_id == org_id).limit(1)),
        }


def _api_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route


async def test_cross_org_access_is_404(app, client_factory):
    from app.db import SessionLocal

    a = await demo_client(client_factory, "admin")
    b = await demo_client(client_factory, "admin")
    ids = await _org_a_ids(SessionLocal, a)
    checked = 0
    for method, route in _api_routes(app):
        params = re.findall(r"{(\w+)}", route.path)
        if not params:
            continue
        url = route.path.format(**{p: ids[p] for p in params})
        r = await b.request(method, url, json=BODIES.get((method, route.path)),
                            params={"from": 1, "to": 1} if route.path.endswith("/diff") else None)
        assert r.status_code == 404, f"{method} {route.path} -> {r.status_code} {r.text[:200]}"
        checked += 1
    assert checked >= 15


async def test_unauthenticated_requests_are_401(app, client_factory):
    anon = client_factory()
    for method, route in _api_routes(app):
        if route.path in PUBLIC or "{" in route.path:
            continue
        r = await anon.request(method, route.path, json={})
        assert r.status_code in (401, 422), f"{method} {route.path} -> {r.status_code}"
        if r.status_code == 422:  # body validated first; still must not succeed
            assert method in ("POST", "PUT")


async def test_role_restricted_routes_return_403(app, client_factory):
    from app.db import SessionLocal

    owner = await demo_client(client_factory, "admin")
    ids = await _org_a_ids(SessionLocal, owner)
    clients = {"admin": owner}
    # every role lives in the owner's sandbox, so a 404 can never mask a missing role check
    for role in ("creator", "reviewer"):
        c = client_factory()
        c.cookies = owner.cookies
        await c.post("/api/demo/switch-role", json={"role": role})
        clients[role] = c
    checked = 0
    for method, route in _api_routes(app):
        roles = None
        for dep in route.dependant.dependencies:
            roles = getattr(dep.call, "required_roles", None) or roles
        if not roles:
            continue
        for role, c in clients.items():
            if role in roles:
                continue
            params = re.findall(r"{(\w+)}", route.path)
            url = route.path.format(**{p: ids[p] for p in params})
            body = BODIES.get((method, route.path)) or (RULE_BODY if "rules" in route.path else
                                                        FACT_BODY if "facts" in route.path else {"title": "t"})
            if route.path == "/api/rules/test":
                body = {"rule": RULE_BODY, "text": "x"}
            if route.path == "/api/palette":
                body = []
            if route.path == "/api/drafts":
                body = {"title": "t", "channel": "x", "purpose": "ppp", "text": "x"}
            r = await c.request(method, url, json=body)
            assert r.status_code == 403, f"{role} {method} {route.path} -> {r.status_code} {r.text[:200]}"
            checked += 1
    assert checked >= 10
