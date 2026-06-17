---
type: Decision
title: D5 — Testing scope: Option A (core only)
description: Test the core engine, infrastructure, and services; fix four documented bugs; do not test customer-care.
---

# D5 — Testing scope: Option A (core only)

**Decided:** Test the core engine, infrastructure, and services; fix four documented production bugs; do **not** test the reference-only customer-care workflow. Then every new workflow ships with its own tests.
**Why:** Customer-care is disposable reference code Brandon won't extend; testing it spends effort on throwaway. The same testing patterns are learned by testing code that's kept.
**Rejected:** Option B (full sweep including customer-care) — more thorough but wastes time on code that won't ship.
