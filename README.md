# Multi-Source Candidate Data Transformer

Ingest messy candidate data from many sources (recruiter CSV, ATS JSON, GitHub,
LinkedIn, recruiter notes, resume) and emit **one clean canonical profile per candidate** —
normalized, deduplicated across sources, with full **provenance** (where each
value came from) and a **confidence** score per field. A runtime **config**
reshapes the output (a projection layer) with no engine changes.

Design goals (from the brief): **deterministic & explainable**, **robust**
(a garbage source never crashes the run; unknowns become `null`, never invented),
and able to **scale to thousands** of candidates.

> One-page design: [`design/DESIGN.md`](design/DESIGN.md).

## Quickstart

```bash
# Python 3.11+
python3 -m venv .venv && source .venv/bin/activate
pip install -e .              # installs the `candidate-transformer` command (incl. PDF resume support)
# tests only ->                    pip install -e ".[dev]"
```

**Default schema (full canonical profile):**

```bash
candidate-transformer \
  --csv      data/samples/recruiter.csv \
  --ats      data/samples/ats.json \
  --ats      data/samples/garbage.json \
  --notes    data/samples/notes.txt \
  --github   data/samples/github_jane.json \
  --linkedin data/samples/linkedin_jane.json \
  --resume   data/samples/resume_jane.pdf \
  --config   data/configs/default.json \
  --out      outputs/default_output.json -v
```

**Custom shape (subset + rename + normalize + on_missing):**

```bash
candidate-transformer \
  --csv data/samples/recruiter.csv --ats data/samples/ats.json \
  --notes data/samples/notes.txt --github data/samples/github_jane.json \
  --linkedin data/samples/linkedin_jane.json --resume data/samples/resume_jane.pdf \
  --config data/configs/custom_compact.json \
  --out outputs/custom_output.json
```

Produced outputs are committed in [`outputs/`](outputs/). Without `--config` the
full canonical profile is emitted. `garbage.json` is intentionally malformed —
it is skipped with a warning to demonstrate robustness.

**Flags are optional** — `--input FILE` auto-detects the source type by
extension/content (explicit flags always win):

```bash
candidate-transformer --input data/samples/recruiter.csv --input data/samples/ats.json
```

**Run the tests:**

```bash
pip install -e ".[dev]"
pytest -q          # 58 tests: normalizers, matching, merge, confidence,
                   # projection, validation, robustness, gold end-to-end
```

## How it works

```
detect -> extract -> normalize -> match -> merge -> confidence -> project -> validate
```

| Stage | Module | What it does |
|------|--------|--------------|
| detect + extract + normalize | `sources/*` + `normalize/*` | One adapter per source — **structured:** `recruiter_csv`, `ats_json` (remaps its own field names); **unstructured:** `recruiter_notes`, `github`, `linkedin`, `resume`. Each parses into partial profiles (`SourceRecord`) in our canonical field names, calling the pure normalizers as it goes. A bad source returns `[]` + a warning. Adding a source = one new file implementing the `Adapter` protocol. |
| match | `matching.py` | Union-find on **strong identifiers** — normalized email, E.164 phone, canonicalized profile URLs (LinkedIn/GitHub). No matching on name/company/skill/location — a wrong merge is the worst outcome. |
| merge | `merge.py` | Per field: scalar fields pick a trust-ranked winner; list fields are deduped unions. All competing claims recorded in provenance. |
| confidence | `confidence.py` | `trust × method`, agreement reinforced by noisy-OR, conflict penalized. |
| project | `projection.py` | Build the requested output from the canonical record + config (path DSL, rename, normalize, toggles, on_missing). Read-only over the canonical record. |
| validate | `validation.py` | Check projected output against the config's declared types + required flags. |
| orchestration | `pipeline.py` | The readable table of contents tying it together. |

The **trust table lives in one place** (`trust.py`) and is read by both merge and
confidence, so there is a single policy to tune and defend.

### Canonical schema & normalized formats
`candidate_id` · `full_name` · `emails[]` · `phones[]` (**E.164**) ·
`location{city, region, country}` (country **ISO-3166 alpha-2**) ·
`links{linkedin, github, portfolio, other[]}` · `headline` ·
`years_experience` · `skills[{name, confidence, sources[]}]` (**canonical names**) ·
`experience[{company, title, start, end, summary}]` (**dates YYYY-MM**) ·
`education[{institution, degree, field, end_year}]` · `provenance[{field, source, method}]` ·
`overall_confidence`.

### Runtime config (the projection layer)
```jsonc
{
  "fields": [
    { "path": "full_name",     "type": "string",   "required": true },
    { "path": "primary_email", "from": "emails[0]",        "type": "string" },
    { "path": "phone",         "from": "phones[0]",        "type": "string",   "normalize": "E164" },
    { "path": "skills",        "from": "skills[].name",    "type": "string[]", "normalize": "canonical" },
    { "path": "github",        "from": "links.github",     "type": "string",   "on_missing": "omit" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```
- **`from` path DSL:** dotted paths, `[i]` index, `[]` map-over-array (`skills[].name`).
- **`normalize`:** `E164` | `canonical` | `iso2` | `yyyy_mm`, re-applied at projection time.
- **`on_missing`:** `null` | `omit` | `error`, global with per-field override.
- **toggles:** `include_provenance`, `include_confidence`.
- No `fields` ⇒ the full canonical profile.

## Edge cases handled (see the samples + `tests/`)
1. **Conflicting values** — Jane's two phones are both kept; `phones[0]` is the higher-trust CSV number; both sources appear in provenance. `years_experience` 8 (ATS) beats notes' 9 with a confidence penalty.
2. **Garbage source** — `garbage.json` (broken JSON) is skipped with a warning; the run completes.
3. **Duplicate person** — Jane appears in all 5 sources and is merged via email.
4. **Field absent everywhere** — Sam has no phone/links; they become `null` (and `github` is *omitted* under the custom config's `on_missing: omit`).
5. **Un-normalizable value** — "call me after 5pm" → no phone; "Summer 2018" → null start date; unknown skills (`Frobnicator` from ATS, `Leadership` from LinkedIn) → kept but discounted. Nothing is invented.

## Determinism
Fixed trust tables, stable sort orders, content-hash `candidate_id`, no wall-clock
or RNG → **byte-stable output for identical inputs** (asserted by the gold-profile test).

## Assumptions
- Default phone region is **US** (configurable in `normalize/phones.py`); a `+`-prefixed number ignores it.
- Email is lower-cased and used as the primary identity key.
- GitHub merges into a person only if the profile exposes a public **email** (the API returns one when public); otherwise it stands alone, since we match on email/phone only.
- Resume parsing targets clean single-column prose with `SKILLS` / `EXPERIENCE` / `EDUCATION` headings.
- GitHub and LinkedIn read **cached JSON fixtures** (`data/samples/*.json`) — offline and deterministic. Swap in real exports to use real data; the LinkedIn fixture mirrors a "Save to JSON"-style export (`profileUrl`, `fullName`, `headline`, `skills[]`, `experience[]`, `education[]`).

## Deliberately descoped (under time pressure)
- **Live API auth / rate-limits** — GitHub uses a cached JSON fixture; a guarded `--github-live` exists but is off by default.
- **Heavy PDF/DOCX layout** — plain prose only; simple-text PDF via optional `pypdf`.
- **Fuzzy / ML entity resolution** — deterministic exact match only (avoids wrong-but-confident merges).
- **Full UI** — CLI only (the brief marks this lower priority).

## Export the design to PDF
```bash
pandoc design/DESIGN.md -o "<MyFullName>_<MyEmail>_Eightfold.pdf" \
  -V geometry:margin=0.6in -V fontsize=10pt          # needs a LaTeX engine
# no LaTeX?  ->  npx md-to-pdf design/DESIGN.md
```
