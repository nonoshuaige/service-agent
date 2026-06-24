from agent_backend.tools.ticket_tools import TICKET_TOOLS
from agent_backend.tools.general_tools import GENERAL_TOOLS

AGENT_TOOL_MAP: dict[str, list] = {
    "ticket": TICKET_TOOLS,
    "general": GENERAL_TOOLS,
    "customer_service": [],
}


def get_agent_tools(agent_type: str) -> list:
    return AGENT_TOOL_MAP.get(agent_type, AGENT_TOOL_MAP.get("general", []))
