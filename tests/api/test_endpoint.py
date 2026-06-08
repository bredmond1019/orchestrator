from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from database.event import Event
from database.session import Base, db_session
from main import app
from worker.config import celery_app

VALID_PAYLOAD = {
    "from_email": "sender@example.com",
    "to_email": "support@example.com",
    "sender": "Test User",
    "subject": "Test Subject",
    "body": "This is a test message.",
}


@pytest.fixture
def endpoint_context():
    """Yields (TestClient, session) sharing the same in-memory SQLite DB.

    Both the FastAPI dependency override and the test assertions use the same
    session object, so database state is visible to the test after each request.
    """
    # StaticPool + check_same_thread=False allows a single in-memory connection to be
    # shared across threads — needed because FastAPI runs sync handlers in a thread pool.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    def override_db_session():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[db_session] = override_db_session
    client = TestClient(app, raise_server_exceptions=False)

    yield client, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


class TestEndpointGhostRow:
    def test_failed_enqueue_does_not_commit_event(self, endpoint_context):
        """send_task raising must leave the Event table empty — no orphaned row."""
        client, session = endpoint_context

        with patch.object(
            celery_app, "send_task", side_effect=RuntimeError("Redis unavailable")
        ):
            response = client.post("/events/", json=VALID_PAYLOAD)

        assert response.status_code == 500
        assert session.query(Event).count() == 0

    def test_successful_enqueue_commits_event(self, endpoint_context):
        """send_task succeeding must result in exactly one committed Event row."""
        client, session = endpoint_context
        mock_result = MagicMock()

        with patch.object(celery_app, "send_task", return_value=mock_result):
            response = client.post("/events/", json=VALID_PAYLOAD)

        assert response.status_code == 202
        assert session.query(Event).count() == 1
