---
type: Decision
title: "D7 — Rust's home: the CLI now, an inference runtime only later (with data)"
description: The Rust CLI is the near-term Rust project; a Rust inference runtime is not in scope until a measured limit demands it.
doc_id: D7-rust-home-cli
layer: [engine, console]
project: python-orchestration
status: active
keywords: [Rust CLI, inference runtime, bastion, console, language boundary]
related: [D6-python-for-orchestration, D17-rust-appliance-shell]
---

# D7 — Rust's home: the CLI now, an inference runtime only later (with data)

**Decided:** The Rust CLI is the near-term Rust project (instant startup, single binary, daily use — keeps the skill warm through genuine use). A Rust local-inference *runtime* layer is kept in mind but **not** in scope; it gets built only if a measured limit makes off-the-shelf serving (Ollama et al.) insufficient.
**Why:** The CLI's Rust advantages are unambiguous and immediate; the runtime's are situational and announce themselves with data. The MIDI tool was dropped — it was an excuse to write Rust, not a real need.
**Rejected:** Forcing a Rust project for its own sake (MIDI tool); pre-building the runtime before a bottleneck is measured.
