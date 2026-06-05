# Update Docs — Patch docs/*.md to reflect recent source changes.

Surgically updates existing reference docs when source code has changed. Does NOT
regenerate docs from scratch — use `/generate-new-docs` for that.

## Instructions

1. Determine the diff range:
   - If `$ARGUMENTS` is provided, use it as the git ref (e.g. `HEAD~3`, `main..HEAD`, a commit hash).
   - Otherwise default to `HEAD~1` (everything in the last commit) plus any unstaged changes.
   - Run `git diff --stat $ARGUMENTS` to get the list of changed source files.

2. Inventory which docs are affected:
   - Read every file in `docs/`.
   - For each doc, check whether it explicitly references any of the changed source files
     (look for `**Source:**` annotations, code paths, function/class names that appear in
     the changed files).
   - Build a map: `{ doc_path → [changed_source_files_it_covers] }`.
   - If no docs reference any changed file, report "No docs affected by these changes" and stop.

3. For each affected doc + changed source pair:
   a. Read the full current doc.
   b. Read the full changed source file.
   c. Identify only the sections in the doc that describe the changed code (a method that
      was renamed, a field that was added, a behavior that changed).
   d. Rewrite those sections to match the source exactly. Leave all other sections untouched.
   e. If a change is too large for surgical patching (e.g. an entire class was replaced),
      flag it as `NEEDS_REVIEW` and skip — do not attempt a full rewrite.

4. Report when done:
   - List every doc updated, with the specific sections changed.
   - List every doc checked but not needing updates.
   - List any `NEEDS_REVIEW` items with a one-line explanation of why.
   - If the scope of changes suggests a doc needs a wholesale refresh, recommend
     `/generate-new-docs` rather than silently producing a partial update.

## Rules

- **Surgical only.** Never rewrite a doc section that was not affected by the diff.
- **Source is authoritative.** If the doc and the source disagree, the source wins.
- **No invention.** Do not add new sections or cover new APIs not already in the doc;
  that is `/generate-new-docs` territory.
- **Do not touch** `planning/` files, `DEVLOG.md`, `STATUS.md`, or `CLAUDE.md`. Those
  are managed by `/log-work`.
- **Do not touch** `docs/app-architecture-overview.md` automatically — it is a
  hand-curated strategic doc. Flag it as `NEEDS_REVIEW` if architecture-level source
  files changed.

## Context / Files to Read

- `docs/` — all existing reference docs
- Changed source files identified by `git diff --stat`
