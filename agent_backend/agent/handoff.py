"""Handoff tools and router functions for cross-agent task transfer."""

from langchain_core.tools import tool
from agent_backend.agent.state import MultiAgentState


# ── Handoff tool definitions ─────────────────────────────────

@tool
def handoff_to_pre_sales(reason: str) -> str:
    """将对话转接给售前顾问（pre_sales），用于活动查询和购票。
    当用户在当前售后对话中想了解活动或购买新票时调用。

    Args:
        reason: 转接原因，说明用户的具体需求（如"用户想查询毕业晚会信息"）
    """
    return f"[转接确认] 已转接至售前顾问。原因：{reason}"


@tool
def handoff_to_after_sales(reason: str) -> str:
    """将对话转接给售后顾问（after_sales），用于订单查询和票务政策。
    当用户在当前售前对话中想查订单或问退款时调用。

    Args:
        reason: 转接原因，说明用户的具体需求（如"用户想查询上次的订单状态"）
    """
    return f"[转接确认] 已转接至售后顾问。原因：{reason}"


HANDOFF_TOOLS = [handoff_to_pre_sales, handoff_to_after_sales]


# ── Handoff detection ────────────────────────────────────────

_HANDOFF_TOOL_NAMES = {t.name for t in HANDOFF_TOOLS}


def is_handoff_tool(tool_name: str) -> bool:
    return tool_name in _HANDOFF_TOOL_NAMES


def extract_handoff_target(tool_name: str) -> str:
    """Extract target agent name from handoff tool name.
    e.g. 'handoff_to_pre_sales' → 'pre_sales'
    """
    prefix = "handoff_to_"
    if tool_name.startswith(prefix):
        return tool_name[len(prefix):]
    return ""


# ── Router functions ─────────────────────────────────────────

def pre_sales_router(state: MultiAgentState) -> str:
    """After pre_sales_agent: go to supervisor if handoff, else end."""
    if state.get("handoff_to"):
        return "supervisor"
    return "end"


def after_sales_router(state: MultiAgentState) -> str:
    """After after_sales_agent: go to supervisor if handoff, else end."""
    if state.get("handoff_to"):
        return "supervisor"
    return "end"
