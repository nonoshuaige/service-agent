from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


def build_system_prompt(compression: str, tools_desc: str) -> str:
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
        "工具描述包含完整的 event 表结构和「关键词→参数映射」表，",
        "根据用户说法选择对应参数：",
        "- 「热卖/现在有什么活动」→ status=1（售票中）",
        "- 「即将开始/预售」→ status=0（预热中）",
        "- 「推荐/好看的」→ keyword=\"\" + status=1",
        "- 具体名称如「毕业晚会」→ keyword=\"毕业晚会\"",
    ]

    if compression:
        parts.append(f"\n## 对话历史摘要\n{compression}")

    if tools_desc:
        parts.append(f"\n## 可用工具\n{tools_desc}")

    return "\n".join(parts)


def build_messages(system_prompt: str, recent_messages: list[dict],
                   user_query: str) -> list:
    messages = [SystemMessage(content=system_prompt)]

    for m in recent_messages:
        role = m.get("role", "")
        if role == "user":
            messages.append(HumanMessage(content=m["content"]))
        elif role == "assistant":
            messages.append(AIMessage(content=m["content"]))
        elif role == "system":
            # Compression summary injected as context
            messages.append(HumanMessage(content=m["content"]))

    messages.append(HumanMessage(content=user_query))
    return messages
