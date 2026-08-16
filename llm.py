from langchain_groq import ChatGroq

from config import GROQ_API_KEY, GROQ_MODEL


def get_llm():
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing")

    return ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=0.6,
        max_tokens=2048,
        reasoning_effort="low",
        model_kwargs={
            "include_reasoning": False,
        },
        timeout=30,
        max_retries=2,
    )