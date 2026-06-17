---
type: Plan
title: Agentic Engineering Projects Plan — Framing Note (June 2026, D26)
description: Documentation for this phase or specification.
---

# Agentic Engineering Projects Plan — Framing Note (June 2026, D26)

*This note applies to the full `Agentic_Engineering_Projects_and_Learning_Plan.md` document. Read it before that document.*

---

## What changed and what didn't (per DECISIONS D26)

The **technical content of this document is unchanged and remains the authoritative reference** for how to build each project: the codebase orientation, the component reference, Projects A–H, the Rust CLI parallel track, the tech stack, the model reference, the red flags list. None of that changes because the goal changed.

**What no longer applies:**

- **Part 4 ("The Company Brain — Assembly & The Three Product Ideas")** — the assembly section describes wiring the projects into a product and shipping it to SMB clients. That product build is no longer the goal. The technical architecture described there is still worth understanding as a depth demonstration; it's just not an active build plan. Skip Part 4 when working from this document for task generation.

- **Part 5 ("The Self-Improving System")** — this was a Phase 3+ capstone for a product platform. Still interesting as an intellectual exercise and a long-term capability; no longer a planned deliverable. Skip Part 5 for task generation.

- **The "Company Brain role" column in tables and the "Company Brain component" framing** throughout Part 3 — wherever a project is described as "the Company Brain's retrieval half" or "the 'keeps it current' engine," read that as "a strong portfolio demonstration of this pattern" rather than a product milestone. The framing is still useful for understanding *why* the projects are designed as they are; it just doesn't imply a product shipping deadline.

- **The Rust appliance shell parallel track** — no longer the "SMB delivery vehicle." It's personal ops CLI tooling that keeps the Rust skill warm. The scope description in that section (supervise the local brain, surface cost/quality numbers, act as a client appliance) still describes an interesting thing to build; the business rationale has changed. Build it for yourself, to the extent it's useful, not as a product.

**What is unchanged and fully applies:**

- The codebase orientation (Phase 0, Part 2) — non-negotiable before any project
- Projects A–H, their sequencing, their build notes, their test requirements
- The "rules" (ship each project, tests non-negotiable, thinnest thing that teaches the pattern)
- The tech stack and all infrastructure decisions
- The local model reference and Project H eval methodology
- Project G's Honcho architecture reference (D25) — still the right way to build G
- Every red flag in the red flags list
- The portfolio one-liner table — those one-liners are contracting portfolio descriptions now, not product team credentials

**The short version:** use this document exactly as written for Parts 1–3 and Part 6. Treat Parts 4–5 as archived reference material you can read for depth but don't need to execute.
