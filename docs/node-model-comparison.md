---
type: Reference
title: Node Model Comparison
description: Assessment of best Cloud and Local LLMs for each orchestrator node.
doc_id: node-model-comparison
layer: [engine]
project: orchestrator
status: active
---

# Node Model Comparison

This document assesses the LLM requirements for each node in the Python Orchestration System and recommends the most suitable models across three categories: **Google**, **Anthropic**, and **Local Alternatives**. 

For local alternatives, we split the recommendations into two target hardware profiles:
- **M2 MacBook Pro (32GB RAM)**: Capable of running quantized 30B-70B parameter models.
- **M1 Mac Mini (16GB RAM)**: Limited to 7B-9B parameter models for responsive inference.

*Note: Utility nodes (routers, fetchers, storage, chunking, etc.) that do not use LLMs directly are omitted from this comparison.*

---

## 1. Content Pipeline Workflow

### SummarizerNode
* **Requirement**: High-quality summarization, accurate structured output (JSON).
* **Google**: **Gemini 1.5 Flash** (Fast, cheap, excellent at structured output).
* **Anthropic**: **Claude 3 Haiku** (Very fast and cost-effective for basic summarization).
* **Local (MBP 32GB)**: **Qwen2.5 32B-Instruct** (Excellent instruction following and JSON generation).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct** (Fast and capable for structured extraction).

### BlogWriterNode
* **Requirement**: Long-form prose generation, tone/voice matching.
* **Google**: **Gemini 1.5 Pro** (Stronger creative writing and tone adherence). *Tradeoff: Gemini 1.5 Flash is cheaper but might sound more generic.*
* **Anthropic**: **Claude 3.5 Sonnet** (Best-in-class prose and voice matching).
* **Local (MBP 32GB)**: **Command-R 35B** (Tuned for RAG and professional prose).
* **Local (Mini 16GB)**: **Mistral-Nemo-12B** (Quantized to fit, punches above its weight in creative writing).

### SelfCriticNode
* **Requirement**: Analytical reasoning, critique against specific criteria.
* **Google**: **Gemini 1.5 Pro** (Strong reasoning capabilities).
* **Anthropic**: **Claude 3.5 Sonnet** (Excellent at nuanced critique). *Tradeoff: Claude 3 Haiku could be used for simple rule checks to save cost.*
* **Local (MBP 32GB)**: **Llama-3-70B-Instruct** (Quantized 4-bit; best open-weight reasoning).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct** (Best reasoning in the small weight class).

### ReviseNode
* **Requirement**: Precise instruction following and editing without rewriting from scratch.
* **Google**: **Gemini 1.5 Pro** (Good at localized edits).
* **Anthropic**: **Claude 3.5 Sonnet** (Follows revision instructions perfectly).
* **Local (MBP 32GB)**: **Qwen2.5 32B-Instruct** (Strong at precise edits).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct**.

### TranslatePtBrNode
* **Requirement**: Translation accuracy and idiomatic Portuguese.
* **Google**: **Gemini 1.5 Flash** (Google models are exceptionally good at translation natively).
* **Anthropic**: **Claude 3.5 Sonnet** (Strong multilingual capabilities).
* **Local (MBP 32GB)**: **Qwen2.5 32B-Instruct** or **Llama-3-70B-Instruct** (Both have solid multilingual training).
* **Local (Mini 16GB)**: **Gemma-2-9B-It** (Good multilingual performance for its size).

---

## 2. Proposal Generator & Research Agent Workflows

### CompanyResearchNode (ToolUseNode)
* **Requirement**: Function calling/tool use (web search), reasoning to determine when to stop searching.
* **Google**: **Gemini 1.5 Pro** (Excellent tool use).
* **Anthropic**: **Claude 3.5 Sonnet** (Industry leader in agentic tool loops).
* **Local (MBP 32GB)**: **Command-R 35B** (Explicitly trained for tool use and web search).
* **Local (Mini 16GB)**: **Hermes-3-Llama-3.1-8B** (Fine-tuned specifically for tool calling).

### OpportunityIdentifierNode
* **Requirement**: Analytical reasoning, synthesizing research into structured opportunities.
* **Google**: **Gemini 1.5 Pro**. *Tradeoff: Gemini 1.5 Flash if cost is a concern, but might miss deeper insights.*
* **Anthropic**: **Claude 3.5 Sonnet**.
* **Local (MBP 32GB)**: **Llama-3-70B-Instruct** (Deep reasoning required here).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct**.

### ProposalWriterNode
* **Requirement**: Professional business writing, strict adherence to formatting.
* **Google**: **Gemini 1.5 Pro**.
* **Anthropic**: **Claude 3.5 Sonnet**.
* **Local (MBP 32GB)**: **Command-R 35B** or **Qwen2.5 32B-Instruct**.
* **Local (Mini 16GB)**: **Mistral-Nemo-12B**.

### ProposalReviewNode & ProposalReviseNode
* **Requirement**: Strict adherence to a rubric, structured evaluation (Pass/Revise).
* **Google**: **Gemini 1.5 Pro** (Needs to avoid hallucinating passes).
* **Anthropic**: **Claude 3.5 Sonnet**.
* **Local (MBP 32GB)**: **Llama-3-70B-Instruct** (Needed for reliable LLM-as-a-judge).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct** (May struggle with complex rubrics; monitor closely).

---

## 3. Document Q&A (RAG) Workflow

### AnswerNode
* **Requirement**: Strict grounding in retrieved context, citation accuracy, and willingness to abstain ("I don't know").
* **Google**: **Gemini 1.5 Pro** (Can handle massive contexts if needed, good at grounding). *Tradeoff: Gemini 1.5 Flash is excellent for RAG if the context is small and straightforward.*
* **Anthropic**: **Claude 3.5 Sonnet** (Best at avoiding hallucinations and citing sources).
* **Local (MBP 32GB)**: **Command-R 35B** (Explicitly trained for RAG and citations).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct** (Prompt heavily to prevent hallucinations).

### UpdateSessionMemoryNode
* **Requirement**: Fast summarization of conversational turns, updating structured JSON.
* **Google**: **Gemini 1.5 Flash** (Perfect for fast background summarization).
* **Anthropic**: **Claude 3 Haiku** (Fast and cheap).
* **Local (MBP 32GB)**: **Llama-3.1-8B-Instruct** (Don't waste 32GB RAM on a background summarization task; use a smaller fast model).
* **Local (Mini 16GB)**: **Llama-3.1-8B-Instruct** or **Qwen2.5-7B**.

---

## 4. Services (Embeddings)

### EmbeddingService
* **Requirement**: Vectorizing text for semantic search.
* **Google**: **text-embedding-004** (Excellent multimodal and text embeddings).
* **Anthropic**: *N/A* (Anthropic does not offer native embedding models. Voyage AI is the recommended partner).
* **Local (MBP 32GB & Mini 16GB)**: **mxbai-embed-large** (1024-dim, excellent performance, runs easily via Ollama on both machines).
