---
type: Index
title: Decisions Registry
description: Registry of architectural decisions and settled choices for the python-orchestration-system, one atomic file per decision.
---

# Decisions — Settled Choices & Their Reasoning

*Append-only registry. Records non-obvious decisions so they don't get relitigated. Newest at the bottom.*
*This is the "why" that outlives `status.md`'s deviation log. If a choice is reversed, add a new decision superseding it — don't edit the old one.*

Each decision lives in its own file, `D{N}-<kebab-title>.md`, in the **Decided · Why · Rejected** form.

| # | Decision | File |
|---|---|---|
| D1 | Expertise first; business/job follows | [D1-expertise-first.md](D1-expertise-first.md) |
| D2 | Sequence, not calendar | [D2-sequence-not-calendar.md](D2-sequence-not-calendar.md) |
| D3 | Drop the Socratic Tutor as the organizing goal | [D3-drop-socratic-tutor.md](D3-drop-socratic-tutor.md) |
| D4 | Project G (agent memory) is the centerpiece, retained at full weight | [D4-project-g-centerpiece.md](D4-project-g-centerpiece.md) |
| D5 | Testing scope: Option A (core only) | [D5-testing-scope-option-a.md](D5-testing-scope-option-a.md) |
| D6 | Python for orchestration; Rust only where it genuinely wins | [D6-python-for-orchestration.md](D6-python-for-orchestration.md) |
| D7 | Rust's home: the CLI now, an inference runtime only later | [D7-rust-home-cli.md](D7-rust-home-cli.md) |
| D8 | Project H (model eval) is offline evaluation, NOT a runtime router | [D8-project-h-offline-eval.md](D8-project-h-offline-eval.md) |
| D9 | Existing production work is foregrounded as case studies | [D9-existing-work-as-case-studies.md](D9-existing-work-as-case-studies.md) |
| D10 | Public narrative: subject-is-always-you; never name the company | [D10-public-narrative.md](D10-public-narrative.md) |
| D11 | Documentation: separate orientation from state; minimum-context by default | [D11-docs-orientation-vs-state.md](D11-docs-orientation-vs-state.md) |
| D12 | Repo strategy: one Python monorepo; separate repos only for different languages | [D12-repo-strategy-monorepo.md](D12-repo-strategy-monorepo.md) |
| D13 | Per-repo agent context and daily log; just-in-time task specs | [D13-per-repo-context-jit-specs.md](D13-per-repo-context-jit-specs.md) |
| D14 | The destination has a named product: the Company Brain *(superseded by D26)* | [D14-company-brain-product.md](D14-company-brain-product.md) |
| D15 | Buyer wedge: fast-growing SMBs at the 30–80 inflection, privacy-first *(superseded by D26)* | [D15-buyer-wedge-smb.md](D15-buyer-wedge-smb.md) |
| D16 | Architecture: one deployment-agnostic Python brain, two shells *(superseded by D26)* | [D16-one-brain-two-shells.md](D16-one-brain-two-shells.md) |
| D17 | Rust earns its place as the appliance shell *(scope revised by D26)* | [D17-rust-appliance-shell.md](D17-rust-appliance-shell.md) |
| D18 | No deployment logic in the brain | [D18-no-deployment-logic-in-brain.md](D18-no-deployment-logic-in-brain.md) |
| D19 | The privacy wedge is real today; "local-by-default, frontier-for-the-few" | [D19-privacy-wedge-local-by-default.md](D19-privacy-wedge-local-by-default.md) |
| D20 | Self-improvement boundary: gates are never self-approved | [D20-self-improvement-boundary.md](D20-self-improvement-boundary.md) |
| D21 | Project A is a personal knowledge feed first, blog engine second | [D21-project-a-knowledge-feed.md](D21-project-a-knowledge-feed.md) |
| D22 | Project A MVP boundary: ingestion + store + dumb display now | [D22-project-a-mvp-boundary.md](D22-project-a-mvp-boundary.md) |
| D23 | Mac Mini two-face architecture: Caddy+Cloudflare public, Tailscale private | [D23-mac-mini-two-face.md](D23-mac-mini-two-face.md) |
| D24 | Firecrawl role: trafilatura-first, Firecrawl-fallback, CrawlSiteNode | [D24-firecrawl-role.md](D24-firecrawl-role.md) |
| D25 | Honcho as Project G reference architecture; build your own G for production | [D25-honcho-reference.md](D25-honcho-reference.md) |
| D26 | Goal revised: solo contracting practice, not a studio or product company | [D26-goal-solo-contracting.md](D26-goal-solo-contracting.md) |
| D27 | Adopt OKF Phase 2 conventions (lowercase names, concept-folder planning, index.md); retire scaffold-project | [D27-adopt-okf-phase-2-conventions.md](D27-adopt-okf-phase-2-conventions.md) |
| D28 | Persist node-level execution state incrementally (injected callback; brain stays agnostic) | [D28-node-level-execution-state.md](D28-node-level-execution-state.md) |
| D29 | Execute OKF Phase 2; adopt base-template's richer-check + token-telemetry engines; harness.json | [D29-execute-okf-and-adopt-richer-check-engines.md](D29-execute-okf-and-adopt-richer-check-engines.md) |
| D30 | Orchestrator owns the versioned data contract; capture per-node input + serializable output | [D30-data-contract-ownership.md](D30-data-contract-ownership.md) |
| D31 | Exclude ARRAY and Vector models from SQLite test fixtures; test against real PostgreSQL only | [D31-sqlite-array-exclusion.md](D31-sqlite-array-exclusion.md) |
| D32 | Lazy imports inside main() for standalone CLI scripts — keeps --dry-run and --help offline-safe | [D32-lazy-import-cli-scripts.md](D32-lazy-import-cli-scripts.md) |

---

**How to read this set:**
- **D1–D13** — foundational sequencing and architecture decisions.
- **D14–D25** — Company Brain product architecture (retained as technical reference; superseded as primary goal by D26).
- **D26** — goal revised to a solo contracting practice.

*To add a decision: create the next `D{N}-<kebab>.md` with `type: Decision` frontmatter and the what / why / rejected body, then append a row above. To reverse one: add a new decision superseding it by number; leave the original intact.*
