from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


def build_system_prompt(
    long_term: dict,
    summary: str,
    tools_desc: str,
) -> str:
    """Build the system prompt with prefix-cache-friendly layout."""
    parts = [
        "你是校园活动票务智能助手，帮助用户查询活动、订票、查订单等。请用中文回复。",
        "",
        "## 重要：工具使用规则",
        "当用户询问以下内容时，你**必须调用对应的工具**获取真实数据，绝对不能凭猜测或编造回答：",
        "- 查询活动/演出/晚会/比赛/热卖/推荐/有什么好看的 → 调用 search_events",
        "- 查询我的订单/购票记录 → 调用 query_my_orders",
        "- 购买门票/下单 → 调用 create_order",
        "- 数学计算 → 调用 calculator",
        "只要用户的问题涉及以上场景，就先调用工具，再基于工具返回的真实结果回答用户。",
        "",
        "## search_events 使用技巧",
        "当用户想找「热卖」「热门」「推荐」的活动时，这些不是活动名称，",
        "直接用 keyword=\"\"（空字符串）获取全部活动，然后从返回结果中向用户推荐。",
        "只有当用户明确提到了具体活动名称（如「毕业晚会」「十佳歌手」）时，才用这些词做 keyword。",
    ]

    if long_term:
        prefs = "\n".join(f"- {k}: {v}" for k, v in long_term.items())
        parts.append(f"\n## 用户偏好\n{prefs}")

    parts.append(f"\n## 对话摘要\n{summary or '新对话'}")

    if tools_desc:
        parts.append(f"\n## 可用工具\n{tools_desc}")

    return "\n".join(parts)


def build_messages(
    system_prompt: str,
    recent_messages: list[dict],
    user_query: str,
) -> list:
    messages = [SystemMessage(content=system_prompt)]

    for m in recent_messages:
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            messages.append(AIMessage(content=m["content"]))

    messages.append(HumanMessage(content=user_query))
    return messages
