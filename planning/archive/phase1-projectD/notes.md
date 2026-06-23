---
type: ProjectContext
title: Project D — Document Q&A + RAG Notes
description: Scope notes and integration requirements for Project D, including brain RAG integration.
---

# Project D — Document Q&A + RAG Notes

## Brain RAG integration (from brain-rag workstream)

RetrieveChunksNode must accept a `corpus` parameter:

    def retrieve_chunks(
        query: str,
        corpus: Literal["content", "brain"] = "content",
        k: int = 5,
        threshold: float = 0.0,
    ) -> list[ContentChunk]

When corpus="brain": query `brain_documents` table via cosine similarity on `embedding`.
When corpus="content": query `learning_artifacts` table (current behavior).

The `BrainDocument` model is in `app/database/brain_document.py` (ships with the brain-rag workstream).
