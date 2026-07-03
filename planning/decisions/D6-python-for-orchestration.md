---
type: Decision
title: D6 — Python for orchestration; Rust only where it genuinely wins
description: The orchestration framework stays Python (I/O-bound); Rust is reserved for CPU/latency/memory-bound work.
doc_id: D6-python-for-orchestration
layer: [engine]
project: orchestrator
status: active
keywords: [Python orchestration, Rust seam, I/O-bound, language choice, architecture]
related: [D7-rust-home-cli, D36-bastion-engine-brain-role]
---

# D6 — Python for orchestration; Rust only where it genuinely wins

**Decided:** The orchestration framework stays Python (I/O-bound — model/DB/network latency dominates). Rust is reserved for genuinely CPU/latency/memory-bound work.
**Why:** Rewriting orchestration in Rust is a *learning* win, not an *architecture* win; microseconds saved are meaningless behind a 2-second model call.
**Rejected:** Porting the engine to Rust for performance — already done once as learning; not worth maintaining as the production path.

> **Narrowed by brain D42 (2026-07-02).** This decision's premise — a Python-orchestrator-only stack where a Rust port buys only microseconds behind a model call — is now stale: a whole Rust infrastructure exists (bastion, bella, mev, rag-engine-rs, claude-sdk-rs), so a Rust Engine (`engine-rs`) is an *architecture* fit, not the learning-only exercise rejected here. D42 reopens the Rust-Engine question and builds `engine-rs` as a parallel pilot. Python stays the prototyping tier + Brain half until data-contract parity. See brain `docs/decisions/D42-rust-engine-parallel-pilot.md` and D41.
