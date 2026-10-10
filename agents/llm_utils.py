# 第 8 阶段。把模型回复拆成正文和思考。

# 用数据类装两段文字。
from dataclasses import dataclass


# 拆开后的结果。
@dataclass(frozen=True)
class LLMResponse:
    # 给用户看的正文。
    text: str
    # 思考过程。没有时是空字符串。
    thinking: str


# 兼容普通字符串和 Gemini 的分块内容。
def parse_llm_response(response) -> LLMResponse:
    # 有 content 属性就取出它，否则把参数本身当内容。
    content = response.content if hasattr(response, "content") else response
    # 普通字符串没有思考。
    if isinstance(content, str):
        # 正文就是整段，思考为空。
        return LLMResponse(text=content, thinking="")
    # 分块列表。
    if isinstance(content, list):
        # 正文片段。
        text_parts: list[str] = []
        # 思考片段。
        thinking_parts: list[str] = []
        # 逐块看类型。
        for block in content:
            # 不是字典就跳过。
            if not isinstance(block, dict):
                # 无法区分正文和思考。
                continue
            # 块类型。
            block_type = block.get("type", "")
            # 正文块。
            if block_type == "text" and block.get("text"):
                # 接上正文。
                text_parts.append(block["text"])
            # 思考块。
            elif block_type in ("thinking", "reasoning") and block.get(block_type):
                # 接上思考。
                thinking_parts.append(block[block_type])
        # 拼成两段。
        return LLMResponse(text="".join(text_parts), thinking="\n\n".join(thinking_parts))
    # 其它类型转成字符串。
    return LLMResponse(text=str(content), thinking="")


# 只要正文。
def extract_text(response) -> str:
    # 丢掉思考。
    return parse_llm_response(response).text
