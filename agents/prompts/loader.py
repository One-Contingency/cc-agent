# 第 10 阶段。导入时读出本目录全部 YAML 提示词。

# 找同目录的 yaml 文件。
from pathlib import Path

# YAML 解析。
import yaml


# 返回「常量名 → 模板字符串」。
def load_prompts() -> dict[str, str]:
    # 本文件所在目录。
    prompts_dir = Path(__file__).parent
    # 汇总结果。
    all_prompts: dict[str, str] = {}
    # 按文件名排序，结果稳定。
    for yaml_file in sorted(prompts_dir.glob("*.yaml")):
        # 读文本。
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        # 空文件或没有 prompts 键就跳过。
        if not data or "prompts" not in data:
            # 继续下一个文件。
            continue
        # 每个常量一条。
        for name, entry in data["prompts"].items():
            # 重名直接失败，避免悄悄覆盖。
            if name in all_prompts:
                # 指出哪个文件。
                raise ValueError(f"Duplicate prompt key '{name}' in {yaml_file.name}")
            # 模板正文。YAML 的 | 会多一个换行，去掉它。
            template = entry["template"] if isinstance(entry, dict) else str(entry)
            # 去掉末尾那一个换行。
            all_prompts[name] = template[:-1] if template.endswith("\n") else template
    # 交给 __init__。
    return all_prompts
