# 第 10 阶段。把 YAML 里的提示词变成可以 import 的常量。

# 读取器。
from agents.prompts.loader import load_prompts

# 导入时加载一次。
_ALL_PROMPTS = load_prompts()
# 放进模块全局，from agents.prompts import XXX 才能用。
globals().update(_ALL_PROMPTS)
# 列出全部常量名。
__all__ = list(_ALL_PROMPTS.keys())
