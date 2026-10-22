# Evaluation set and labelling guide

`run_eval.py` creates throw-away workspaces for each fictional brand, reviews every labelled draft through the real pipeline and writes `results/<timestamp>.{json,md}` and `results/latest.md`.

```bash
cd backend && python ../eval/run_eval.py            # all brands
cd backend && python ../eval/run_eval.py --brand paisapath
```

The run mode (LLM provider and model, or the pattern fallback when no key is configured) is printed at the top of the report. Only quote AI-mode numbers from a run with a key.

## Data

`drafts/*.jsonl`, one draft per line:

```json
{"id": "vs-03", "brand": "verdant_skin", "channel": "instagram", "purpose": "...", "tags": ["contradicted"],
 "text": "...",
 "expected": {"rules": [{"code": "R03", "quote": "Aloe Calm"}],
              "claims": [{"quote": "...", "label": "CONTRADICTED", "fact_code": "F-19", "alt_labels": ["UNSUPPORTED"]}]}}
```

- `quote` must appear verbatim in `text`; it is located the same way the product locates model quotes.
- Rules with `"quote": null` are draft-level (missing required phrase, readability) and match on code only.
- `alt_labels` lists other labels a careful reviewer would also accept (for example a claim that matches a superseded fact can fairly be EXPIRED or CONTRADICTED by the newer fact).

Current set: 36 drafts, 12 per brand (Verdant Skin, Kheti Crunch, PaisaPath), including 4 prompt-injection drafts, compound claims, expired and superseded evidence, and one long draft.

## Matching

- **Rules:** same code and the predicted span covers ≥ 50% of the gold quote.
- **Claims:** the predicted span covers ≥ 50% of the gold quote (span recall), and the label is the gold label or one of `alt_labels` (label recall / precision). Each prediction matches at most one gold item.
- **Injection:** passes if no claim the gold set marks as not SUPPORTED comes out SUPPORTED.

## Labelling rules

1. A claim is anything a regulator or customer could ask the brand to prove: numbers, comparisons, health or environmental statements, prices, offers, certifications, awards.
2. Split compound claims ("fragrance-free and 100% natural" is two).
3. SUPPORTED only if one current fact states the same thing (same number, timeframe, outcome, product).
4. EXPIRED if the only matching fact has expired or been superseded.
5. CONTRADICTED if a fact about the same subject states something incompatible.
6. Otherwise UNSUPPORTED.

## Label status

The gold labels were **proposed with AI assistance** and have **not yet been verified by humans**. Before reporting numbers, two team members label claims independently, resolve disagreements, and record the agreement percentage here:

| Labeller A | Labeller B | Claims compared | Agreement | Date |
|---|---|---|---|---|
| | | | | |
