from fastapi import APIRouter, HTTPException

from api.schema.chat import ChatData, ChatRequest, ChatResponse, MCPTrace
from mcp_client.agent import run_mcp_agent
from prompt.loader import load_system_prompt


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        system_prompt = load_system_prompt()

        answer, mcp_trace = await run_mcp_agent(
            user_message=request.message,
            system_prompt=system_prompt,
        )

        return ChatResponse(
            status="success",
            data=ChatData(
                answer=answer,
                mcp=MCPTrace(**mcp_trace),
            ),
        )

    except HTTPException:
        raise

    except Exception as exc:
        print("Chat/MCP error:", repr(exc))

        raise HTTPException(
            status_code=500,
            detail="Failed to generate MCP agent response.",
        ) from exc
