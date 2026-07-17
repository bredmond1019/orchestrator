"""UpdateSessionMemoryNode — append new Q&A turns to the ChatSession.

Terminal node for both branches of the confidence-gated DAG (block OR.L):
the normal ``AnswerNode`` path and the deterministic ``AbstainNode`` path.
Whichever branch ran, this node:
1. Reads the unified answer envelope (design decision 5) from whichever of
   ``AnswerNode`` / ``AbstainNode`` actually produced output — exactly one of
   the two runs per event, so a plain membership check on
   ``task_context.nodes`` picks the right one.
2. Loads the existing ``ChatSession`` (or creates a new one if this is the
   first turn for this session id).
3. Appends the user question and assistant answer as new turns.
4. Extends ``topics_covered`` from any cited sections in the answer.
5. Persists the session via ``GenericRepository`` using the ``db_session``
   factory (CLAUDE.md rule 7 — no deployment logic inside the node).

The user question is read from ``task_context.event.question`` directly
(rather than from ``AssembleContextNode``'s output) since the abstain branch
never runs ``AssembleContextNode`` at all.

Two persistence seams (``_load_session`` / ``_persist``) are isolated so tests
never touch a real database.
"""

from contextlib import contextmanager

from core.nodes.base import Node
from core.task import TaskContext
from database.chat_session import ChatSession
from database.repository import GenericRepository
from database.session import db_session


class UpdateSessionMemoryNode(Node):
    """Persist the new turn (user question + assistant answer) to ChatSession."""

    # ------------------------------------------------------------------
    # DB seams — patched in tests
    # ------------------------------------------------------------------

    def _load_session(self, session_id) -> ChatSession | None:
        """Load an existing ChatSession by id, or return None.

        Tests monkeypatch this to return a fixture session or None.
        """
        with contextmanager(db_session)() as session:
            return GenericRepository(
                session=session, model=ChatSession
            ).get(str(session_id))

    def _persist(self, chat_session: ChatSession) -> None:
        """Persist (create or update) the ChatSession via GenericRepository.

        Uses ``create`` for new sessions and ``update`` (merge) for existing
        ones. Tests monkeypatch this method so no real DB connection is needed.
        """
        with contextmanager(db_session)() as session:
            repo = GenericRepository(session=session, model=ChatSession)
            if repo.exists(id=chat_session.id):
                repo.update(chat_session)
            else:
                repo.create(chat_session)

    @staticmethod
    def _get_answer_envelope(task_context: TaskContext):
        """Return the answer envelope from whichever terminal node produced it.

        Three possibilities per event, checked most-downstream-first:

        - ``VerifyCitationsNode`` (block OR.L, Task 3): ran on the answered
          branch, after ``AnswerNode`` — its output is the final envelope
          (verified/unverified citations, corroboration, and any
          citations-unverified withhold), so it must win over the raw
          ``AnswerNode`` output when both are present.
        - ``AnswerNode``: the answered branch before ``VerifyCitationsNode``
          existed, or a workflow wired without citation verification.
        - ``AbstainNode``: the confidence-gated abstain path (block OR.L,
          Task 2) — no ``AnswerNode``/``VerifyCitationsNode`` ever ran.

        Raises:
            KeyError: descriptive error if none of the three has run
                (mis-ordered workflow), matching
                ``TaskContext.get_node_output``'s contract.
        """
        if "VerifyCitationsNode" in task_context.nodes:
            return task_context.get_node_output("VerifyCitationsNode")["result"]
        if "AnswerNode" in task_context.nodes:
            return task_context.get_node_output("AnswerNode")["result"]
        return task_context.get_node_output("AbstainNode")["result"]

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def process(self, task_context: TaskContext) -> TaskContext:
        """Append the new Q&A turn and persist the session.

        Reads:
          - ``task_context.event``: ``question``, ``session_id``, ``doc_id``.
          - Whichever of ``AnswerNode`` / ``AbstainNode`` ran: the answer
            envelope (``answer`` + ``cited_sections``).

        Writes:
          - ``UpdateSessionMemoryNode`` result:
            ``{"session_id": <str>, "turns": <int>}``.
        """
        event = task_context.event

        # The user question is always available on the event itself — the
        # abstain branch never runs AssembleContextNode, so it can't be the
        # source of truth here.
        question: str = event.question

        # Read the answer envelope from whichever branch produced it.
        answer_output = self._get_answer_envelope(task_context)
        # AnswerNode stores result as OutputType (Pydantic model) serialized by
        # run_agent_recorded → update_node. to_jsonable converts it to a dict.
        # AbstainNode always stores a plain dict.
        if hasattr(answer_output, "answer"):
            # Pydantic model instance
            answer_text: str = answer_output.answer
            cited_sections: list[str] = list(answer_output.cited_sections or [])
        else:
            # Already a dict (serialized by to_jsonable, or AbstainNode's envelope)
            answer_text = answer_output.get("answer", "")
            cited_sections = list(answer_output.get("cited_sections", []))

        # Load or create the session
        chat_session = self._load_session(event.session_id)
        is_new = chat_session is None
        if is_new:
            chat_session = ChatSession(
                id=event.session_id,
                doc_id=event.doc_id,
                turns=[],
                topics_covered=[],
            )

        # Append the new turn pair
        current_turns: list[dict] = list(chat_session.turns or [])
        current_turns.append({"role": "user", "content": question})
        current_turns.append({"role": "assistant", "content": answer_text})
        chat_session.turns = current_turns

        # Extend topics_covered with any cited sections (deduplicated)
        existing_topics: list[str] = list(chat_session.topics_covered or [])
        new_topics = [t for t in cited_sections if t not in existing_topics]
        chat_session.topics_covered = existing_topics + new_topics

        self._persist(chat_session)

        task_context.update_node(
            node_name=self.node_name,
            result={
                "session_id": str(event.session_id),
                "turns": len(chat_session.turns),
            },
        )
        return task_context
