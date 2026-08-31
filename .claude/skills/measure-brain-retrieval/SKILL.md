---
name: measure-brain-retrieval
description: Measure whether a change to Brain retrieval actually helped — running syn eval, reading its metrics honestly, and comparing two runs without repeating the corpus-mismatch error that has already voided three blocks' conclusions. Use BEFORE running syn eval, before quoting or comparing any recall/MRR/groundedness number, before promoting a baseline, and whenever tuning ranking constants, chunking, embeddings or the golden set.
allowed-tools: Bash(uv:*) Bash(cd:*) Bash(python3:*) Bash(ls:*) Bash(grep:*) Bash(psql:*)
---

# Measuring Brain retrieval

The eval harness is easy to run and easy to draw a false conclusion from. **A run file records its
metrics but not, historically, the corpus it was measured against** — so two numbers from two dates
are not comparable by default. `OR.0.C` compared a pre-prune run to a post-prune run and attributed
the whole delta to the wrong variable; the same trap voided `OR.0.A`'s ranking sweep, measured on a
corpus that no longer exists.

Start at the observatory index — it is the authority, this skill is the entry point:
[`planning/retrieval-eval-runs/index.md`](../../planning/retrieval-eval-runs/index.md).

## Run it

Everything here runs from this repo's root (the golden set and the run directory are
repo-relative). From the HQ root, `cd core/synapse` first.

```bash
uv run syn eval                    # score the golden set, write a dated run file,
                                   # compare against the promoted pin (baseline.json)
uv run syn eval --no-write         # same scoring, zero files written — the throwaway form
uv run syn eval --no-baseline      # skip the comparison entirely; always exits 0
uv run syn eval --report out.md    # render the scrubbed, publishable Markdown report
```

**`syn eval` always writes a tracked run file unless you pass `--no-write`.** Use `--no-write` for
every exploratory run; a directory full of experiment files makes the time series unreadable.

Exit code: non-zero **iff** some metric's paired verdict is `regressed-significant`. `--strict`
restores the old tripwire (non-zero on *any* metric decrease) — that is a different, much noisier
question, so only pass it deliberately.

## The five rules that exist because breaking them cost real runs

1. **Never compare two runs without checking the corpus each was measured against.** Run files are
   not self-describing about their corpus unless they carry the `corpus` stamp.
2. **Re-fingerprint immediately before and after every run** — `brain_documents` count,
   `brain_edges` count, `max(indexed_at)`. If any moves between a control and its arm, **that pair
   is void**; re-run, do not reason around it.
3. **Never modify an existing run file**, and never re-scope a golden-set case to flatter a metric.
   Factual path corrections are allowed and belong in the case's `notes:` (precedent:
   `archive-01-rates`).
4. **Use `--no-write` for throwaway experiments.**
5. **Never run a diagnostic as `python -c`.** `load_dotenv()` resolves `core/.env`
   (`DATABASE_NAME=orchestration_dev`) only when running a *script file*; with `-c` it falls back to
   `postgres`, which has **0 brain rows**. You get a confident, empty, wrong answer. Always put the
   diagnostic in a `.py` file and run that.

## Reading the metrics

Six gated metrics: recall@5, recall@10, MRR, abstain-correctness, `groundedness`,
`groundedness_on_hits`. No LLM sits in the scoring path.

- **Read the groundedness pair together.** Headline `groundedness` scores a recall miss as `0.0`,
  so it partly re-measures recall. `groundedness_on_hits` restricts the same lexical-support mean to
  cases that actually matched an `expect_docs` document. **Groundedness is a band, not a target** —
  its structural biases and healthy range are in `docs/brain-rag.md` §
  "Reading `groundedness`", decomposed case-by-case in
  `planning/artifacts/groundedness-baseline-analysis.md`.
- Every run stamps `aggregate_stats`: a 95% interval (Wilson for proportions, seeded bootstrap
  otherwise) plus `n` per metric. **Quote the interval, not the point estimate** — most single-run
  deltas on this golden set are inside it.
- The comparison prints a signed per-metric delta **plus a paired per-case verdict** (exact sign
  test for proportions, paired bootstrap for continuous). The verdict is the answer; the delta's
  sign alone is not.
- A live-corpus divergence from the pin's corpus **warns, never gates**. Read the warning — it is
  usually rule 1 firing.

## The baseline pin

`planning/retrieval-eval-runs/baseline.json` is the pin — a pointer file, not prose. `syn eval`
reads it on every bare invocation and names which run it compared against.

```bash
uv run syn eval promote planning/retrieval-eval-runs/<run>.json --reason "why this is the new floor"
```

Guarded: `--reason` must be non-empty; the run must carry `corpus`, `ranking_constants` **and**
`aggregate_stats` (which mechanically excludes all 15 pre-statistical-honesty runs); and `--force`
is required to promote over an existing pin that is significantly better.

**Today's pin is grandfathered and is not a valid same-day control.** It points at
`2026-08-02T10-15-24Z.json` (recall@10 = 1.0000), measured at 13054 chunks / 1094 files — a corpus
that no longer exists after the 2026-08-07 zombie-path prune took it to 11249. It was hand-migrated
in with `corpus: null` so the pin would have some machine-readable provenance. Treat it as an
aspirational target, never as an A/B control.

## Where the data lives

| Path (repo-relative) | What it holds |
|---|---|
| `planning/retrieval-eval-runs/index.md` | **Start here** — the observatory |
| `planning/retrieval-eval-runs/*.json` | Dated runs — the metric time series |
| `planning/retrieval-eval-runs/baseline.json` | The promoted pin |
| `planning/retrieval-eval-runs/_report-*.md` | Scrubbed, publishable reports (leading `_` keeps them out of the corpus gate, deliberately) |
| `planning/retrieval-eval-runs/snapshots/` | Corpus + ranking constants + `brain.toml` + gate status at a point in time |
| `planning/retrieval-eval-runs/query-log/` | Exported `retrieval_queries` rows — **real** traffic, and the only copy that survives a DB reset |
| `planning/artifacts/rag-diagnosis-*.md` | The written analyses, indexed from the observatory |

## Growing the golden set from real traffic

```bash
uv run syn queries --since 7d --json      # what was actually asked, + read-time abstain_rate
uv run syn queries --abstained            # the rows retrieval gave up on
uv run syn queries mine                   # propose golden-set candidates as YAML on stdout
```

`syn queries mine` **never writes** `planning/retrieval-golden-set.yaml`. The loop is mine → edit →
paste → schema test → eval → promote, by hand. Its `confidently-wrong-suspect` label is a heuristic,
never a detector — verify each case before adopting it.

## Cron-safe forms

`syn routine eval` is report-only: no baseline comparison, nothing promoted. `syn routine reconcile`
is likewise report-only. Repairing and promoting are judgement-shaped and must not run unattended.

## See also

- `query-brain` — the read path (`syn recall` / `walk` / `pulse`); run `pulse` first if results look
  wrong, because a degraded backend looks like "no results", not like an error.
- `CLAUDE.md` § "Brain RAG measurement — where the data lives" — the source of the five
  rules above.
- `docs/brain-rag.md` — retrieval architecture and the groundedness band.
