from fastapi import APIRouter

from llm import get_llm
from config import GROQ_MODEL

router = APIRouter(
    prefix="/llm",
    tags=["LLM"],
)

@router.get("/test")
async def test_llm():
    llm = get_llm()

    response = llm.invoke(
        "Reply only with: Groq LLM connection successful"
    )

    return {
        "status": "success",
        "model": GROQ_MODEL,
        "response": response.content
    }