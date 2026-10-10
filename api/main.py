# 第 1 阶段 · 顺序 2
# 写在 pyproject.toml 之后、health.py 之前。
# 第 4 阶段 · 顺序 1 在本文件追加了跨域，见下面标有「第 4 阶段」的 import 和 add_middleware。

# 第 4 阶段 · 顺序 1。读取 FRONTEND_URL。没配置时，跨域规则使用本地前端地址。
import os
# Path 用来根据本文件的位置算出项目根目录，避免写死磁盘路径。
from pathlib import Path

# 第 13 阶段。启动日志。
import logging
# 生命周期是异步上下文。
from contextlib import asynccontextmanager

# load_dotenv 把根目录 .env 里的键值读进当前进程的环境变量。
from dotenv import load_dotenv
# FastAPI 是整个后端应用的类。一个进程里创建一个实例。
# 第 7 阶段。ValueError 转成 422 时要看请求。
from fastapi import FastAPI, Request
# 第 4 阶段 · 顺序 1。跨域中间件。页面在 3000 端口，接口在 8000 端口，没有它浏览器会拦请求。
from fastapi.middleware.cors import CORSMiddleware
# 第 7 阶段。缺密钥时的响应。
from fastapi.responses import JSONResponse

# 第 13 阶段。生产环境拒绝关掉登录。
from api.clerk_auth import is_auth_disabled, is_clerk_enabled
# 第 3 阶段。启动建表，关闭时断开。
from api.db import close_db, init_db
# 导入健康检查路由。起别名 health_router，是为了后面还有别的路由时名字不撞车。
from api.routes.health import router as health_router
# 第 5 阶段。K 线路由。和 health_router 一样，先导入再挂上。
from api.routes.chart import router as chart_router
# 第 7 阶段。模型列表。
from api.routes.models import router as models_router
# 第 9 阶段。会话。
from api.routes.sessions import router as sessions_router
# 第 9 阶段。聊天。
from api.routes.chat import router as chat_router
# 第 11 阶段。公司概览和财报。
from api.routes.company import router as company_router
# 第 12 阶段。自选和早报。
from api.routes.watchlist import router as watchlist_router

# 本文件位于 <项目根>/api/main.py。
# parent 是 api 目录，parent.parent 才是项目根目录。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 读取 <项目根>/.env。文件还不存在时，这行什么都不做，也不会报错。
load_dotenv(_PROJECT_ROOT / ".env")

# 第 13 阶段。本文件的日志。
logger = logging.getLogger(__name__)
# 这两个值都表示生产环境。
_PROD_ENV_VALUES = ("production", "prod")
# 本地占位的 SEC 联系人。生产环境带着它启动会被拒绝。
_DEFAULT_SEC_HEADER = "Analyst Agent dev@localhost"


# 第 13 阶段。生产环境必须能核对登录。
def check_production_auth_config() -> None:
    # 读 ENV。
    env = (os.getenv("ENV") or "").strip().lower()
    # 记下来。
    logger.info("Startup env check: ENV=%r", env)
    # 本地不检查。
    if env not in _PROD_ENV_VALUES:
        # 返回。
        return
    # 紧急开关。
    if (os.getenv("ANALYST_ALLOW_DISABLED_AUTH") or "").lower() in ("1", "true", "yes"):
        # 警告后跳过。
        logger.warning("ANALYST_ALLOW_DISABLED_AUTH set — skipping production auth guard")
        # 返回。
        return
    # 生产环境不能关掉登录。
    if is_auth_disabled():
        # 拒绝启动。
        raise RuntimeError("Refusing to start: ENV=production with DISABLE_AUTH=true.")
    # 生产环境必须有 Clerk 密钥。
    if not is_clerk_enabled():
        # 拒绝启动。
        raise RuntimeError("Refusing to start: ENV=production but CLERK_SECRET_KEY is not set.")


# 第 13 阶段。生产环境必须有真实 SEC 联系人。
def check_production_sec_config() -> None:
    # 读 ENV。
    env = (os.getenv("ENV") or "").strip().lower()
    # 本地不检查。
    if env not in _PROD_ENV_VALUES:
        # 返回。
        return
    # 同一个紧急开关。
    if (os.getenv("ANALYST_ALLOW_DISABLED_AUTH") or "").lower() in ("1", "true", "yes"):
        # 警告后跳过。
        logger.warning("ANALYST_ALLOW_DISABLED_AUTH set — skipping production SEC_HEADER guard")
        # 返回。
        return
    # 联系人。
    header = (os.getenv("SEC_HEADER") or "").strip()
    # 没填或仍是占位。
    if not header or header == _DEFAULT_SEC_HEADER:
        # 拒绝启动。
        raise RuntimeError("Refusing to start: ENV=production but SEC_HEADER is unset or default.")


# 第 11 阶段。整个进程只设置一次 SEC 身份。
def set_sec_identity() -> None:
    # 延迟导入，避免没装 edgartools 时连健康检查都起不来。装上之后启动仍会调用。
    from edgar import set_identity
    # 环境变量优先，否则用本地占位。
    header = (os.getenv("SEC_HEADER") or "").strip() or _DEFAULT_SEC_HEADER
    # 全局只设这一次。
    set_identity(header)
    # 记下来。
    logger.info("SEC EDGAR identity set: %s", header)


# 第 3 阶段起，启动建表，关闭断开。第 11、13 阶段的检查也在这里。
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 生产登录检查。
    check_production_auth_config()
    # 生产 SEC 检查。
    check_production_sec_config()
    # SEC 身份。
    set_sec_identity()
    # 建表。
    await init_db()
    # 开始接请求。
    yield
    # 断开数据库。
    await close_db()


# 创建应用。启动命令 uvicorn api.main:app 里的 app，指的就是这个变量。
# lifespan 在开始听端口之前建表并设置 SEC 身份。
app = FastAPI(title="Analyst Agent API", lifespan=lifespan)

# 第 4 阶段 · 顺序 1。写在创建 app 之后、挂上 /health 之前。
# 把跨域规则登记进应用。不登记的话，3000 端口的页面访问不了 8000 端口。
app.add_middleware(
    # 使用 FastAPI 提供的这套跨域实现。
    CORSMiddleware,
    # 允许访问的页面来源。环境变量没设时就是本地前端。
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    # 允许浏览器在跨域请求里携带凭证。
    allow_credentials=True,
    # 允许的 HTTP 方法：读取、提交、删除。聊天走 WebSocket，不在这三项里。
    allow_methods=["GET", "POST", "DELETE"],
    # 允许浏览器附带的请求头。没列出来的头，预检会被浏览器拦住。
    allow_headers=[
        # 发送 JSON 时用来声明正文格式。
        "Content-Type",
        # Google 模型密钥。
        "X-Google-Api-Key",
        # OpenAI 模型密钥。
        "X-Openai-Api-Key",
        # Anthropic 模型密钥。
        "X-Anthropic-Api-Key",
        # 可选的网页研究密钥。
        "X-Tavily-Api-Key",
        # 用户选中的模型编号。
        "X-Model-Id",
        # 当前用户编号，用来区分会话和自选股。
        "X-User-Id",
        # 生产环境用来核对这个用户编号是不是本人。
        "X-Clerk-Session-Token",
    ],
)

# 第 13 阶段。每个 HTTP 响应补上安全头。WebSocket 不走这里。
@app.middleware("http")
async def security_headers(request: Request, call_next):
    # 先让路由处理。
    response = await call_next(request)
    # 不让浏览器猜内容类型。
    response.headers["X-Content-Type-Options"] = "nosniff"
    # 不允许被嵌进别的网页。
    response.headers["X-Frame-Options"] = "DENY"
    # 跳转时少带路径。
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # 返回。
    return response


# 第 7 阶段。缺用户或密钥时的 ValueError 变成 422，而不是 500。
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    # JSON。
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# 把健康检查路由登记进应用。登记之后，GET /health 才会进入 health()。
app.include_router(health_router)
# 第 5 阶段。挂上之后，GET /stock/{ticker}/chart 和 POST /stock/quotes 才能访问。
app.include_router(chart_router)
# 第 7 阶段。模型列表和密钥检查。
app.include_router(models_router)
# 第 9 阶段。会话。
app.include_router(sessions_router)
# 第 9 阶段。聊天。
app.include_router(chat_router)
# 第 11 阶段。公司。
app.include_router(company_router)
# 第 12 阶段。自选。
app.include_router(watchlist_router)
