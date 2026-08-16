from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn


app = FastAPI(
    title="MCP AI Assistant",
    description="Groq + LangChain + MCP based AI Assistant",
    version="1.0.0",
)


# HTML templates
templates = Jinja2Templates(directory="templates")


# Static files: CSS, JS, images
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )