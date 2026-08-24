from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.router.chat import router as chat_router
from api.router.health import router as health_router
from api.router.llm import router as llm_router
from mcp_client.agent import (
    start_mcp_runtime,
    stop_mcp_runtime,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start the MCP stdio process once when FastAPI starts and keep it alive
    until FastAPI shuts down. This preserves the Playwright browser session
    across separate chat messages.
    """
    await start_mcp_runtime()

    try:
        yield

    finally:
        await stop_mcp_runtime()


app = FastAPI(
    title="MCP AI Assistant",
    description="Groq + LangChain + MCP based AI Assistant",
    version="1.0.0",
    lifespan=lifespan,
)


templates = Jinja2Templates(
    directory="templates"
)


app.mount(
    "/static",
    StaticFiles(
        directory="static"
    ),
    name="static",
)


app.include_router(
    health_router
)

app.include_router(
    llm_router
)

app.include_router(
    chat_router
)


@app.get("/")
async def home(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
