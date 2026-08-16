from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatData(BaseModel):
    answer: str


class ChatResponse(BaseModel):
    status: str
    data: ChatData