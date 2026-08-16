from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from api.schema.chat import ChatData, ChatRequest, ChatResponse
from llm import get_llm
from prompt.loader import load_system_prompt


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        llm = get_llm()

        system_prompt = load_system_prompt()

        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=request.message),
            ]
        )

        content = response.content

        if isinstance(content, str):
            text = content.strip()

        elif isinstance(content, list):
            text = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
            ).strip()

        else:
            text = str(content).strip() if content else ""

        if not text:
            raise HTTPException(
                status_code=502,
                detail="LLM returned an empty response.",
            )

        return ChatResponse(
            status="success",
            data=ChatData(
                answer=text
            ),
        )

    except HTTPException:
        raise

    except Exception as e:
        print("Chat error:", repr(e))

        raise HTTPException(
            status_code=500,
            detail="Failed to generate response.",
        ) from e