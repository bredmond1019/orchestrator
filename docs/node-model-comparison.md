---
type: Reference
title: Node Model Comparison
description: Assessment of best Cloud and Local LLMs for each orchestrator node, including storage requirements and hardware capabilities.
doc_id: node-model-comparison
layer: [engine]
project: orchestrator
status: active
related: [sdlc-workflow-nodes-design]
---

# Node Model Comparison

This document assesses the LLM requirements for each node in the Python Orchestration System and recommends the most suitable models across three categories: **Google**, **Anthropic**, and **Local Alternatives**. 

*Note: Utility nodes (routers, fetchers, storage, chunking, etc.) that do not use LLMs directly are omitted from this comparison.*

---

## 1. Local Hardware Limits & The "Best Two" Models

Running local models depends heavily on Unified Memory (RAM). A model's size in GB (when using 4-bit quantization, the standard for Ollama/LM Studio) roughly dictates how much RAM it consumes. 

### M2 MacBook Pro (32GB RAM)
**Limit:** Can comfortably run models up to ~35B parameters (which take ~20-22 GB of RAM), leaving enough overhead for macOS and context windows. *Note: 70B models (like Llama-3-70B) take ~40 GB in 4-bit and will aggressively swap to disk on a 32GB machine, making them painfully slow.*

**The Best Two Models (The "Go-To" Stack):**
1. **Qwen2.5-32B-Instruct (~20 GB on disk):** Your heavy lifter. Excellent at reasoning, tool use, coding, and LLM-as-a-judge tasks.
2. **Llama-3.1-8B-Instruct (~4.7 GB on disk):** Your fast utility model. Perfect for quick summarization, structuring JSON, and background tasks.

### M1 Mac Mini (16GB RAM)
**Limit:** Can comfortably run models up to ~12B parameters (which take ~7-8 GB of RAM).

**The Best Two Models (The "Go-To" Stack):**
1. **Llama-3.1-8B-Instruct (~4.7 GB on disk):** The absolute best all-rounder in the small weight class.
2. **Mistral-Nemo-12B (~7.1 GB on disk):** A slightly heavier model that excels at long-context generation and creative prose (good for writing).

*(Plus **mxbai-embed-large** which is ~670 MB for both machines to handle embeddings).*

---

## 2. Workflow Local Feasibility

Since you can assign models on a per-node basis, you can mix and match. But if you wanted to run entirely local, here is how the hardware stacks up:

### ✅ Workflows Fine for Mac Mini (16GB)
* **Document Ingest:** Doesn't require heavy reasoning, just embeddings (`mxbai`).
* **Content Pipeline (Digest Only):** `Llama-3.1-8B` is perfectly capable of extracting bullet points, generating JSON, and summarizing articles/videos.
* **Update Session Memory:** Background summarization of chat turns is easily handled by an 8B model.

### ✅ Workflows Fine for MacBook Pro (32GB)
* **Content Pipeline (Full Blog Branch):** `Qwen2.5-32B` can handle the `SelfCriticNode` and `BlogWriterNode` with excellent quality.
* **Document Q&A (RAG):** `Qwen2.5-32B` has strong context adherence and grounding abilities for the `AnswerNode`.
* **Research Agent:** `Qwen2.5-32B` is highly capable of driving a tool-calling loop (web search).
* **Proposal Generator:** `Qwen2.5-32B` is smart enough to act as the `OpportunityIdentifier` and the `ProposalReviewNode`.

### ❌ ABSOLUTELY Cloud-Only (Do Not Use Local)
1. **Dream-Time Memory Consolidation (Project G):** As explicitly stated in your standing rules (*D35 named frontier-only exception*), this must stay on Claude. Weak local models will hallucinate "durable facts" with high confidence, which will silently corrupt your entire entity memory store downstream.
2. **High-Stakes LLM-as-a-Judge (`ProposalReviewNode` for real clients):** While Qwen 32B is okay for practice, if you are gating an actual client proposal, a local model might "hallucinate a pass" on your rubric. **Claude 3.5 Sonnet** or **Gemini 1.5 Pro** should be used when the output represents your brand.
3. **SDLC Code Generation and Review (`ImplementTaskNode`, `ConsolidatedReviewNode`):** Writing production-grade code autonomously and judging its correctness is an extremely high stakes task. While local 32B models can do basic bug fixes, full-scale feature work and authoritative reviews should remain on **Claude 3.5 Sonnet** (or Opus for escalation).

---

## 3. Node-by-Node Model Breakdown

### Content Pipeline Workflow
| Node | Requirement | Google | Anthropic | Local (32GB Mac) | Local (16GB Mac) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SummarizerNode** | Fast JSON structured output | Gemini 1.5 Flash | Claude 3 Haiku | Llama-3.1-8B (~4.7 GB) | Llama-3.1-8B (~4.7 GB) |
| **BlogWriterNode** | Long-form prose, voice match | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Mistral-Nemo-12B (~7.1 GB) |
| **SelfCriticNode** | Analytical reasoning, critique | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Llama-3.1-8B (~4.7 GB) |
| **ReviseNode** | Precise instruction following | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Llama-3.1-8B (~4.7 GB) |
| **TranslatePtBrNode** | Translation, idiomatic prose | Gemini 1.5 Flash | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Gemma-2-9B-It (~5.4 GB) |

### Proposal Generator & Research Agent
| Node | Requirement | Google | Anthropic | Local (32GB Mac) | Local (16GB Mac) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CompanyResearch** | Web search tool use / loops | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Hermes-3-Llama-8B (~4.7 GB) |
| **OpportunityIdentifier**| Synthesizing research | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Llama-3.1-8B (~4.7 GB) |
| **ProposalWriter** | Business writing, formatting | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Mistral-Nemo-12B (~7.1 GB) |
| **ProposalReview** | Strict rubric evaluation | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | *Cloud Recommended* |

### Document Q&A (RAG)
| Node | Requirement | Google | Anthropic | Local (32GB Mac) | Local (16GB Mac) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AnswerNode** | Grounding, citation, abstain | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Llama-3.1-8B (Monitor closely) |
| **UpdateSessionMemory**| Fast chat summarization | Gemini 1.5 Flash | Claude 3 Haiku | Llama-3.1-8B (~4.7 GB) | Llama-3.1-8B (~4.7 GB) |

### SDLC Workflows (sdlc-flow & sdlc-run)
| Node | Requirement | Google | Anthropic | Local (32GB Mac) | Local (16GB Mac) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GenerateTasksNode** | Planning, architectural layout | Gemini 1.5 Pro | Claude 3 Opus | Qwen2.5-32B (~20 GB) | *Cloud Recommended* |
| **SetupWorktreeNode**<br>**EnumerateTasksNode**<br>**TestTaskNode** | Deterministic operations, basic JSON parsing | Gemini 1.5 Flash | Claude 3 Haiku | Llama-3.1-8B (~4.7 GB) | Llama-3.1-8B (~4.7 GB) |
| **ImplementTaskNode**<br>**PatchDocsNode** | Autonomous coding, surgical editing | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Qwen2.5-7B-Coder (~4.2 GB) |
| **ConsolidatedReviewNode**<br>**TriageTaskNode** | LLM-as-a-judge, complex code review | Gemini 1.5 Pro | Claude 3.5 Sonnet / Opus | Qwen2.5-32B (~20 GB) | *Cloud Recommended* |
| **WrapUpNode** | Log writing, summary prose | Gemini 1.5 Pro | Claude 3.5 Sonnet | Qwen2.5-32B (~20 GB) | Llama-3.1-8B (~4.7 GB) |

### Shared Services
| Service | Requirement | Google | Anthropic | Local (All Macs) |
| :--- | :--- | :--- | :--- | :--- |
| **EmbeddingService** | Semantic vectorization | text-embedding-004 | *Voyage AI* | mxbai-embed-large (~670 MB) |
