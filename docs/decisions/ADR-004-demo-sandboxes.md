# ADR-004: Per-visitor demo sandboxes from a pre-built pool

**Status:** accepted

**Context.** Several judges may test at once. A shared demo workspace lets one judge's approvals and edits confuse another, and sign-up forms cost minutes of the 3-minute budget.

**Decision.** Each visitor gets a private copy of the Verdant Skin workspace, with Creator, Reviewer and Admin users and drafts in every workflow state. The worker keeps a small pool of sandboxes ready so the first click is instant; a header switcher changes role inside the same sandbox. Sandboxes expire after 48 hours.

**Consequences.** No accounts, no collisions, no empty screens. Role switching exists only in sandboxes; real workspaces use password login (`python -m app.seed.cli`).
