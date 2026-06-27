from agent_backend.tools.ticket_tools import search_events, query_my_orders, create_order
from agent_backend.tools.general_tools import calculator


AGENT_TOOL_MAP: dict[str, list] = {
    # ── Legacy mappings (backward compatible) ──
    "ticket": [search_events, query_my_orders, create_order, calculator],
    "general": [calculator],
    "customer_service": [query_my_orders],

    # ── New supervisor-based agent mappings ──
    "pre_sales": [search_events, create_order, calculator],
    "after_sales": [query_my_orders, calculator],
    "chitchat": [],
}


def get_agent_tools(agent_type: str) -> list:
    return AGENT_TOOL_MAP.get(agent_type, AGENT_TOOL_MAP.get("general", []))
