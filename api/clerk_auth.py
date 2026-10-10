# 第 13 阶段。用 Clerk 公布的公钥核对登录令牌，取出里面的用户编号。

# 日志。失败原因不包含令牌本身。
import logging
# 读开关和签发地址。
import os
# 公钥缓存的过期时间。
import time
# 解码后的声明是字典。
from typing import Any

# 拉取公钥失败时认这个异常。
import httpx
# 校验签名和过期时间。
import jwt
# 按令牌头里的 kid 找公钥。
from jwt import PyJWKClient

# 本文件的日志。
logger = logging.getLogger(__name__)
# 公钥大约每 10 分钟换一次缓存。
_JWKS_TTL_SECONDS = 10 * 60
# 地址到「取到的时间、客户端」的缓存。
_jwks_cache: dict[str, tuple[float, PyJWKClient]] = {}


# 配了密钥才启用核对。
def is_clerk_enabled() -> bool:
    # 空字符串当成没配。
    return bool(os.getenv("CLERK_SECRET_KEY"))


# 本地可以关掉登录。
def is_auth_disabled() -> bool:
    # 这几个写法都算打开。
    return (os.getenv("DISABLE_AUTH") or "").lower() in ("1", "true", "yes")


# 签发方地址，末尾不留斜杠。
def _issuer() -> str | None:
    # 读环境变量。
    issuer = os.getenv("CLERK_ISSUER_URL")
    # 没配就无法核对。
    if not issuer:
        # 调用方会拒绝。
        return None
    # 去掉末尾斜杠，避免拼出来双斜杠。
    return issuer.rstrip("/")


# 公钥地址。可以单独覆盖。
def _jwks_url() -> str | None:
    # 显式地址优先。
    override = os.getenv("CLERK_JWKS_URL")
    # 配了就用它。
    if override:
        # 不再拼接。
        return override
    # 否则用签发方。
    issuer = _issuer()
    # 两者都没有。
    if not issuer:
        # 无法核对。
        return None
    # Clerk 的默认公钥路径。
    return f"{issuer}/.well-known/jwks.json"


# 同一地址的公钥客户端复用 10 分钟。
def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    # 看缓存。
    cached = _jwks_cache.get(jwks_url)
    # 当前时间。
    now = time.time()
    # 还没过期就继续用。
    if cached and (now - cached[0]) < _JWKS_TTL_SECONDS:
        # 返回旧客户端。
        return cached[1]
    # 新建一个会自己缓存密钥的客户端。
    client = PyJWKClient(jwks_url, cache_keys=True, lifespan=_JWKS_TTL_SECONDS)
    # 记下取到的时间。
    _jwks_cache[jwks_url] = (now, client)
    # 交给核对。
    return client


# 核对通过时返回 sub，失败返回 None。
def verify_clerk_token(token: str) -> str | None:
    # 空的或不是字符串。
    if not token or not isinstance(token, str):
        # 当失败。
        return None
    # 签发方。
    issuer = _issuer()
    # 公钥地址。
    jwks_url = _jwks_url()
    # 缺配置。
    if not issuer or not jwks_url:
        # 记一条警告，不写令牌。
        logger.warning("Clerk verification requested but CLERK_ISSUER_URL is not set")
        # 无法核对。
        return None
    # 验签。
    try:
        # 取客户端。
        client = _get_jwk_client(jwks_url)
        # 按 kid 找公钥。
        signing_key = client.get_signing_key_from_jwt(token)
        # 只接受 RS256，并要求过期、签发方和用户编号。
        payload: dict[str, Any] = jwt.decode(
            # 令牌原文。
            token,
            # 公钥。
            signing_key.key,
            # 算法。
            algorithms=["RS256"],
            # 必须和配置的签发方一致。
            issuer=issuer,
            # 缺这三项就失败。
            options={"require": ["exp", "iss", "sub"]},
        )
    # 过期。
    except jwt.ExpiredSignatureError:
        # 记原因。
        logger.warning("Clerk token verification failed: expired")
        # 当失败。
        return None
    # 签发方不对。
    except jwt.InvalidIssuerError:
        # 记原因。
        logger.warning("Clerk token verification failed: issuer mismatch")
        # 当失败。
        return None
    # 签名不对。
    except jwt.InvalidSignatureError:
        # 记原因。
        logger.warning("Clerk token verification failed: bad signature")
        # 当失败。
        return None
    # 其它令牌错误。
    except jwt.PyJWTError as exc:
        # 只记异常类型。
        logger.warning("Clerk token verification failed: %s", type(exc).__name__)
        # 当失败。
        return None
    # 公钥下载失败。
    except httpx.HTTPError as exc:
        # 只记异常类型。
        logger.warning("Clerk JWKS fetch failed: %s", type(exc).__name__)
        # 当失败。
        return None
    # 取出用户编号。
    sub = payload.get("sub")
    # 不是非空字符串。
    if not isinstance(sub, str) or not sub:
        # 记原因。
        logger.warning("Clerk token verification failed: missing sub")
        # 当失败。
        return None
    # 核对通过。
    return sub
