"""UpdateSessionMemoryNode — append new Q&A turns to the ChatSession.

After the ``AnswerNode`` generates a grounded answer, this node:
1. Loads the existing ``ChatSession`` (or creates a new one if this is the
   first turn for this session id).
2. Appends the user question and assistant answer as new turns.
3. Extends ``topics_covered`` from any cited sections in the answer.
4. Persists the session via ``GenericRepository`` using the ``db_session``
   factory (CLAUDE.md rule 7 — no deployment logic inside the node).

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

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def process(self, task_context: TaskContext) -> TaskContext:
        """Append the new Q&A turn and persist the session.

        Reads:
          - ``AssembleContextNode`` output: ``question``.
          - ``AnswerNode`` output: the ``OutputType`` result with ``answer``
            and ``cited_sections``.
          - ``task_context.event``: ``session_id``, ``doc_id``.

        Writes:
          - ``UpdateSessionMemoryNode`` result:
            ``{"session_id": <str>, "turns": <int>}``.
        """
        event = task_context.event

        # Read the user question from AssembleContextNode
        assembled = task_context.get_node_output("AssembleContextNode")["result"]
        question: str = assembled.get("question", "")

        # Read the assistant answer from AnswerNode
        answer_output = task_context.get_node_output("AnswerNode")["result"]
        # AnswerNode stores result as OutputType (Pydantic model) serialized by
        # run_agent_recorded → update_node. to_jsonable converts it to a dict.
        if hasattr(answer_output, "answer"):
            # Pydantic model instance
            answer_text: str = answer_output.answer
            cited_sections: list[str] = list(answer_output.cited_sections or [])
        else:
            # Already a dict (serialized by to_jsonable)
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
