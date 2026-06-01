from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class CustomerCareEventSchema(BaseModel):
    ticket_id: UUID = Field(
        default_factory=uuid4, description="Unique identifier for the ticket"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time when the ticket was created",
    )
    from_email: str = Field(..., description="Email address of the sender")
    to_email: str = Field(..., description="Email address of the recipient")
    sender: str = Field(..., description="Name or identifier of the sender")
    subject: str = Field(..., description="Subject of the ticket")
    body: str = Field(..., description="The body of the ticket")
