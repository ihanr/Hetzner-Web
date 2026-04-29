import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.core.config import STATIC_DIR
from app.tasks.scheduler import start_background_tasks
from app.api.endpoints import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动后台任务 (流量监控, 定时任务, Telegram 机器人等)
    start_background_tasks()
    yield

app = FastAPI(
    title="Hetzner Web Console",
    version="modular-v1",
    lifespan=lifespan
)

# 挂载 API 路由
app.include_router(api_router)

# 挂载静态文件
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
@app.get("/demo")
def index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Static files not found"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "modular-v1"}
