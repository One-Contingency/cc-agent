# 第 7 阶段读请求头里的用户和密钥。第 13 阶段加上 Clerk 核对。
# 没有选中模型对应的密钥时，require_provider_key 抛 ValueError，入口把它变成 422。
# 这一版不开放匿名免费试用，缺密钥就拒绝。

# 日志。
import logging
# 环境变量是密钥的本地后备。
import os
# 装一套已经解析好的密钥。
from dataclasses import dataclass, field

# 请求头。
from fastapi import Header, HTTPException

# 登录核对。
from api.clerk_auth import is_auth_disabled, is_clerk_enabled, verify_clerk_token
# 用户编号格式。
from api.validators import USER_ID_RE

# 本文件的日志。
logger = logging.getLogger(__name__)
# 厂商名到字段名。
_PROVIDER_KEY_FIELDS = {
    # Google。
    "google_genai": "google_api_key",
    # OpenAI。
    "openai": "openai_api_key",
    # Anthropic。
    "anthropic": "anthropic_api_key",
}
# 只警告一次「没配 Clerk」。
_warned = False


# 格式不对就当成没有用户。
def _validate_user_id(raw: str | None) -> str | None:
    # 必须是字符串并且匹配正则。
    if raw and isinstance(raw, str) and USER_ID_RE.match(raw):
        # 合法。
        return raw
    # 丢掉。
    return None


# Clerk 的账号以 user_ 开头。本地 UUID 不是。
def _is_clerk_user_id(user_id: str) -> bool:
    # 前缀。
    return user_id.startswith("user_")


# 本地或关登录时信任传入的编号。生产开了 Clerk 时，UUID 不能当登录用户。
def _trusted_user_id(user_id: str | None) -> str | None:
    # 关登录，或根本没配 Clerk。
    if is_auth_disabled() or not is_clerk_enabled():
        # 原样信任。本地 UUID 可以写数据库。
        return user_id
    # 只有 Clerk 编号才继续交给令牌核对。
    if user_id and _is_clerk_user_id(user_id):
        # 还要在后面核对令牌。
        return user_id
    # 无法核对的编号当成匿名。
    return None


# 匿名访客不能花服务器 .env 里的密钥。
def _env_keys_allowed(user_id: str | None) -> bool:
    # 本地开发允许。
    if is_auth_disabled() or not is_clerk_enabled():
        # 请求头没有时可以回退到环境变量。
        return True
    # 生产里只有核对过的用户可以。
    return _trusted_user_id(user_id) is not None


# 提醒当前是不是在跳过登录。
def _maybe_warn() -> None:
    # 用模块级标记。
    global _warned
    # 已经提醒过。
    if _warned:
        # 不再刷日志。
        return
    # 显式关掉。
    if is_auth_disabled():
        # 记一条。
        logger.warning("DISABLE_AUTH=true — Clerk verification is bypassed")
    # 没配。
    elif not is_clerk_enabled():
        # 本地可以，生产启动检查会另外拒绝。
        logger.warning("CLERK_SECRET_KEY not set — skipping Clerk verification")
    # 标记已提醒。
    _warned = True


# REST 上核对用户编号和令牌。失败抛 401。
def _verify_user_identity(user_id: str | None, token: str | None) -> str | None:
    # 先提醒。
    _maybe_warn()
    # 本地直接信任。
    if is_auth_disabled() or not is_clerk_enabled():
        # 返回校验过格式的编号。
        return user_id
    # 不是 Clerk 编号就当匿名。
    if not user_id or not _is_clerk_user_id(user_id):
        # 不能凭 UUID 读别人的数据。
        return None
    # Clerk 编号必须带令牌。
    if not token:
        # 401。
        raise HTTPException(status_code=401, detail="Missing Clerk session token")
    # 验签。
    verified = verify_clerk_token(token)
    # 签不对。
    if verified is None:
        # 401。
        raise HTTPException(status_code=401, detail="Invalid Clerk session token")
    # 令牌里的人和请求头不是同一个。
    if verified != user_id:
        # 401。
        raise HTTPException(status_code=401, detail="User ID does not match Clerk session")
    # 通过。
    return user_id


# 请求头优先，没有再看环境变量。
def _resolve_key(user_supplied: str | None, env_var: str, allow_env: bool) -> tuple[str | None, str | None]:
    # 浏览器带来的。
    if user_supplied:
        # 来源记成用户。
        return user_supplied, "user"
    # 允许用服务器上的。
    if allow_env:
        # 读 .env。
        env_value = os.getenv(env_var)
        # 有值。
        if env_value:
            # 来源记成环境。额度只对这种来源计数。
            return env_value, "env"
    # 都没有。
    return None, None


# 当前请求能用的密钥。
@dataclass
class ApiKeys:
    # Google。
    google_api_key: str | None
    # OpenAI。
    openai_api_key: str | None
    # Anthropic。
    anthropic_api_key: str | None
    # 网页研究。
    tavily_api_key: str | None
    # 选中的模型。
    model_id: str | None
    # 用户。匿名是 None。
    user_id: str | None = None
    # 每个厂商的密钥是用户带来的还是环境变量。
    key_sources: dict[str, str] = field(default_factory=dict)

    # 要写数据库的接口调用。没有用户就抛错，入口变成 422。
    def require_user_id(self) -> str:
        # 空。
        if not self.user_id:
            # 交给全局异常处理。
            raise ValueError("User ID required (X-User-Id header)")
        # 有。
        return self.user_id

    # 按厂商取密钥，没有就是 None。
    def get_provider_key(self, provider: str) -> str | None:
        # 字段名。
        field_name = _PROVIDER_KEY_FIELDS.get(provider)
        # 不认识的厂商。
        if field_name is None:
            # 没有密钥。
            return None
        # 取值。
        return getattr(self, field_name, None)

    # 没有密钥就抛错。
    def require_provider_key(self, provider: str) -> str:
        # 先取。
        key = self.get_provider_key(provider)
        # 没有。
        if not key:
            # 给人看的厂商名。
            raise ValueError(f"{provider.replace('_', ' ').title()} API key required")
        # 有。
        return key

    # 这次是不是在花操作员自己的密钥。
    def is_operator_paid(self, provider: str) -> bool:
        # 只有来源是 env 才计每天 100 次。
        return self.key_sources.get(provider) == "env"


# 把三个来源收成字典。
def _sources(google: str | None, openai: str | None, anthropic: str | None) -> dict[str, str]:
    # 结果。
    sources: dict[str, str] = {}
    # Google。
    if google:
        # 记下。
        sources["google_genai"] = google
    # OpenAI。
    if openai:
        # 记下。
        sources["openai"] = openai
    # Anthropic。
    if anthropic:
        # 记下。
        sources["anthropic"] = anthropic
    # 交给 ApiKeys。
    return sources


# FastAPI 依赖。路由参数写 keys: ApiKeys = Depends(get_api_keys)。
async def get_api_keys(
    # Google 头。
    x_google_api_key: str | None = Header(None),
    # OpenAI 头。
    x_openai_api_key: str | None = Header(None),
    # Anthropic 头。
    x_anthropic_api_key: str | None = Header(None),
    # 研究头。
    x_tavily_api_key: str | None = Header(None),
    # 模型头。
    x_model_id: str | None = Header(None),
    # 用户头。
    x_user_id: str | None = Header(None),
    # 登录令牌。
    x_clerk_session_token: str | None = Header(None),
) -> ApiKeys:
    # 先看格式。
    user_id = _validate_user_id(x_user_id)
    # 再核对令牌。
    user_id = _verify_user_identity(user_id, x_clerk_session_token)
    # 能不能用 .env。
    allow_env = _env_keys_allowed(user_id)
    # 四个密钥。
    google_key, google_source = _resolve_key(x_google_api_key, "GOOGLE_API_KEY", allow_env)
    # OpenAI。
    openai_key, openai_source = _resolve_key(x_openai_api_key, "OPENAI_API_KEY", allow_env)
    # Anthropic。
    anthropic_key, anthropic_source = _resolve_key(x_anthropic_api_key, "ANTHROPIC_API_KEY", allow_env)
    # Tavily 不参与模型额度，来源不用记。
    tavily_key, _tavily_source = _resolve_key(x_tavily_api_key, "TAVILY_API_KEY", allow_env)
    # 组装。
    return ApiKeys(
        # Google。
        google_api_key=google_key,
        # OpenAI。
        openai_api_key=openai_key,
        # Anthropic。
        anthropic_api_key=anthropic_key,
        # 研究。
        tavily_api_key=tavily_key,
        # 模型。头没有时用环境变量。
        model_id=x_model_id or os.getenv("DEFAULT_MODEL_ID"),
        # 用户。
        user_id=user_id,
        # 来源。
        key_sources=_sources(google_source, openai_source, anthropic_source),
    )


# WebSocket 第一帧不能带 HTTP 头，密钥放在 JSON 里。令牌核对由聊天路由另做。
def resolve_ws_keys(auth_message: dict) -> ApiKeys:
    # 格式和可信范围。
    user_id = _trusted_user_id(_validate_user_id(auth_message.get("user_id")))
    # 模型编号必须是字符串。
    raw_model = auth_message.get("model_id")
    # 不是字符串就忽略。
    model_id = raw_model if isinstance(raw_model, str) else None
    # 能不能用 .env。
    allow_env = _env_keys_allowed(user_id)
    # 四个密钥。
    google_key, google_source = _resolve_key(auth_message.get("google_api_key"), "GOOGLE_API_KEY", allow_env)
    # OpenAI。
    openai_key, openai_source = _resolve_key(auth_message.get("openai_api_key"), "OPENAI_API_KEY", allow_env)
    # Anthropic。
    anthropic_key, anthropic_source = _resolve_key(auth_message.get("anthropic_api_key"), "ANTHROPIC_API_KEY", allow_env)
    # 研究。
    tavily_key, _tavily_source = _resolve_key(auth_message.get("tavily_api_key"), "TAVILY_API_KEY", allow_env)
    # 组装。
    return ApiKeys(
        # Google。
        google_api_key=google_key,
        # OpenAI。
        openai_api_key=openai_key,
        # Anthropic。
        anthropic_api_key=anthropic_key,
        # 研究。
        tavily_api_key=tavily_key,
        # 模型。
        model_id=model_id or os.getenv("DEFAULT_MODEL_ID"),
        # 用户。
        user_id=user_id,
        # 来源。
        key_sources=_sources(google_source, openai_source, anthropic_source),
    )


# 聊天连接前核对。返回是否通过，以及给人看的原因。
def verify_ws_identity(user_id: str | None, auth_message: dict) -> tuple[bool, str | None]:
    # 提醒。
    _maybe_warn()
    # 本地总是通过。
    if is_auth_disabled() or not is_clerk_enabled():
        # 没有错误。
        return True, None
    # 匿名或本地 UUID，不占用 Clerk 数据。
    if not user_id or not _is_clerk_user_id(user_id):
        # 当匿名连接。
        return True, None
    # 令牌。
    token = auth_message.get("clerk_session_token")
    # 没带。
    if not token:
        # 拒绝。
        return False, "Missing Clerk session token"
    # 验签。
    verified = verify_clerk_token(token)
    # 失败。
    if verified is None:
        # 拒绝。
        return False, "Invalid Clerk session token"
    # 不是同一个人。
    if verified != user_id:
        # 拒绝。
        return False, "User ID does not match Clerk session"
    # 通过。
    return True, None
