## Problem & framing

- Many messy sources per candidate (CSV, ATS, GitHub, LinkedIn, recruiter notes, resume), conflicting and duplicated.
- Goal: **one canonical profile** — normalized, deduped — plus **provenance** (where each value came from) and a **confidence** per field, and a **runtime config** that reshapes the output with no engine change.
- North star: **wrong-but-confident is the worst outcome.** Unknowns become `null`, never invented; a garbage source never crashes the run.

## Architecture tour

- Pipeline: `detect → extract → normalize → match → merge → confidence → project → validate` — open `[pipeline.py](src/transformer/pipeline.py)`, it's the table of contents.
- **The one rule:** an immutable internal **canonical record**, and a separate read-only **projection** layer. Same engine serves any output schema.
- One adapter per source (`[sources/](src/transformer/sources/)`), all satisfying a tiny `Adapter` protocol → adding a source is one file. **2 structured** (CSV, ATS) + **4 unstructured** (notes, GitHub, LinkedIn, resume) — covers both required groups. GitHub and LinkedIn adapters accept **URLs directly** (live fetch).
- Pure normalizers (`[normalize/](src/transformer/normalize/)`): phones→E.164, dates→YYYY-MM, country→ISO-2, skills→canonical. Each returns the value or `None`, never raises.



NOTE: 

- **GitHub:** URL (live fetch). Unauthenticated API → low rate limit (60 req/hr/IP); large profiles may be throttled.

- **LinkedIn:** URL (live fetch) or cached JSON export. **Live fetch is effectively non-functional** — LinkedIn blocks unauthenticated requests (`HTTP Error 999`), so URL input degrades gracefully to empty. **Reliable path = cached JSON export.** Compliant vendors (People Data Labs, Coresignal, Bright Data) are the only at-scale option, paid + not yet integrated.

## Design decision I'm proud of

- **One trust table → both merge and confidence** (`[trust.py](src/transformer/trust.py)`).
  - Claim score = `trust(source, field) × method_factor` (direct 1.0 / regex 0.8 / inferred 0.6).
  Example: phone from CSV column = trust(CSV, phone)=0.95 × 1.0 = 0.95. Phone regex'd from notes = trust(notes, phone)=0.5 × 0.8 = 0.4. CSV wins.
  - **Field-source affinity:** contact info trusts CSV/ATS; skills trust GitHub/resume; experience/headline trust LinkedIn/resume. Show the table.
  - Agreement is reinforced with **noisy-OR** `1 − Π(1−cᵢ)`; conflict gets a penalty.
  cᵢ = claim score from source i (0–1)
  (1−cᵢ) = probability source i is wrong
  Π(1−cᵢ) = probability all sources are wrong (assuming independence)
  1 − Π(1−cᵢ) = probability at least one source is right
  Example: two sources each 0.8. Single = 0.8. Together = 1 − (0.2 × 0.2) = 1 − 0.04 = 0.96. Agreement → higher. 
  - Why I like it: one small fixed policy, deterministic, no black box, **one place to tune or defend**.
- Honesty beat: `**candidate_id` determinism bug I caught.** I first hashed a *list* of match keys with duplicates, so adding a 6th source that shared an email changed the id. Fixed to hash the **distinct set**.

## Run the DEFAULT config

```bash
candidate-transformer --csv data/samples/recruiter.csv --ats data/samples/ats.json \
  --ats data/samples/garbage.json --notes data/samples/notes.txt \
  --github https://github.com/janedoe --linkedin data/samples/linkedin_jane.json \
  --resume data/samples/resume_jane.pdf --config data/configs/default.json \
  --out outputs/default_output.json -v
```

- `WARNING: skipping ... garbage.json` then `wrote 2 profile(s)` → robust.
- Open `[outputs/default_output.json](outputs/default_output.json)`: Jane merged from **6 sources**; `provenance` traces every field to source+method; `overall_confidence: 0.94`; per-skill confidence + sources.

## Edge cases I handled

1. **Conflict**: Jane's two phones (`…0142` CSV vs `…0199` ATS) — **both kept**, both in provenance, `phones[0]` is the higher-trust CSV one. `years_experience` 8 (ATS) beats notes' 9, with a confidence penalty.
2. **Garbage** `garbage.json` (broken JSON) → skipped + warned, run completes.
3. **Dedup**: same Jane across all 6 sources, merged by email.
4. **Absent field**: Sam has no phone/links → `null` (and `github` *omitted* under the custom config).
5. **Un-normalizable**: "call me after 5pm" → no phone; "Summer 2018" → `null` start date; unknown skills `Frobnicator` (ATS) + `Leadership` (LinkedIn) kept but discounted.
6. Mention the **location** call: LinkedIn's "San Francisco Bay Area" is more trusted but less complete than ATS's "San Francisco, CA, US" → I rank location by **completeness first** so we keep the country.

## Run the CUSTOM config

```bash
candidate-transformer --csv data/samples/recruiter.csv --ats data/samples/ats.json \
  --notes data/samples/notes.txt --github https://github.com/janedoe \
  --linkedin data/samples/linkedin_jane.json --resume data/samples/resume_jane.pdf \
  --config data/configs/custom_compact.json --out outputs/custom_output.json
```

- Open `[outputs/custom_output.json](outputs/custom_output.json)`: **same engine, different shape**.
  - rename + path DSL: `primary_email` ← `emails[0]`, `skills` ← `skills[].name`.
  - `normalize`: `phone` → E.164, re-applied at projection.
  - `on_missing`: Jane has `github`; **Sam's `github` key is omitted**; `twitter` is `null` for both.
  - `include_confidence` attaches `overall_confidence` to the custom shape too.

## Determinism, validation, tests, scope

- Fixed tables + stable sorts + content-hash id → **byte-stable output** (gold test runs the pipeline twice and asserts equality).
- Every projected output is **validated** against the config's declared types/required before return.
- `pytest -q` → **60 passed** (normalizers, matching, merge, confidence, projection, validation, robustness, gold).
- **Descoped honestly:** LinkedIn live fetch (no public API — URL accepted, degrades gracefully if blocked), heavy PDF/DOCX layout (sample resume is a single-column `.pdf` read via `pypdf`; rich multi-column layout out of scope), fuzzy/ML matching (exact only — avoids wrong merges), full UI (CLI).

## Close

- "Deterministic, explainable, robust, and every value is traceable. The trust
policy and the canonical/projection split are the two ideas everything else
hangs off." Show `pytest` green.

