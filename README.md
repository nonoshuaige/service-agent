# Service Agent

校园活动票务智能助手，基于 FastAPI + LangChain + Redis 的 AI Agent 对话系统。

## 概述

在现有校园活动票务系统（Spring Boot + Vue 3）基础上，提供智能对话能力。Agent 能够：
- 调用工具查询活动、订单、执行计算
- 维护用户三层记忆（长期偏好 + 会话摘要 + 近期对话）
- 通过 SSE 流式推送思考过程和回复
- 将用户 JWT 全链路传递到 Spring Boot 后端

## 架构

```
Vue 3 前端 (localhost:5173)
    │  Authorization: Bearer <JWT>
    ▼
FastAPI Agent 后端 (localhost:8000)
    │  POST /api/v1/agent/chat/stream  (SSE)
    │  POST /api/v1/agent/sessions
    │
    ├── JWT 验证 → 提取 userId → ContextVar 存储 token
    ├── LLM 调用 (智谱 GLM-4.6V / DeepSeek)
    ├── 工具执行 → 转发 JWT 到后端
    ├── Redis 上下文存储 + 活跃会话追踪
    └── 会话重命名 + 自动恢复上次对话
    │
    ▼
Spring Boot 后端 (localhost:8080)
```

## 快速开始

### 环境要求

- Python 3.11+
- Redis（Docker 容器）
- 可访问的 LLM API（智谱 / DeepSeek）
- 运行中的 Spring Boot 后端（活动/订单/用户 API）

### 安装

```bash
conda create -n agent python=3.11 -y
conda activate agent
pip install -r requirements.txt
```

### 配置

复制并编辑 `.env` 文件，填入 API Key 和 JWT Secret：

```env
LLM_PROVIDER=zhipu
ZHIPU_API_KEY=your-api-key
JWT_SECRET=与SpringBoot共享的密钥
REDIS_URL=redis://localhost:6379/0
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

# 流式对话
curl -X POST http://localhost:8000/api/v1/agent/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"agent_type": "ticket", "message": "帮我查一下有什么活动"}'
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agent/sessions` | 创建会话 |
| GET | `/api/v1/agent/sessions` | 会话列表（含 active_session_id） |
| PATCH | `/api/v1/agent/sessions/{id}` | 重命名会话 |
| DELETE | `/api/v1/agent/sessions/{id}` | 删除会话 |
| GET | `/api/v1/agent/sessions/{id}` | 会话详情（含历史消息） |
| POST | `/api/v1/agent/chat/stream` | SSE 流式对话 |

## SSE 事件类型

| 事件 | 含义 |
|------|------|
| `thinking` | 正在分析/推理 |
| `tool_call` | 调用工具 |
| `tool_result` | 工具返回结果 |
| `final` | 最终回复 |
| `error` | 错误信息 |
| `done` | 流结束 |

## 项目结构

```
agent_backend/
├── main.py              # FastAPI 入口
├── config.py            # 配置管理
├── api/                 # HTTP 层（路由 + 依赖注入）
├── auth/                # JWT 验证 + token 传播
├── agent/               # LLM 工厂 + Prompt 构建 + LangGraph 预留
├── tools/               # 工具定义（票务/通用）+ 注册表
├── context/             # 三层记忆（Redis）
├── models/              # Pydantic 请求/响应模型
└── utils/               # Redis 客户端 + SSE 工具
```

## 技术栈

| 组件 | 用途 |
|------|------|
| FastAPI | Web 框架 |
| LangChain + langchain-openai | LLM 抽象 + 工具定义 |
| LangGraph | 状态机编排（预留） |
| Redis | 上下文缓存 + 会话存储 |
| SSE | 流式推送 |
| python-jose | JWT 验证 |
| httpx | 后端 API 调用 |

## 关联项目

- [校园活动票务系统](https://github.com/nonoshuaige/school-ticket) — Spring Boot + Vue 3 主项目
- 详细设计文档：[开发文档.md](./开发文档.md)
