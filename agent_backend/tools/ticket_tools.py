from langchain_core.tools import tool
import httpx
from agent_backend.config import settings
from agent_backend.auth.jwt_handler import current_jwt


def _auth_headers() -> dict:
    """Build Authorization header if a JWT is available in the current context."""
    token = current_jwt.get()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


@tool
async def search_events(keyword: str = "") -> str:
    """搜索校园活动。当用户询问有什么活动、演出、晚会、比赛、热卖、推荐时调用。
    获取的是当前所有可购票的活动列表，然后按关键词筛选。

    重要：keyword 必须是具体的活动名称关键词（如"毕业晚会"、"歌手大赛"），
    不能是抽象概念（如"热卖"、"热门"、"推荐"、"好看的"）。
    如果用户想找热门/推荐/热卖的活动，传 keyword="" 获取全部活动，再从中介绍即可。

    Args:
        keyword: 活动名称关键词，留空则返回全部活动。"毕业晚会"、"歌手大赛"等具体词。
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{settings.ticket_backend_url}/api/v1/event/list",
                params={"page": 1, "pageSize": 5},
                headers=_auth_headers(),
                timeout=10.0,
            )
            data = resp.json()
            events = data.get("data", {}).get("records", [])
            if not events:
                return "当前没有找到相关活动。"

            if keyword:
                events = [e for e in events if keyword in e.get("title", "")]

            if not events:
                return f"没有找到与'{keyword}'相关的活动。"

            return "\n".join(
                f"- {e.get('title', '未知')} | {e.get('venue', '未知')} | "
                f"¥{e.get('minPrice', '?')}起 | {e.get('saleStartTime', '未知')}"
                for e in events
            )
        except Exception as e:
            return f"查询活动失败: {str(e)}"


@tool
async def query_my_orders(status: str = "all") -> str:
    """查询当前用户的订单。当用户询问我的订单、购票记录时调用。

    Args:
        status: 订单状态，可选值: all/pending/paid/cancelled/refunded
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{settings.ticket_backend_url}/api/v1/order/list",
                params={"status": status, "page": 1, "pageSize": 10},
                headers=_auth_headers(),
                timeout=10.0,
            )
            data = resp.json()
            orders = data.get("data", {}).get("records", [])
            if not orders:
                return "当前没有订单记录。"

            return "\n".join(
                f"- 订单#{o.get('id', '?')} | {o.get('title', '未知')} | "
                f"¥{o.get('amount', '?')} | 状态: {o.get('status', '未知')}"
                for o in orders
            )
        except Exception as e:
            return f"查询订单失败: {str(e)}"


@tool
async def create_order(ticket_id: int, quantity: int = 1) -> str:
    """创建购票订单。当用户明确要购买某张票时调用。

    Args:
        ticket_id: 票种ID
        quantity: 购买数量，默认1
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{settings.ticket_backend_url}/api/v1/order/create",
                json={"ticketId": ticket_id, "quantity": quantity},
                headers=_auth_headers(),
                timeout=10.0,
            )
            data = resp.json()
            if resp.status_code >= 400:
                return f"下单失败: {data.get('msg', '未知错误')}"
            order_id = data.get("data", {}).get("id", "未知")
            return f"下单成功！订单号: {order_id}"
        except Exception as e:
            return f"下单失败: {str(e)}"


TICKET_TOOLS = [search_events, query_my_orders, create_order]
