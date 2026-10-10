# 第 7 阶段列出模型。第 8 阶段起列表来自 get_all_models。
# POST /models/check 用来在聊天出现之前就拒绝缺密钥的请求。

# 看服务器有没有配 SEC 联系人。只返回有或没有。
import os

# 路由和依赖。
from fastapi import APIRouter, Depends

# 清单。
from agents.model_registry import get_all_models, get_default_model, get_model
# 密钥。
from api.dependencies import ApiKeys, get_api_keys

# 模型路由。
router = APIRouter(tags=["models"])


# 公开列表。不需要密钥。
@router.get("/models")
async def list_models():
    # 每条模型转成字典。
    return {"models": [item.model_dump() for item in get_all_models()]}


# 只告诉前端服务器上有哪些密钥，不返回密钥原文。
@router.get("/env-keys")
async def env_keys(keys: ApiKeys = Depends(get_api_keys)):
    # 四个布尔值。匿名时操作员密钥不会解析成功，所以这里是 false。
    return {
        # Google 是否来自环境变量。
        "google": keys.is_operator_paid("google_genai"),
        # OpenAI。
        "openai": keys.is_operator_paid("openai"),
        # Anthropic。
        "anthropic": keys.is_operator_paid("anthropic"),
        # SEC 联系人是否配置。这不是模型密钥。
        "sec_header": bool(os.getenv("SEC_HEADER")),
        # 研究密钥是否可用。
        "tavily": bool(keys.tavily_api_key),
    }


# 设置页保存前调用。缺密钥抛 ValueError，变成 422。
@router.post("/models/check")
async def check_model(body: dict, keys: ApiKeys = Depends(get_api_keys)):
    # 请求体里的编号优先，其次请求头，最后默认模型。
    requested = body.get("model_id") if isinstance(body.get("model_id"), str) else None
    # 解析。
    model = get_model(requested or keys.model_id or "") or get_default_model()
    # 没有对应密钥就抛错。
    keys.require_provider_key(model.provider)
    # 通过。
    return {"ok": True, "model_id": model.id, "provider": model.provider}
