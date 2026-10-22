# ADR-002: The model quotes; code finds offsets and verifies citations

**Status:** accepted

**Context.** LLMs are unreliable at character offsets and can invent citations. Wrong highlights or a fabricated "approved fact" would destroy reviewer trust.

**Decision.** No LLM output contains offsets. Claim and voice quotes are located in the draft by `locate()` (exact, normalised, then fuzzy within the sentence with matching numbers) and dropped if not found. Judge citations are accepted only if the fact code was a candidate for that claim and the quote is a word-for-word substring of the fact statement; otherwise the verdict is downgraded to UNSUPPORTED.

**Consequences.** Highlights always sit on the right words and citation validity is 100% by construction. Some correct but paraphrased model citations are downgraded; the count is reported by the eval harness as `verify_downgrades`.
