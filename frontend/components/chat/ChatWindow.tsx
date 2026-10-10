"use client";
// 上一行必须在第一行。输入框在浏览器里。

// 第 9 阶段。聊天框。阶段文字来自 WebSocket 事件。
import { useState } from "react";
// 一条消息。
import { ChatMessage } from "./ChatMessage";
// 密钥。
import { useApiKeys } from "../../hooks/useApiKeys";
// 连接。
import { useWebSocket } from "../../hooks/useWebSocket";
// 密钥类型。
import type { ApiKeys } from "../../types";

// 绑一只股票。先等密钥从浏览器读出来。
export function ChatWindow({ ticker }: { ticker: string }) {
  // 密钥。
  const { keys, loaded } = useApiKeys();
  // 还在读。
  if (!loaded) return <p>正在读取密钥</p>;
  // 再连接。
  return <ChatWindowReady ticker={ticker} keys={keys} />;
}

// 密钥读完再连接，避免用空密钥连上后又不再重连。
function ChatWindowReady({ ticker, keys }: { ticker: string; keys: ApiKeys }) {
  // 输入。
  const [text, setText] = useState("");
  // 连接。
  const { messages, status, sendMessage } = useWebSocket({ ticker, keys });

  // 发送。
  function handleSubmit(event: React.FormEvent) {
    // 不刷新。
    event.preventDefault();
    // 去掉空白。
    const clean = text.trim();
    // 空的或还没连上。
    if (!clean || status !== "connected") return;
    // 发送。
    sendMessage(clean);
    // 清空输入。
    setText("");
  }

  // 聊天框。
  return (
    <section>
      {/* 标题和连接状态。 */}
      <h2>聊天（{status}）</h2>
      {/* 消息。 */}
      {messages.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}
      {/* 输入。 */}
      <form onSubmit={handleSubmit}>
        {/* 问题。 */}
        <input value={text} onChange={(event) => setText(event.target.value)} placeholder="问这只股票" />
        {/* 发送。没连上时不能点。 */}
        <button type="submit" disabled={status !== "connected"}>发送</button>
      </form>
    </section>
  );
}
