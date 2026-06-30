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
async def search_events(
    keyword: str = "",
    status: int | None = None,
    page: int = 1,
    page_size: int = 8,
) -> str:
    """搜索校园活动。数据库 event 表存储所有活动，后端按时间窗口自动过滤。

    ## event 表字段
    字段              | 类型          | 说明
    event_id          | BIGINT        | 活动ID
    title             | VARCHAR(100)  | 活动标题，keyword 对此字段模糊匹配
    description       | TEXT          | 活动描述
    organizer         | VARCHAR(100)  | 主办方
    venue             | VARCHAR(100)  | 场地
    poster_url        | VARCHAR(255)  | 海报URL
    sale_start_time   | DATETIME      | 开售时间
    sale_end_time     | DATETIME      | 停售时间
    event_start_time  | DATETIME      | 活动开始时间
    event_end_time    | DATETIME      | 活动结束时间
    status            | TINYINT       | 活动状态
    minPrice          | DECIMAL       | 最低票价（从 ticket_category 表自动计算）

    ## status 枚举（后端按时间窗口自动过滤）
    - 0 = 预热中：sale_start_time > 当前时间（尚未开售）
    - 1 = 售票中：sale_start_time <= 当前时间 < sale_end_time（热卖中 / 正在售票）
    - 2 = 已结束
    - 3 = 已下架

    ## 关键词 → 参数映射规则
    | 用户说法 | 参数 |
    |---------|------|
    | "热卖" / "现在有什么活动" / "正在售票" / "能买票的活动" | status=1 |
    | "即将开始" / "即将开售" / "预售" / "预热" | status=0 |
    | 具体活动名称如"毕业晚会" / "十佳歌手" | keyword="毕业晚会" |
    | "推荐" / "好看的" / "有什么好看的"（无具体名称） | keyword="" 且 status=1 |

    Args:
        keyword: 活动标题关键词，空字符串则不按标题筛选
        status: 活动状态。1=售票中, 0=预热中, None=全部
        page: 页码
        page_size: 每页条数
    """
    async with httpx.AsyncClient() as client:
        try:
            params = {"page": page, "pageSize": page_size}
            if status is not None:
                params["status"] = status

            resp = await client.get(
                f"{settings.ticket_backend_url}/api/v1/event/list",
                params=params,
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
                f"¥{e.get('minPrice', '?')}起 | "
                f"开售: {e.get('saleStartTime', '?')} | 停售: {e.get('saleEndTime', '?')} | "
                f"活动时间: {e.get('eventStartTime', '?')}"
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
