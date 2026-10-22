# Countersign evaluation (2026-10-22T11:02:41+00:00)

Mode: **LLM gemini gemini-3.5-flash** · 36 labelled drafts across 3 fictional brands.

| Metric | Round 1 target | Result |
|---|---|---|
| Rules precision | >= 0.95 | 1.0 (recall 1.0, n=25) |
| Claims recall (span + label) | >= 0.80 | 0.66 (span-only 0.894, n=47) |
| Claims precision (label) | >= 0.75 | 0.646 (48 predicted) |
| Citation validity | 100% | 100% by construction; 0 model citations downgraded |
| Injection attempts resisted | all | 4/4 |
| Rules latency | < 1 s | p50 7.6 ms, p95 21.5 ms |
| Full review latency | < 20 s p95 | p50 10.4 s, p95 24.4 s |
| LLM calls | report | 276 calls, 0 cache hits |

## Claim label confusion (gold -> predicted)

| gold \ predicted | SUPPORTED | UNSUPPORTED | CONTRADICTED | EXPIRED | MISSED |
|---|---|---|---|---|---|
| SUPPORTED | 11 | 9 | 0 | 0 | 2 |
| UNSUPPORTED | 0 | 8 | 3 | 0 | 1 |
| CONTRADICTED | 0 | 2 | 2 | 0 | 0 |
| EXPIRED | 0 | 1 | 0 | 6 | 2 |

## Per-draft problems

- **kc-01**: label UNSUPPORTED for SUPPORTED '10 g of protein'; label UNSUPPORTED for SUPPORTED '6 g of fibre'
- **kc-04**: extra claim SUPPORTED '40gms'
- **kc-05**: label UNSUPPORTED for CONTRADICTED 'Only 2 g of added sugar'
- **kc-06**: extra claim EXPIRED 'within 180 days'
- **pp-07**: missed claim SUPPORTED 'lessons are free for all users'; extra claim SUPPORTED 'free'
- **pp-08**: label UNSUPPORTED for EXPIRED '₹100 cashback on your first UPI payment'
- **pp-09**: label UNSUPPORTED for SUPPORTED 'reviewed by a SEBI-registered investment adviser'; missed claim SUPPORTED 'stored on servers in India'
- **pp-12**: extra claim SUPPORTED '12 lessons'
- **vs-01**: label UNSUPPORTED for SUPPORTED '92% aloe vera leaf juice'
- **vs-03**: extra claim CONTRADICTED 'in 3 days'
- **vs-04**: missed claim EXPIRED '20% off AloeCalm'; extra claim EXPIRED '20% off'
- **vs-07**: label UNSUPPORTED for SUPPORTED 'fragrance-free'
- **vs-08**: missed claim EXPIRED 'costs Rs. 599 for 30 ml'
- **vs-10**: missed claim UNSUPPORTED 'the No. 1 skincare brand in India'
- **vs-12**: label UNSUPPORTED for SUPPORTED '2% niacinamide'; label UNSUPPORTED for SUPPORTED '74% reported more even-looking skin tone'; label UNSUPPORTED for SUPPORTED 'fragrance-free'; label UNSUPPORTED for SUPPORTED 'priced at Rs 699 for 30 ml'

Labels: see eval/README.md for the labelling guide and status of human verification.