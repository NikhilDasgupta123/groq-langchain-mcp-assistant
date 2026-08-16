from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from api.schema.chat import ChatRequest, ChatResponse
from llm import get_llm


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        llm = get_llm()

        response = await llm.ainvoke(
            [HumanMessage(content=request.message)]
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
            print("Empty LLM response:", response)

            raise HTTPException(
                status_code=502,
                detail="Groq returned an empty LLM response.",
            )

        return ChatResponse(
            response=text
        )

    except HTTPException:
        raise

    except Exception as e:
        print("Chat error:", repr(e))

        raise HTTPException(
            status_code=500,
            detail=str(e),
        ) from e