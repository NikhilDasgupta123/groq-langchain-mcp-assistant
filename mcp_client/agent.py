from pathlib import Path
import sys
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from llm import get_llm


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "local": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "cwd": str(PROJECT_ROOT),
            }
        }
    )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))

        return "".join(parts).strip()

    return str(content).strip() if content is not None else ""


def _extract_tool_trace(messages: list[Any]) -> list[dict[str, Any]]:
    tool_calls_by_id: dict[str, dict[str, Any]] = {}
    ordered_calls: list[dict[str, Any]] = []

    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                call_id = str(call.get("id") or "")

                entry = {
                    "name": str(call.get("name") or "unknown_tool"),
                    "arguments": call.get("args") or {},
                    "result": None,
                }

                ordered_calls.append(entry)

                if call_id:
                    tool_calls_by_id[call_id] = entry

        elif isinstance(message, ToolMessage):
            call_id = str(message.tool_call_id or "")
            result = _content_to_text(message.content)

            entry = tool_calls_by_id.get(call_id)

            if entry is not None:
                entry["result"] = result
            else:
                ordered_calls.append(
                    {
                        "name": str(message.name or "unknown_tool"),
                        "arguments": {},
                        "result": result,
                    }
                )

    return ordered_calls


async def run_mcp_agent(
    user_message: str,
    system_prompt: str,
) -> tuple[str, dict[str, Any]]:

    mcp_client = _build_mcp_client()

    async with mcp_client.session("local") as session:
        tools = await load_mcp_tools(session)

        available_tools = [tool.name for tool in tools]

        llm = get_llm()

        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
        )

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ]
            }
        )

    messages = result.get("messages", [])

    if not messages:
        raise RuntimeError("Agent returned no messages.")

    answer = _content_to_text(messages[-1].content)

    if not answer:
        raise RuntimeError("Agent returned an empty final response.")

    tool_calls = _extract_tool_trace(messages)

    mcp_trace = {
        "connected": True,
        "available_tools": available_tools,
        "tool_used": bool(tool_calls),
        "tool_calls": tool_calls,
    }

    return answer, mcp_trace
