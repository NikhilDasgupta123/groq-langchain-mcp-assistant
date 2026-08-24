from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from llm import get_llm


PROJECT_ROOT = Path(__file__).resolve().parents[1]

_mcp_client: MultiServerMCPClient | None = None
_session_context: Any | None = None
_session: Any | None = None
_tools: list[Any] = []

_runtime_lock = asyncio.Lock()
_request_lock = asyncio.Lock()

# Simple in-process memory for this local single-user weekend project.
# Browser state is already persistent through the MCP session; this history
# gives the LangChain agent the previous user/assistant conversational context.
_conversation_history: list[dict[str, str]] = []
MAX_HISTORY_MESSAGES = 20


def _build_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "local": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [
                    "-m",
                    "mcp_server.server",
                ],
                "cwd": str(PROJECT_ROOT),
            }
        }
    )


async def start_mcp_runtime() -> None:
    """
    Start one long-lived stdio MCP session.

    Keeping this session open keeps the MCP subprocess alive, which in turn
    keeps the Playwright browser/page alive across separate /chat requests.
    """
    global _mcp_client
    global _session_context
    global _session
    global _tools

    if _session is not None:
        return

    async with _runtime_lock:
        if _session is not None:
            return

        client = _build_mcp_client()
        session_context = client.session("local")

        try:
            session = await session_context.__aenter__()
            tools = await load_mcp_tools(session)

        except Exception:
            try:
                await session_context.__aexit__(
                    *sys.exc_info()
                )
            except Exception:
                pass

            raise

        _mcp_client = client
        _session_context = session_context
        _session = session
        _tools = tools


async def stop_mcp_runtime() -> None:
    """
    Close the persistent MCP session and its stdio subprocess.
    """
    global _mcp_client
    global _session_context
    global _session
    global _tools

    async with _runtime_lock:
        session_context = _session_context

        _session = None
        _session_context = None
        _mcp_client = None
        _tools = []
        _conversation_history.clear()

        if session_context is not None:
            await session_context.__aexit__(
                None,
                None,
                None,
            )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)

            elif isinstance(block, dict):
                text = block.get("text")

                if text:
                    parts.append(
                        str(text)
                    )

        return "".join(parts).strip()

    return (
        str(content).strip()
        if content is not None
        else ""
    )


def _extract_tool_trace(
    messages: list[Any],
) -> list[dict[str, Any]]:
    tool_calls_by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    ordered_calls: list[
        dict[str, Any]
    ] = []

    for message in messages:

        if isinstance(
            message,
            AIMessage,
        ):
            for call in message.tool_calls or []:

                call_id = str(
                    call.get("id") or ""
                )

                entry = {
                    "name": str(
                        call.get("name")
                        or "unknown_tool"
                    ),
                    "arguments": (
                        call.get("args")
                        or {}
                    ),
                    "result": None,
                }

                ordered_calls.append(
                    entry
                )

                if call_id:
                    tool_calls_by_id[
                        call_id
                    ] = entry

        elif isinstance(
            message,
            ToolMessage,
        ):
            call_id = str(
                message.tool_call_id
                or ""
            )

            result = _content_to_text(
                message.content
            )

            entry = tool_calls_by_id.get(
                call_id
            )

            if entry is not None:
                entry["result"] = result

            else:
                ordered_calls.append(
                    {
                        "name": str(
                            message.name
                            or "unknown_tool"
                        ),
                        "arguments": {},
                        "result": result,
                    }
                )

    return ordered_calls


async def refresh_browser_and_reset_chat() -> dict[str, Any]:
    """
    Reload the current Playwright page and clear LangChain conversation memory.

    The persistent MCP/Playwright session remains alive; only the page is
    reloaded and chatbot memory is reset.
    """
    await start_mcp_runtime()

    async with _request_lock:
        reload_tool = next(
            (
                tool
                for tool in _tools
                if tool.name == "browser_reload"
            ),
            None,
        )

        if reload_tool is None:
            raise RuntimeError(
                "browser_reload MCP tool is not available."
            )

        result = await reload_tool.ainvoke({})

        _conversation_history.clear()

        return {
            "status": "refreshed",
            "browser_result": _content_to_text(result),
            "chat_memory_cleared": True,
        }


async def run_mcp_agent(
    user_message: str,
    system_prompt: str,
) -> tuple[
    str,
    dict[str, Any],
]:
    """
    Run one chat request against the same persistent MCP session.

    Requests are serialized because all browser commands intentionally act on
    one shared Playwright page/session.
    """
    await start_mcp_runtime()

    async with _request_lock:
        tools = list(_tools)

        if not tools:
            raise RuntimeError(
                "No MCP tools are available."
            )

        available_tools = [
            tool.name
            for tool in tools
        ]

        llm = get_llm()

        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
        )

        # Include prior chat context so follow-up commands such as
        # "scroll down", "close the popup", "search men's slippers",
        # or "click the first product" refer to the existing conversation.
        agent_messages = [
            *list(_conversation_history),
            {
                "role": "user",
                "content": user_message,
            },
        ]

        result = await agent.ainvoke(
            {
                "messages": agent_messages
            }
        )

        messages = result.get(
            "messages",
            [],
        )

        if not messages:
            raise RuntimeError(
                "Agent returned no messages."
            )

        answer = _content_to_text(
            messages[-1].content
        )

        if not answer:
            raise RuntimeError(
                "Agent returned an empty final response."
            )

        tool_calls = _extract_tool_trace(
            messages
        )

        # Save only conversational user/assistant text. Tool messages are
        # intentionally not stored because the real browser state already
        # persists inside Playwright/MCP and can be inspected on demand.
        _conversation_history.extend(
            [
                {
                    "role": "user",
                    "content": user_message,
                },
                {
                    "role": "assistant",
                    "content": answer,
                },
            ]
        )

        if len(_conversation_history) > MAX_HISTORY_MESSAGES:
            del _conversation_history[
                : len(_conversation_history) - MAX_HISTORY_MESSAGES
            ]

        mcp_trace = {
            "connected": True,
            "available_tools": available_tools,
            "tool_used": bool(
                tool_calls
            ),
            "tool_calls": tool_calls,
        }

        return (
            answer,
            mcp_trace,
        )
