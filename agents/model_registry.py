# 第 8 阶段。启动时读 models.json，成为模型清单的唯一来源。

# 读 JSON 文本。
import json
# 环境变量可以改掉默认模型。
import os
# 清单文件和本文件放在同一个目录。
from pathlib import Path

# 用冻结模型描述每一条记录。
from pydantic import BaseModel


# 清单里的一条模型。
class ModelDef(BaseModel):
    # 禁止事后改字段，避免请求之间互相踩到。
    model_config = {"frozen": True}
    # 模型编号。
    id: str
    # 厂商名。
    provider: str
    # 设置页上的名字。
    display_name: str
    # 上下文长度。
    max_context: int
    # 能不能开思考。
    thinking_capable: bool
    # 是不是默认模型。
    default: bool
    # 试用标记。这一步不启用免费试用。
    free_tier: bool = False


# 清单文件的路径。
_MODELS_PATH = Path(__file__).parent / "models.json"
# 读入原始列表。文件坏了会在导入时失败。
_raw = json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
# 用编号当键。
_MODELS: dict[str, ModelDef] = {entry["id"]: ModelDef(**entry) for entry in _raw}
# 找出所有默认模型。
_defaults = [item for item in _MODELS.values() if item.default]
# 必须正好一个。
if len(_defaults) != 1:
    # 配置错误，拒绝启动。
    raise ValueError(f"models.json must have exactly one default model, found {len(_defaults)}")
# 留下那一个。
_DEFAULT_MODEL = _defaults[0]


# 按编号查。没有就返回 None。
def get_model(model_id: str) -> ModelDef | None:
    # 字典查找。
    return _MODELS.get(model_id)


# 默认模型。DEFAULT_MODEL_ID 可以改掉 JSON 里的默认值。
def get_default_model() -> ModelDef:
    # 读环境变量。
    env_id = os.getenv("DEFAULT_MODEL_ID")
    # 配了并且清单里有，就用它。
    if env_id and env_id in _MODELS:
        # 返回覆盖后的默认模型。
        return _MODELS[env_id]
    # 否则用 JSON 里标了 default 的那条。
    return _DEFAULT_MODEL


# 全部模型，给 GET /models 用。
def get_all_models() -> list[ModelDef]:
    # 转成列表。
    return list(_MODELS.values())


# 上下文的大约四分之一。未知模型用 3 万。
def get_token_threshold(model_id: str) -> int:
    # 查这条模型。
    model = _MODELS.get(model_id)
    # 不在清单里。
    if model is None:
        # 固定兜底。
        return 30_000
    # 留出系统提示和回答的空间。
    return model.max_context // 4
