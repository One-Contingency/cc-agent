"use client";
// 上一行必须在第一行。消息要在浏览器里渲染。

// 第 9 阶段。一条聊天，包含阶段、思考和正文。
import type { StreamingMessage } from "../../types";

// 组件。
export function ChatMessage({ message }: { message: StreamingMessage }) {
  // 一条。
  return (
    <article>
      {/* 谁说的。 */}
      <strong>{message.role === "user" ? "我" : "分析"}</strong>
      {/* 当前阶段。 */}
      {message.status ? <p>{message.status}</p> : null}
      {/* 思考。 */}
      {message.thinking ? <p>思考：{message.thinking}</p> : null}
      {/* 正文。 */}
      <p>{message.content}</p>
    </article>
  );
}
