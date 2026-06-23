"""AssembleContextNode — combine RAG context and session memory for the AnswerNode.

Combines two inputs:
1. **Retrieved chunks** from ``RetrieveChunksNode`` — formatted with their
   section title and a normalized relevance score (porting the
   ``build_rag_prompt`` format from ``chat_server.rs`` in the rag-engine-rs).
2. **Prior conversation turns** from the current ``ChatSession`` (if one
   exists) — formatted as a readable transcript so the ``AnswerNode`` can
   provide coherent multi-turn answers.

The assembled context block and the prior-turn history are stored separately
so ``AnswerNode`` can compose the final user prompt in a structured way.

The ``_load_session`` method is isolated as a patachable seam so tests never
touch a real database.
"""

from contextlib import contextmanager

from core.nodes.base import Node
from core.task import TaskContext
from database.chat_session import ChatSession
from database.repository import GenericRepository
from database.session import db_session


class AssembleContextNode(Node):
    """Assemble the grounded context block and session history for the answer step."""

    # ------------------------------------------------------------------
    # DB seam — patched in tests
    # ------------------------------------------------------------------

    def _load_session(self, session_id) -> ChatSession | None:
        """Load an existing ``ChatSession`` by id, or return None.

        Uses the shared ``db_session`` factory so no deployment-specific
        connection logic lives inside the node (CLAUDE.md rule 7).
        Tests monkeypatch this method to inject a fake session.
        """
        with contextmanager(db_session)() as session:
            return GenericRepository(
                session=session, model=ChatSession
            ).get(str(session_id))

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def process(self, task_context: TaskContext) -> TaskContext:
        """Build the grounded context from retrieved chunks + prior session turns.

        Reads:
          - ``RetrieveChunksNode`` output: list of chunk dicts with
            ``content``, ``section_title``, and ``score``.
          - ``task_context.event.session_id``: used to load prior turns.
          - ``task_context.event.question``: passed through for ``AnswerNode``.

        Writes:
          - ``AssembleContextNode`` result:
            ``{"context": <str>, "history": <list[dict]>, "question": <str>}``
        """
        event = task_context.event

        # --- RAG context (rag-engine-rs build_rag_prompt format) ---
        retrieve_result = task_context.get_node_output("RetrieveChunksNode")["result"]
        chunks: list[dict] = retrieve_result.get("chunks", [])

        context_parts: list[str] = []
        for chunk in chunks:
            section = chunk.get("section_title") or "General"
            score = chunk.get("score", 0.0)
            content = chunk.get("content", "")
            context_parts.append(
                f"Section: {section} (relevance: {score:.2f})\n{content}"
            )
        context_block = "\n\n".join(context_parts)

        # --- Session memory (prior turns) ---
        chat_session = self._load_session(event.session_id)
        prior_turns: list[dict] = []
        if chat_session is not None and chat_session.turns:
            prior_turns = list(chat_session.turns)

        task_context.update_node(
            node_name=self.node_name,
            result={
                "context": context_block,
                "history": prior_turns,
                "question": event.question,
            },
        )
        return task_context
