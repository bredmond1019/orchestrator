"""Tests for app/schemas/ingest_schema.py (OR.Q task 3).

Covers:
- ProposalIngestPayload round-trips on a valid, exact engine-rs shape
- Missing required fields (e.g. roadmap) raise ValidationError
- Empty content/artifact_id/doc_type are rejected
- ArtifactIngestPayload optional fields default to None
"""

import pytest
from pydantic import ValidationError

from schemas.ingest_schema import (
    ArtifactIngestPayload,
    IngestResponse,
    ProposalIngestPayload,
)


# ---------------------------------------------------------------------------
# ProposalIngestPayload
# ---------------------------------------------------------------------------


def _valid_proposal_payload(**overrides) -> dict:
    base = {
        "artifact_id": "prop-123",
        "company_name": "Acme Corp",
        "doc_type": "proposal",
        "section": "executive_summary",
        "content": "Some proposal content here.",
        "roadmap": {
            "situation_summary": "Client has manual workload",
            "candidates": [],
            "top_profiles": [],
            "recommended_workflow": "Invoice Automation",
            "engagement_scope": "Phase 1",
            "price_range_brl": [15000, 25000],
        },
    }
    base.update(overrides)
    return base


class TestProposalIngestPayload:
    def test_valid_payload_round_trips(self):
        data = _valid_proposal_payload()
        payload = ProposalIngestPayload(**data)
        assert payload.artifact_id == "prop-123"
        assert payload.company_name == "Acme Corp"
        assert payload.doc_type == "proposal"
        assert payload.section == "executive_summary"
        assert payload.content == "Some proposal content here."
        assert payload.roadmap == data["roadmap"]

    def test_missing_roadmap_raises(self):
        data = _valid_proposal_payload()
        del data["roadmap"]
        with pytest.raises(ValidationError, match="roadmap"):
            ProposalIngestPayload(**data)

    def test_missing_artifact_id_raises(self):
        data = _valid_proposal_payload()
        del data["artifact_id"]
        with pytest.raises(ValidationError, match="artifact_id"):
            ProposalIngestPayload(**data)

    def test_missing_company_name_raises(self):
        data = _valid_proposal_payload()
        del data["company_name"]
        with pytest.raises(ValidationError, match="company_name"):
            ProposalIngestPayload(**data)

    def test_missing_section_raises(self):
        data = _valid_proposal_payload()
        del data["section"]
        with pytest.raises(ValidationError, match="section"):
            ProposalIngestPayload(**data)

    def test_empty_content_rejected(self):
        data = _valid_proposal_payload(content="")
        with pytest.raises(ValidationError):
            ProposalIngestPayload(**data)

    def test_empty_artifact_id_rejected(self):
        data = _valid_proposal_payload(artifact_id="")
        with pytest.raises(ValidationError):
            ProposalIngestPayload(**data)

    def test_empty_doc_type_rejected(self):
        data = _valid_proposal_payload(doc_type="")
        with pytest.raises(ValidationError):
            ProposalIngestPayload(**data)


# ---------------------------------------------------------------------------
# ArtifactIngestPayload
# ---------------------------------------------------------------------------


class TestArtifactIngestPayload:
    def test_valid_minimal_payload(self):
        payload = ArtifactIngestPayload(
            artifact_id="art-1", doc_type="content", content="Body text"
        )
        assert payload.artifact_id == "art-1"
        assert payload.doc_type == "content"
        assert payload.content == "Body text"

    def test_optional_fields_default_to_none(self):
        payload = ArtifactIngestPayload(
            artifact_id="art-1", doc_type="content", content="Body text"
        )
        assert payload.section is None
        assert payload.project is None
        assert payload.title is None
        assert payload.description is None
        assert payload.metadata is None

    def test_optional_fields_accept_values(self):
        payload = ArtifactIngestPayload(
            artifact_id="art-1",
            doc_type="content",
            content="Body text",
            section="intro",
            project="orchestrator",
            title="A Title",
            description="A description",
            metadata={"source": "external"},
        )
        assert payload.section == "intro"
        assert payload.project == "orchestrator"
        assert payload.title == "A Title"
        assert payload.description == "A description"
        assert payload.metadata == {"source": "external"}

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            ArtifactIngestPayload(artifact_id="art-1", doc_type="content", content="")

    def test_missing_artifact_id_raises(self):
        with pytest.raises(ValidationError):
            ArtifactIngestPayload(doc_type="content", content="Body text")

    def test_missing_doc_type_raises(self):
        with pytest.raises(ValidationError):
            ArtifactIngestPayload(artifact_id="art-1", content="Body text")


# ---------------------------------------------------------------------------
# IngestResponse
# ---------------------------------------------------------------------------


class TestIngestResponse:
    def test_valid_response(self):
        response = IngestResponse(artifact_id="art-1", chunks_written=3)
        assert response.artifact_id == "art-1"
        assert response.chunks_written == 3

    def test_missing_fields_raise(self):
        with pytest.raises(ValidationError):
            IngestResponse(artifact_id="art-1")
