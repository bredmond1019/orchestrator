---
type: Decision
title: D6 — Python for orchestration; Rust only where it genuinely wins
description: The orchestration framework stays Python (I/O-bound); Rust is reserved for CPU/latency/memory-bound work.
---

# D6 — Python for orchestration; Rust only where it genuinely wins

**Decided:** The orchestration framework stays Python (I/O-bound — model/DB/network latency dominates). Rust is reserved for genuinely CPU/latency/memory-bound work.
**Why:** Rewriting orchestration in Rust is a *learning* win, not an *architecture* win; microseconds saved are meaningless behind a 2-second model call.
**Rejected:** Porting the engine to Rust for performance — already done once as learning; not worth maintaining as the production path.
