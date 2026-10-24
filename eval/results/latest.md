# Countersign evaluation (2026-10-24T06:17:17+00:00)

Mode: **LLM gemini gemini-3.5-flash · answered by gemini-3.5-flash-lite (42)** · **compact mode** (1 call per review, +1 to verify fixes) · 36 labelled drafts across 3 fictional brands.

| Metric | Round 1 target | Result |
|---|---|---|
| Rules precision | >= 0.95 | 1.0 (recall 1.0, n=25) |
| Claims recall (span + label) | >= 0.80 | 0.915 (span-only 0.915, n=47) |
| Claims precision (label) | >= 0.75 | 0.956 (45 predicted) |
| Citation validity | 100% | 100% by construction; 0 model citations downgraded |
| Injection attempts resisted | all | 4/4 |
| Rules latency | < 1 s | p50 5.4 ms, p95 10.2 ms |
| Full review latency | < 20 s p95 | p50 4.8 s, p95 10.2 s |
| LLM calls | report | 43 calls, 3 cache hits |
| Drafts on pattern fallback | 0 | 0 of 36 |

## Claim label confusion (gold -> predicted)

| gold \ predicted | SUPPORTED | UNSUPPORTED | CONTRADICTED | EXPIRED | MISSED |
|---|---|---|---|---|---|
| SUPPORTED | 21 | 0 | 0 | 0 | 1 |
| UNSUPPORTED | 0 | 8 | 2 | 0 | 2 |
| CONTRADICTED | 0 | 0 | 4 | 0 | 0 |
| EXPIRED | 0 | 0 | 1 | 7 | 1 |

## Per-draft problems

- **pp-04**: missed claim UNSUPPORTED 'you will earn 12% every year'; extra claim CONTRADICTED 'will earn 12%'
- **pp-11**: extra claim UNSUPPORTED 'Investments are subject to market risks'
- **pp-12**: missed claim SUPPORTED '12 lessons of about 10 minutes each'
- **vs-08**: missed claim EXPIRED 'costs Rs. 599 for 30 ml'
- **vs-10**: missed claim UNSUPPORTED 'the No. 1 skincare brand in India'

Labels: see eval/README.md for the labelling guide and status of human verification.