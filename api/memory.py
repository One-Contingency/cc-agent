# 第 13 阶段。对话太长时压缩旧消息，数据库里的原文不删。

# 摘要写回数据库用后台任务，不挡住当前回答。
import asyncio

# 发给模型的两种消息。
from langchain_core.messages import AIMessage, HumanMessage

# 摘要存在 sessions.summary。
from api.db import update_session_summary
# 压缩提示词。
from agents.prompts import CONVERSATION_COMPRESSION_PROMPT

# 压缩后保留最近 6 条，大约 3 个来回。
RECENT_MESSAGES_TO_KEEP = 6


# 粗略按 4 个字符一个 token。
def estimate_tokens(messages: list) -> int:
    # 只用来决定要不要压缩。
    return sum(len(str(message.content)) for message in messages) // 4


# 只把新消息加进累计字符数，避免每轮重扫整段历史。
def estimate_tokens_incremental(history: list, prev_chars: int, prev_len: int) -> tuple[int, int, int]:
    # 历史被换成更短的列表时，旧累计已经对不上。
    if prev_len > len(history):
        # 整段重算。
        total_chars = sum(len(str(message.content)) for message in history)
        # token、字符、条数。
        return total_chars // 4, total_chars, len(history)
    # 只加新尾巴。
    added_chars = sum(len(str(message.content)) for message in history[prev_len:])
    # 新的累计字符。
    chars = prev_chars + added_chars
    # token、字符、条数。
    return chars // 4, chars, len(history)


# 把旧消息收成一条摘要，再拼上最近 6 条。
async def compress_history(session_id: str | None, conversation_history: list, llm) -> list:
    # 原样保留的尾巴。
    recent = conversation_history[-RECENT_MESSAGES_TO_KEEP:]
    # 要被摘要的头部。
    to_summarize = conversation_history[:-RECENT_MESSAGES_TO_KEEP]
    # 转成纯文本。
    lines: list[str] = []
    # 逐条。
    for message in to_summarize:
        # 正文。
        content = str(message.content)
        # 上一次的摘要再压一次。
        if content.startswith("[CONVERSATION SUMMARY]"):
            # 标成已有摘要。
            lines.append("PRIOR SUMMARY:\n" + content.replace("[CONVERSATION SUMMARY]", "").strip())
        # 用户。
        elif message.type == "human":
            # 标成用户。
            lines.append(f"USER: {content}")
        # 助手。
        else:
            # 标成助手。
            lines.append(f"ASSISTANT: {content}")
    # 填提示词。
    prompt = CONVERSATION_COMPRESSION_PROMPT.format(transcript="\n\n".join(lines))
    # 让模型写摘要。
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    # 摘要正文。
    summary_text = str(response.content)
    # 有会话才落库。匿名聊天只留在内存。
    if session_id:
        # 不等待写库完成。
        asyncio.create_task(update_session_summary(session_id, summary_text))
    # 摘要伪装成一条用户消息，方便下次继续压。
    summary_message = HumanMessage(content=f"[CONVERSATION SUMMARY]\n{summary_text}")
    # 短上下文。
    return [summary_message] + recent


# 从数据库恢复模型看得见的上下文。
def build_context_from_session(session: dict, all_messages: list[dict]) -> list:
    # 一行数据库记录变成一条模型消息。
    def to_lc(message: dict):
        # 用户。
        if message["role"] == "user":
            # 用户消息。
            return HumanMessage(content=message["content"])
        # 助手。
        return AIMessage(content=message["content"])

    # 已有摘要。
    summary = session.get("summary") if session else None
    # 消息比保留条数多，就用摘要加最近几条。
    if summary and len(all_messages) > RECENT_MESSAGES_TO_KEEP:
        # 最近原文。
        recent_raw = all_messages[-RECENT_MESSAGES_TO_KEEP:]
        # 摘要在前。
        return [HumanMessage(content=f"[CONVERSATION SUMMARY]\n{summary}")] + [to_lc(item) for item in recent_raw]
    # 还没长到要压缩，全部带上。
    return [to_lc(item) for item in all_messages]
