---
type: Reference
title: Orchestrator ↔ bastion Knowledge Workspace Contract
description: The versioned, canonical contract for the shared "knowledge workspace" convention — workspace names, resolution precedence, and the OKF corpus rules — consumed identically by the Python Brain readers (OR.C) and bastion's graph reader (BA.6.B).
doc_id: workspace-contract
layer: [brain, console]
project: orchestrator
status: active
keywords: [workspace, knowledge directory, data contract, brain.toml, OKF, multi-workspace, bastion]
related: [data-contract, brain-rag, scripts]
---

# Knowledge Workspace Contract

**Contract Version: 1.0.0**

This is the **single source of truth** for the shared "knowledge workspace" convention — what a
workspace *is*, how it is *named*, how a name *resolves* to a corpus root, and what a conforming
root must *contain*. The orchestrator **owns** this document. Consumers (e.g.
[`bastion`](../../bastion)) reference and *pin* it; they never fork it. When any shape here
changes, bump the version and add a changelog row (see [Versioning](#6-versioning)).

> This contract predates the orchestrator's own multi-workspace implementation (`OR.C`, not yet
> built) — it was pinned first (2026-07-15, brain decision **D47**) precisely so the Python half
> cannot invent a naming scheme that drifts from bastion's already-shipped half (`BA.6.B`).
> Governing block specs: orchestrator `planning/master-plan.md` `### OR.C`; bastion
> `planning/master-plan.md` `### BA.6.B`.

---

## 1. What a workspace is

A **knowledge workspace** is a *named root directory* holding an OKF markdown corpus (§4). It is
the unit of Brain addressing: per-repo corpora, per-client corpora, and the future memory/entity
scope are all keyed by workspace. Two independent readers consume the same convention:

- the **Python RAG readers** (indexer `scripts/index_brain.py` + retriever
  `RetrieveChunksNode`) — the orchestrator half, generalized by `OR.C`;
- the **bastion graph reader** (`bastion brain` / `bastion code`) — the Rust half, shipped as
  `BA.6.B`.

A workspace is identified by its **name**; the name maps to a **root path** via each consumer's
own registry (§3). The pair `(name, root)` plus the corpus rules in §4 is the whole convention.

---

## 2. Workspace names

**Format:** kebab-case — lowercase ASCII letters, digits, and hyphens (the same shape as OKF
`doc_id` slugs). Names are opaque keys; they carry no path information.

**Canonical name source — `brain.toml` `[[repos]].slug`.** For every corpus that is part of the
company-brain family (the brain root and each manifest sub-repo), the workspace name **is** the
`slug` field of that repo's `[[repos]]` entry in the brain root's `brain.toml` (e.g.
`orchestrator`, `bastion`, `mev`, `brain`). There is deliberately **no second namespace**: the
manifest slug is already the identity key throughout the stack.

**The workspace name is the same string as:**

| Surface | Where |
|---|---|
| the `BrainDocument.project` column value stamped on every sub-repo chunk | `scripts/index_brain.py` `_sub_repo_files()` → `project_override` (OR.O) |
| the retrieval-time scoping key `filters={"project": "<name>"}` on the `"brain"` corpus | `RetrieveChunksNode` `filter_fields` / `_apply_metadata_filters` |
| the `--workspace <NAME>` registry key on `bastion brain` / `bastion code` | bastion `src/config.rs` `[workspaces]` table |
| the future `workspace_id` memory/entity addressing key (Block S) | orchestrator `planning/master-plan.md` `### OR.S` |

**Non-manifest workspaces** (e.g. a per-client knowledge dir that is not a `[[repos]]` entry) use
the same kebab-case format and **must not collide** with any `brain.toml` slug. A manifest slug
always denotes the manifest repo's corpus; registries may not rebind it to a different root.

---

## 3. Resolution — name → root

Each consumer resolves a workspace name to a root path through its **own registry**; the contract
pins the *semantics*, not a shared file (**name-parity**, decision D47). The registries are:

| Consumer | Registry | Status |
|---|---|---|
| bastion | `[workspaces]` TOML table (name → path) + `default_workspace` in `~/.config/bastion/config.toml` (or `$XDG_CONFIG_HOME/bastion/config.toml`) | shipped (`BA.6.B`) |
| Python readers | config/CLI surface to be defined by `OR.C` | future — must implement these semantics |

**Resolution precedence** (highest → lowest), as shipped in bastion
`config::resolve_workspace_root` and binding on every future resolver:

1. **Explicit root** — a directly supplied path (bastion `--root`) always wins; no registry lookup.
2. **Named workspace** — an explicitly supplied name (bastion `--workspace`, alias
   `--knowledge-dir`), looked up in the registry.
3. **Default workspace** — the registry's configured default name (bastion `default_workspace`),
   looked up in the registry.
4. **Built-in default** — the current working directory (`.`).

**Resolution behaviors (binding):**

- Resolution is **pure**: no I/O, no canonicalization, no existence check. The registry's stored
  path (or the explicit root) is returned verbatim; whether it exists is the *reader's* problem,
  surfaced when the corpus is opened (§4).
- A name that is **not in the registry** (step 2 or 3) is a **fatal, typed error** naming the
  unknown workspace — never a silent fallback to another root.
- A name supplied when **no registry exists at all** is a **distinct** fatal error ("no workspace
  registry"), so the user learns to create the registry rather than to fix a name.
- A registry **file that is absent or unreadable** degrades to an *empty registry* (no error at
  load time); a registry file that is **present but malformed** is a load-time error.

---

## 4. Workspace root expectations (OKF corpus rules)

The **shared minimum** every conforming reader honors over a workspace root:

- **Files:** `.md` and `.mdx` only. Discovery is a recursive walk of the root.
- **Skips:** any entry (file or directory) whose name starts with `.` (hidden), and any directory
  named `target`.
- **Frontmatter is optional.** Files without valid OKF YAML frontmatter are still corpus members.
- **Node identity:** the OKF frontmatter `doc_id` when present and non-empty, else the **filename
  stem**. `title` falls back the same way.
- **Edges:** `[[slug]]` / `[[slug|alias]]` wiki-links; the target is the slug portion (a `doc_id`
  or filename stem). Links whose target matches no corpus node are **silently dropped**, never an
  error.
- **Empty corpus** (zero markdown files under the resolved root) is a fatal reader error naming
  the root — the signal for a wrong `--root`/workspace mapping.

**Consumer-specific supersets are allowed** as long as the shared minimum holds. Known today: the
Python indexer additionally skips underscore-prefixed and ephemeral planning dirs plus the
`brain.toml` `[crawl].skip_dirs` list, and enriches chunks with embeddings/FTS — none of which
bastion's structural reader needs. A superset may *narrow* what gets indexed; it must not *widen*
(e.g. indexing non-markdown files as corpus nodes) or change node identity.

---

## 5. Consumers

| Consumer | Half | Status | Conformance surface |
|---|---|---|---|
| `bastion brain` / `bastion code` | Rust graph reader (`BA.6.B`) | **shipped** | `src/config.rs` (`FileConfig.workspaces`, `resolve_workspace_root`), `src/cli.rs` (`--root`, `--workspace`/`--knowledge-dir`), `src/validate/mod.rs` (`find_markdown_files`), `src/brain/okf.rs` (node identity, `[[link]]` edges). Consumer view: `bastion/docs/workspace-contract.md` |
| Python indexer/retriever | orchestrator half (`OR.C`) | **future** | must implement §2–§4 when built: workspace-name = manifest slug, precedence semantics of §3, corpus rules of §4. Today's single-workspace behavior (`index_brain.py` hardcoded brain root + `project_override` stamping) is the degenerate one-workspace case and already name-conformant |
| `engine-rs` | workflow-execution Engine | **out of scope by design** | never resolves workspaces (its governing principle: "Brain/RAG stays Python", `engine-rs/planning/context.md`). If a workflow ever needs workspace context, the **already-resolved** `workspace_id` (and root, if required) arrives as event/metadata data through the D20 data contract — resolution never happens inside the Engine |

---

## 6. Versioning

Semver on this document:

- **Patch** — wording/clarification, no rule change.
- **Minor** — additive, backward-compatible (a new optional expectation, a new consumer row, a
  documented extension point).
- **Major** — a breaking change (change the name format or canonical name source, reorder or
  change resolution precedence, tighten/loosen a §4 corpus rule incompatibly).

When you change any rule here: bump the version in the header, add a row below, and **re-pin the
consumer** (`bastion/docs/workspace-contract.md`). The brain repo's `CLAUDE.md` Update Protocol
table carries the sync step.

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-07-15 | Initial contract: workspace = named OKF root; names = `brain.toml` `[[repos]].slug` (kebab-case, no second namespace); name-parity registries with pinned resolution precedence (explicit root > named > default > cwd, pure, typed errors); shared-minimum OKF corpus rules; engine-rs receives resolved `workspace_id` as event data only. Decision D47. |
