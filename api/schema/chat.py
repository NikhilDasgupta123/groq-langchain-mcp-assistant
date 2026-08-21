from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ToolCallTrace(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None


class MCPTrace(BaseModel):
    connected: bool
    available_tools: list[str] = Field(default_factory=list)
    tool_used: bool
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)


class ChatData(BaseModel):
    answer: str
    mcp: MCPTrace


class ChatResponse(BaseModel):
    status: str
    data: ChatData
