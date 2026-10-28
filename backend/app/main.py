import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__, database, scheduler
from app.config import get_settings
from app.routers import auth, issues, settings, setup
from app.security import ensure_admin, forget_secret, setup_code

FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend_dist"))


def _on_db_ready():
    """数据库连接成功后（启动时或安装向导保存后）：建管理员、按保存的时间排早晚报"""
    forget_secret()
    ensure_admin()
    scheduler.reschedule()
    print("[startup] 数据库已连接", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    database.add_ready_hook(_on_db_ready)
    if database.configured_url():
        # 放到后台连接，网页可以立刻打开（MySQL 未就绪时会重试约 1 分钟，之后由定时重连接手）
        asyncio.get_running_loop().run_in_executor(None, lambda: database.connect_from_saved(force=True, retries=20))
    else:
        print("[startup] 未配置数据库，请在网页安装向导中填写 MySQL 信息", flush=True)
    scheduler.start(run_jobs=not os.environ.get("MYNEWS_NO_JOBS"))   # 测试里不跑后台任务
    print(f"[startup] 我的新闻 {__version__} 已启动，Web 端口 {s.http_port}", flush=True)
    print(f"[startup] 首次设置的安装码：{setup_code()}（只有从公网地址打开安装向导时才需要；内网访问不用）", flush=True)
    yield
    scheduler.stop()


app = FastAPI(title="MyNews", version=__version__, lifespan=lifespan)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # 详情只进日志；返回给客户端的只有异常类型，避免带出内部路径 / SQL 等信息
    print(f"[error] {request.method} {request.url.path}: {exc!r}", flush=True)
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误：{type(exc).__name__}"})


for r in (setup.router, auth.router, settings.router, issues.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        root = os.path.realpath(FRONTEND_DIR)
        f = os.path.realpath(os.path.join(root, path))
        if path and f.startswith(root + os.sep) and os.path.isfile(f):
            return FileResponse(f)
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
