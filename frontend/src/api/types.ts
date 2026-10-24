export type Role = "creator" | "reviewer" | "admin";
export type Lane = "rules" | "claims" | "voice";
export type Severity = "blocking" | "warning" | "advisory" | "info";
export type ClaimLabel = "SUPPORTED" | "UNSUPPORTED" | "CONTRADICTED" | "EXPIRED";
export type Channel = "instagram" | "x" | "linkedin" | "email" | "product_page" | "ad";
export type DraftStatus =
  | "draft" | "checking" | "checked" | "in_review" | "changes_requested" | "approved" | "rejected";
export type FindingStatus = "open" | "accepted" | "edited" | "dismissed" | "overridden" | "resolved";

export interface Me {
  user: { id: string; name: string; email: string; role: Role };
  org: { id: string; name: string; slug: string; is_sandbox: boolean; rulebook_version: number;
         facts_version: number; expires_at: string | null };
}

export interface UserRef { id: string; name: string; role: Role }

export interface Evidence {
  fact_id: string | null; fact_code: string; statement: string | null; quote: string | null; verified: boolean;
  owner: string | null; source_document: string | null; source_locator: string | null; valid_to: string | null;
  status: string; superseded_by: string | null; role: "cited" | "candidate";
}

export interface Suggestion {
  replacement: string | null;
  kind: "deterministic" | "ai";
  approach: string | null;
  recheck: { rules_ok: boolean | null; claims_ok: boolean | null; intent_score: number | null } | null;
}

export interface Finding {
  id: string; lane: Lane; severity: Severity; source: "rule" | "ai" | "pattern";
  span: { start: number; end: number; text: string };
  rule: { id: string | null; code: string | null } | null;
  criterion_code: string | null;
  claim: { type: string | null; text: string | null; label: ClaimLabel | null } | null;
  evidence: Evidence[]; message: string; explanation: string; regulatory_prompt: string | null;
  suggestion: Suggestion | null; status: FindingStatus; carried_over: boolean;
  model: string | null; prompt_version: string | null;
}

export interface Review {
  version: { id: string; version_no: number; text: string; rulebook_version: number; facts_version: number };
  job: { status: "queued" | "running" | "done" | "failed"; lane_status: Record<string, string>;
         timings: Record<string, unknown>; ai_degraded: boolean; error: string | null } | null;
  findings: Finding[];
}

export interface Counts { blocking_open: number; claims: number; dismissed: number; advisory: number }

export interface DraftSummary {
  id: string; title: string; channel: Channel; purpose: string; status: DraftStatus; author: UserRef | null;
  current_version_no: number; current_version_id: string | null; created_at: string; updated_at: string;
  counts: Counts;
}

export interface DraftDetail extends DraftSummary {
  versions: { id: string; version_no: number; created_at: string; source_type: string;
              rulebook_version: number; facts_version: number }[];
  current_text: string;
  can: { edit: boolean; review: boolean };
}

export interface Comment {
  id: string; version_no: number; author: UserRef | null; body: string; finding_id: string | null; created_at: string;
}

export interface History {
  versions: { version_no: number; id: string; created_at: string; author: UserRef | null; source_type: string;
              text_hash: string; rulebook_version: number; facts_version: number }[];
  decisions: { version_no: number; decision: string; reason: string | null; claims_reviewed: boolean;
               actor: UserRef | null; created_at: string }[];
  finding_decisions: { version_no: number; action: string; reason: string | null; actor: UserRef | null;
                       finding: { id: string; lane: Lane; message: string; span: string; code: string | null };
                       created_at: string }[];
  audit: { id: number; action: string; actor: UserRef | null; payload: Record<string, unknown>; created_at: string;
           hash: string; prev_hash: string }[];
  chain: { ok: boolean; events: number; head?: string; broken_at?: number };
}

export interface Rule {
  id: string; code: string; type: string; params: Record<string, unknown>; severity: "blocking" | "warning" | "info";
  channels: string[] | null; title: string; description: string; introduced_in: number; retired_in: number | null;
}

export interface Fact {
  id: string; code: string; statement: string; source_document: string; source_locator: string; owner: string;
  scope_products: string[]; scope_channels: string[]; scope_regions: string[]; valid_from: string | null;
  valid_to: string | null; superseded_by: string | null; superseded_by_code: string | null;
  status: "valid" | "expired" | "superseded" | "expiring_soon"; introduced_in: number;
}

export interface Criterion {
  id: string; code: string; title: string; description: string; good_examples: string[]; bad_examples: string[];
}

export interface Palette {
  colors: { name: string; hex: string; role: "text" | "background" | "accent" }[];
  matrix: { foreground: string; foreground_hex: string; background: string; background_hex: string; ratio: number;
            aa_normal: boolean; aa_large: boolean; aaa_normal: boolean }[];
}

export interface Services {
  llm: { role: string; provider: string; model: string }[]; llm_configured: boolean; llm_note: string | null;
  llm_data_use: string; embeddings: string; pii_masking: string; hosting: string; database: string;
  data_sent_to_llm: string;
}

export const CHANNEL_LABEL: Record<Channel, string> = {
  instagram: "Instagram", x: "X", linkedin: "LinkedIn", email: "Email", product_page: "Product page", ad: "Ad",
};

export const STATUS_LABEL: Record<DraftStatus, string> = {
  draft: "Draft", checking: "Checking", checked: "Checked", in_review: "Awaiting countersign",
  changes_requested: "Changes requested", approved: "Approved", rejected: "Rejected",
};

export interface TeamUser { id: string; name: string; email: string; role: Role; is_you: boolean; active: boolean; has_password: boolean }
export interface TeamInvite { id: string; email: string; name: string; role: Role; kind: "join" | "reset"; expires_at: string; expired: boolean }
export interface Team { users: TeamUser[]; invites: TeamInvite[] }
export interface InviteInfo { email: string; name: string; role: Role; org_name: string; kind: "join" | "reset" }
