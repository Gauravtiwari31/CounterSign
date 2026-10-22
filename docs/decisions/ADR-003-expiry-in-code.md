# ADR-003: Retrieval includes expired facts; expiry is decided in code

**Status:** accepted (changes the Round 1 plan, which filtered by validity at retrieval)

**Context.** If retrieval hides expired or superseded facts, a claim based on an old offer or an old statistic finds no evidence and is labelled UNSUPPORTED, which tells the creator nothing about *why*.

**Decision.** Retrieval returns expired and superseded facts with everything else. The label step checks `valid_to` and `superseded_by` and labels a claim supported only by such a fact as EXPIRED, naming the date or the newer fact.

**Consequences.** Outdated claims are visible as outdated. The judge prompt never sees validity metadata, so its verdict is about meaning only.
