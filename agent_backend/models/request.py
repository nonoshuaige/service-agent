from pydantic import BaseModel, Field


class CreateSessionReq(BaseModel):
    agent_type: str = Field(default="ticket", description="Agent type: ticket | general | customer_service")
    title: str | None = Field(default=None, description="Optional session title")


class ChatStreamReq(BaseModel):
    session_id: str | None = Field(default=None, description="Session ID, null to auto-create")
    agent_type: str = Field(default="ticket", description="Agent type")
    message: str = Field(..., min_length=1, description="User message")
