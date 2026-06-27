from pydantic import BaseModel, Field


class CreateSessionReq(BaseModel):
    agent_type: str | None = Field(
        default=None,
        description="Agent type (optional, auto-classified if omitted). "
                    "Accepted: chitchat | pre_sales | after_sales. "
                    "Legacy values ticket/general/customer_service are auto-mapped."
    )
    title: str | None = Field(default=None, description="Optional session title")


class ChatStreamReq(BaseModel):
    session_id: str | None = Field(default=None, description="Session ID, null to auto-create")
    agent_type: str | None = Field(
        default=None,
        description="Agent type (optional, intent is now auto-classified). "
                    "If provided, used as fallback when LLM classification fails."
    )
    message: str = Field(..., min_length=1, description="User message")
