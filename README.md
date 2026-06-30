# Service Agent

校园活动票务智能助手，基于 FastAPI + LangGraph Supervisor + Redis + MySQL 的多 Agent 对话系统。

> 版本：v1.7 | 最后更新：2026-06-30

## 概述

在现有校园活动票务系统（Spring Boot + Vue 3）基础上，基于 LangGraph StateGraph 构建 **Router 多 Agent 架构**（3 Agent）：

- **Router Agent** — 单一 Agent 同时完成改写查询 + 意图分类 + 闲聊回复 + 路由调度（单次 LLM）
- **售前 Agent** — 搜索活动（内置 event 表 schema）、购票下单、计算器
- **售后 Agent** — 查询订单、票务政策FAQ、计算器
- **Handoff 跨Agent协作** — 子Agent互相感知，可传递任务（handoff 路由 0 LLM）
- **双层存储** — Redis 热数据缓存 + MySQL 全量持久化
- **性能优化** — 问候语快速通道（0 LLM）+ 快慢模型分离（Router 用 flash，子Agent 用完整模型）
- **SSE 流式推送** — thinking / intent / route / tool_call / tool_result / final / done
- **数据可靠** — Redis 热数据兜底恢复，MySQL 无数据时自动补齐

## 架构

```
Vue 3 前端 (localhost:5173)
    │  Authorization: Bearer <JWT>
    ▼
FastAPI Agent 后端 (localhost:8000)
    │
    ├── router (rewrite+intent+chitchat+routing) → pre_sales | after_sales
    │                                               │  handoff  │
    │                                               └───────────┘
    ├── JWT 验证 → ContextVar → 工具层转发到 Spring Boot
    ├── Redis 热数据 (7天TTL) + MySQL 全量持久化
    └── SSE 流式输出
    │
    ▼
Spring Boot 后端 (localhost:8080)
```

## 快速开始

### 环境要求

- Python 3.11+
- Redis（Docker 容器）
- 可访问的 LLM API（智谱 / DeepSeek）
- 运行中的 Spring Boot 后端（活动/订单 API）

### 安装

```bash
conda create -n agent python=3.11 -y
conda activate agent
pip install -r requirements.txt
```

### 配置

复制并编辑 `.env` 文件：

```env
LLM_PROVIDER=zhipu
ZHIPU_API_KEY=your-api-key
ZHIPU_MODEL=glm-4.5-air
JWT_SECRET=与SpringBoot共享的密钥
REDIS_URL=redis://localhost:6379/0
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=agent_db
```

### 启动

```bash
uvicorn agent_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

验证：`curl http://localhost:8000/health` → `{"status": "ok"}`

### 测试

```bash
# 获取 JWT（从票务系统登录）
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800138000","password":"123456"}'

# 流式对话（意图自动识别，agent_type 已废弃）
curl -X POST http://localhost:8000/api/v1/agent/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "帮我查一下有什么活动"}'
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agent/sessions` | 创建会话 |
| GET | `/api/v1/agent/sessions` | 会话列表（含 active_session_id） |
| PATCH | `/api/v1/agent/sessions/{id}` | 重命名会话 |
| DELETE | `/api/v1/agent/sessions/{id}` | 删除会话 |
| GET | `/api/v1/agent/sessions/{id}` | 会话详情（最近 20 条 + has_more） |
| GET | `/api/v1/agent/sessions/{id}/messages?before_seq=N` | 游标分页加载更早消息 |
| POST | `/api/v1/agent/chat/stream` | SSE 流式对话（意图自动识别） |

## SSE 事件类型

| 事件 | 含义 |
|------|------|
| `thinking` (start) | 开始处理 |
| `thinking` (intent) | 意图识别结果：chitchat / pre_sales / after_sales |
| `thinking` (route) | 路由调度结果 |
| `tool_call` | 子Agent调用工具 |
| `tool_result` | 工具返回结果 |
| `final` | 最终回复 |
| `error` | 错误信息 |
| `done` | 流结束 |

## 多 Agent 工具分配

| Agent | 工具 |
|-------|------|
| router（路由 + 闲聊） | 无（纯 LLM 决策，闲聊直接回复） |
| pre_sales（售前） | search_events (含event表schema), create_order, calculator |
| after_sales（售后） | query_my_orders, calculator |

## 项目结构

```
agent_backend/
├── main.py                  # FastAPI 入口 + lifespan
├── config.py                # 配置管理
├── api/                     # HTTP 层（路由 + JWT 依赖注入）
├── auth/                    # JWT 验证 + token 传播
├── agent/                   # Router 多 Agent 核心
│   ├── state.py             # MultiAgentState 定义
│   ├── graph.py             # LangGraph StateGraph 编排 (v1.7: 3节点)
│   ├── router.py            # ★ Router Agent — 合并 rewrite+intent+chitchat+supervisor
│   ├── nodes.py             # LLM 工厂
│   ├── prompts.py           # System Prompt 模板 (v1.7: 3个)
│   ├── handoff.py           # handoff 工具 + router
│   ├── prompt_builder.py    # build_messages 工具函数 (legacy)
│   └── sub_agents/          # 子Agent实现
│       ├── pre_sales.py     # 售前 Agent
│       └── after_sales.py   # 售后 Agent
├── tools/                   # 工具定义 + 注册表
├── storage/                 # MySQL 持久化层
├── context/                 # Redis 上下文中心
├── models/                  # Pydantic 请求/响应模型
└── utils/                   # Redis 客户端 + SSE 工具
```

## 技术栈

| 组件 | 用途 |
|------|------|
| FastAPI | Web 框架 |
| LangGraph | Supervisor → Router 多 Agent 编排 |
| LangChain + langchain-openai | LLM 抽象 + 工具定义 |
| Redis | 热数据缓存（全 Key 7 天 TTL） |
| MySQL (aiomysql) | 全量消息持久化 + 压缩记录 |
| SSE | 流式推送 |
| python-jose | JWT 验证 |
| httpx | 后端 API 调用 |

## 关联项目

- [校园活动票务系统](https://github.com/nonoshuaige/school-ticket) — Spring Boot + Vue 3 主项目
- 详细设计文档：[开发文档.md](./开发文档.md)
