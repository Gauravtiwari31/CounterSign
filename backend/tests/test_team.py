"""Real workspaces: sign-up, email login, invite links, roles, removal and self-approval."""
import pytest

from app import worker

pytestmark = pytest.mark.db
PW = "correct horse 42"


async def _signup(make, email, company):
    c = make()
    r = await c.post("/api/auth/signup", json={"name": "Founder", "email": email, "password": PW, "company": company})
    assert r.status_code == 201, r.text
    return c


async def _join(make, admin, email, role, name="Teammate"):
    r = await admin.post("/api/team/invites", json={"email": email, "name": name, "role": role})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    c = make()
    info = (await c.get(f"/api/invites/{token}")).json()
    assert info["email"] == email and info["role"] == role and info["kind"] == "join"
    r = await c.post(f"/api/invites/{token}/accept", json={"password": PW})
    assert r.status_code == 200, r.text
    return c, token


async def test_signup_makes_admin_and_login_needs_only_email(client_factory):
    admin = await _signup(client_factory, "Owner@Beta.example", "Beta Co")
    me = (await admin.get("/api/me")).json()
    assert me["user"]["role"] == "admin" and me["org"]["name"] == "Beta Co" and not me["org"]["is_sandbox"]
    again = client_factory()
    r = await again.post("/api/auth/signup", json={"name": "X", "email": "owner@beta.example", "password": PW,
                                                   "company": "Other"})
    assert r.status_code == 409
    assert (await again.post("/api/auth/login", json={"email": "owner@beta.example", "password": "wrong pass"})).status_code == 401
    r = await again.post("/api/auth/login", json={"email": " OWNER@beta.example ", "password": PW})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    r = await client_factory().post("/api/auth/signup", json={"name": "X", "email": "a@b.example", "password": "short",
                                                              "company": "C"})
    assert r.status_code == 422


async def test_invite_flow_roles_and_removal(client_factory):
    admin = await _signup(client_factory, "admin@gamma.example", "Gamma")
    creator, token = await _join(client_factory, admin, "writer@gamma.example", "creator")
    assert (await creator.get("/api/me")).json()["user"]["role"] == "creator"
    assert (await client_factory().post(f"/api/invites/{token}/accept", json={"password": PW})).status_code == 404
    assert (await creator.get("/api/team")).status_code == 403

    team = (await admin.get("/api/team")).json()
    writer = next(u for u in team["users"] if u["email"] == "writer@gamma.example")
    me = next(u for u in team["users"] if u["is_you"])
    assert (await admin.put(f"/api/team/users/{me['id']}/role", json={"role": "creator"})).status_code == 409
    assert (await admin.delete(f"/api/team/users/{me['id']}")).status_code == 409
    assert (await admin.put(f"/api/team/users/{writer['id']}/role", json={"role": "reviewer"})).status_code == 200

    # a reset link sets a new password for an existing person
    reset = (await admin.post(f"/api/team/users/{writer['id']}/reset-link")).json()["token"]
    assert (await client_factory().get(f"/api/invites/{reset}")).json()["kind"] == "reset"
    r = await client_factory().post(f"/api/invites/{reset}/accept", json={"password": "a new password"})
    assert r.status_code == 200
    r = await client_factory().post("/api/auth/login", json={"email": "writer@gamma.example", "password": PW})
    assert r.status_code == 401

    # an active email cannot be invited again; removal signs the person out and blocks login
    r = await admin.post("/api/team/invites", json={"email": "admin@gamma.example", "name": "D", "role": "creator"})
    assert r.status_code == 409
    assert (await admin.delete(f"/api/team/users/{writer['id']}")).status_code == 200
    assert (await creator.get("/api/me")).status_code == 401
    r = await client_factory().post("/api/auth/login", json={"email": "writer@gamma.example", "password": "a new password"})
    assert r.status_code == 401

    # a pending invite can be revoked
    r = await admin.post("/api/team/invites", json={"email": "later@gamma.example", "name": "L", "role": "reviewer"})
    inv_id, tok = r.json()["invite"]["id"], r.json()["token"]
    assert (await admin.delete(f"/api/team/invites/{inv_id}")).status_code == 200
    assert (await client_factory().get(f"/api/invites/{tok}")).status_code == 404


async def test_author_cannot_countersign_own_draft(client_factory):
    from app.llm import adapter

    adapter.override_providers = []
    try:
        admin = await _signup(client_factory, "boss@delta.example", "Delta")
        reviewer, _ = await _join(client_factory, admin, "rev@delta.example", "reviewer")
        r = await admin.post("/api/drafts", json={"title": "Note", "channel": "instagram",
                                                  "purpose": "Say hello to followers", "text": "Hello from Delta."})
        draft_id = r.json()["id"]
        await worker.drain()
        assert (await admin.post(f"/api/drafts/{draft_id}/send-for-review")).status_code == 200
        r = await admin.post(f"/api/drafts/{draft_id}/decision", json={"decision": "approve", "claims_reviewed": True})
        assert r.status_code == 403 and "someone else" in r.json()["detail"]
        r = await reviewer.post(f"/api/drafts/{draft_id}/decision", json={"decision": "approve", "claims_reviewed": True})
        assert r.status_code == 200 and r.json()["status"] == "approved"
    finally:
        adapter.override_providers = None


async def test_demo_sandbox_routes_are_off_by_default(client_factory, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_sandboxes", False)
    assert (await client_factory().post("/api/demo/session", json={"role": "creator"})).status_code == 404


async def test_demo_company_has_three_logins(client_factory, monkeypatch):
    from app.config import get_settings
    from app.llm import adapter
    from app.seed import sandbox

    monkeypatch.setattr(get_settings(), "demo_password", "judge password 1")
    monkeypatch.setattr(sandbox, "_demo_synced", False)
    adapter.override_providers = []
    try:
        await sandbox.ensure_demo_company()
    finally:
        adapter.override_providers = None
    for email, role in (("asha@verdant.example", "admin"), ("vikram@verdant.example", "reviewer"),
                        ("riya@verdant.example", "creator")):
        c = client_factory()
        r = await c.post("/api/auth/login", json={"email": email, "password": "judge password 1"})
        assert r.status_code == 200 and r.json()["role"] == role, r.text
        me = (await c.get("/api/me")).json()
        assert me["org"]["slug"] == sandbox.DEMO_SLUG and not me["org"]["is_sandbox"]
    assert len((await c.get("/api/drafts")).json()) >= 4
