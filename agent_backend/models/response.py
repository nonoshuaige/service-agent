from pydantic import BaseModel
from typing import Any


class ApiResponse(BaseModel):
    code: int = 200
    msg: str = "success"
    data: Any = None

    @staticmethod
    def success(data: Any = None, msg: str = "success") -> "ApiResponse":
        return ApiResponse(code=200, msg=msg, data=data)

    @staticmethod
    def error(code: int = 400, msg: str = "error") -> "ApiResponse":
        return ApiResponse(code=code, msg=msg, data=None)


class SessionInfo(BaseModel):
    session_id: str
    title: str
    agent_type: str
    last_message: str = ""
    updated_at: str = ""
    created_at: str = ""


class SessionListData(BaseModel):
    sessions: list[SessionInfo] = []
