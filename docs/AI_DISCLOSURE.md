# AI use disclosure

## In the product

- **Claims lane:** an LLM extracts claims and judges them against retrieved facts. Code locates every quote, verifies every citation word for word and decides the final label. Findings produced this way are labelled **AI**.
- **Voice lane:** an LLM writes advisory notes against the brand voice rubric. They can never block approval.
- **Fixes:** an LLM proposes rewrites for flagged spans; code rejects any that add numbers, trigger rules, keep unsupported claims or score below 4/5 on intent.
- **Providers:** Gemini (primary) and Groq (fallback), configured by environment variables and listed in Settings → External services. Personal data is masked before any call. Embeddings are computed locally (fastembed), so evidence text used for retrieval does not leave the server.
- Rule findings are deterministic and labelled **Rule**; pattern-fallback findings are labelled **Pattern, needs human review**.

## In building the product

Parts of the code, tests, seed data, evaluation drafts and documentation were drafted with an AI coding assistant and then reviewed, run and corrected by the team. In particular:

- The evaluation drafts and their gold labels were proposed with AI assistance. Per our Round 1 commitment, labels must be verified independently by two team members before the numbers are reported (see `eval/README.md`).
- The fictional brands, products, facts and people were written for this project and do not describe real companies.

All product code was written during the Round 2 window.
