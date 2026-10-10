# 第 8 阶段。按清单编号和密钥创建模型。工具模型默认关思考。

# 日志。未知编号会记一条警告。
import logging
# 思考开关。
from dataclasses import dataclass

# 清单查询。
from agents.model_registry import get_default_model, get_model

# 本文件的日志。
logger = logging.getLogger(__name__)

# 厂商对应 init_chat_model 的密钥参数名。
_PROVIDER_KEY_KWARG = {
    # Google。
    "google_genai": "google_api_key",
    # OpenAI。
    "openai": "api_key",
    # Anthropic。
    "anthropic": "anthropic_api_key",
}


# 三家通用的思考配置。
@dataclass(frozen=True)
class ThinkingConfig:
    # 是否开启。
    enabled: bool = False
    # 强度。
    level: str = "medium"


# 创建一个模型。编号不在清单里就改用默认模型。
def create_llm(model_id: str, api_key: str, thinking: ThinkingConfig | None = None):
    # 延迟导入，避免没装 langchain 时整个包在导入阶段失败。
    from langchain.chat_models import init_chat_model
    # 查清单。
    model = get_model(model_id)
    # 没有这条。
    if model is None:
        # 改用默认。
        model = get_default_model()
        # 记下替换。
        logger.warning("Model '%s' not found, falling back to '%s'", model_id, model.id)
    # 密钥参数名。
    key_name = _PROVIDER_KEY_KWARG.get(model.provider, "api_key")
    # 先放密钥和温度。
    kwargs = {key_name: api_key, "temperature": 0}
    # 只有模型支持并且调用方打开时才加思考参数。
    if thinking and thinking.enabled and model.thinking_capable:
        # Google 的写法。
        if model.provider == "google_genai":
            # 强度和思考内容。
            kwargs["thinking_level"] = thinking.level
            # 让回复里带上思考块。
            kwargs["include_thoughts"] = True
        # OpenAI 的写法。
        elif model.provider == "openai":
            # 推理强度。
            kwargs["reasoning_effort"] = thinking.level
        # Anthropic 的写法。开了思考就不要温度。
        elif model.provider == "anthropic":
            # 自适应思考。
            kwargs["thinking"] = {"type": "adaptive"}
            # 这类模型拒绝温度。
            kwargs.pop("temperature", None)
    # 用「厂商:编号」创建。
    return init_chat_model(f"{model.provider}:{model.id}", **kwargs)


# 一次做两个模型。工具模型关思考，总结模型可以开。
def create_llm_pair(model_id: str, api_key: str):
    # 工具模型。
    main_llm = create_llm(model_id, api_key)
    # 查它能不能思考。
    model = get_model(model_id)
    # 能思考就再做一个开着思考的总结模型。
    if model is not None and model.thinking_capable:
        # 强度用 medium。
        synthesizer = create_llm(model_id, api_key, thinking=ThinkingConfig(enabled=True, level="medium"))
    else:
        # 不能思考时两个是同一个。
        synthesizer = main_llm
    # 交给分析图。
    return main_llm, synthesizer
