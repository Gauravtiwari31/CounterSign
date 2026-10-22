import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Organization, User
from app.security import COOKIE_NAME, decode_token


@dataclass
class Principal:
    user: User
    org: Organization

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id


async def current_principal(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    token = request.cookies.get(COOKIE_NAME)
    claims = decode_token(token) if token else None
    if not claims:
        raise HTTPException(401, "Not signed in")
    user = await session.get(User, uuid.UUID(claims["sub"]))
    if user is None or str(user.org_id) != claims["org"]:
        raise HTTPException(401, "Session no longer valid")
    org = await session.get(Organization, user.org_id)
    if org is None:
        raise HTTPException(401, "Workspace no longer exists")
    return Principal(user=user, org=org)


def require_role(*roles: str):
    async def _dep(p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(403, f"This action needs the {' or '.join(roles)} role")
        return p

    _dep.required_roles = roles  # read by the access-control test
    return _dep


class SlidingWindowLimiter:
    """Small in-process limiter; enough for one container."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_s: float = 3600) -> bool:
        now = monotonic()
        q = self._hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


limiter = SlidingWindowLimiter()
