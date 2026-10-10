"use client";
// 上一行必须在第一行。聊天连接只存在于浏览器。

// 第 9 阶段。连接、收阶段事件、发送问题。
import { useCallback, useEffect, useRef, useState } from "react";
// 地址。
import { WS_BASE } from "../lib/constants";
// 用户。
import { getUserId } from "./useUserId";
// 类型。
import type { ApiKeys, StreamingMessage } from "../types";

// 连接状态。
export type WsStatus = "connecting" | "connected" | "disconnected" | "error";

// 参数。
interface UseWebSocketOptions {
  // 股票。
  ticker: string;
  // 密钥。
  keys: ApiKeys;
}

// 聊天钩子。
export function useWebSocket({ ticker, keys }: UseWebSocketOptions) {
  // 消息。
  const [messages, setMessages] = useState<StreamingMessage[]>([]);
  // 状态。
  const [status, setStatus] = useState<WsStatus>("disconnected");
  // 当前这条助手消息的下标。
  const streamingIdx = useRef<number | null>(null);
  // 连接。
  const wsRef = useRef<WebSocket | null>(null);
  // 密钥用 ref，避免每次按键都重连。
  const keysRef = useRef(keys);
  // 始终是最新密钥。
  keysRef.current = keys;

  // 建立连接。
  const connect = useCallback(() => {
    // 已经连着就不再连。
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;
    // 状态。
    setStatus("connecting");
    // 地址。
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${ticker}`);
    // 记住。
    wsRef.current = ws;
    // 打开后发认证。
    ws.onopen = () => {
      // 当前密钥。
      const current = keysRef.current;
      // 第一帧。
      ws.send(
        // JSON。
        JSON.stringify({
          // 认证。
          type: "auth",
          // 本地用户。
          user_id: getUserId() || undefined,
          // 模型。
          model_id: current.model_id || undefined,
          // 三家密钥。
          google_api_key: current.google_api_key || undefined,
          // OpenAI。
          openai_api_key: current.openai_api_key || undefined,
          // Anthropic。
          anthropic_api_key: current.anthropic_api_key || undefined,
          // 研究。
          tavily_api_key: current.tavily_api_key || undefined,
        }),
      );
    };
    // 收到事件。
    ws.onmessage = (event: MessageEvent) => {
      // 解析。
      const data = JSON.parse(String(event.data)) as { type: string; message?: string; node?: string; tool?: string };
      // 认证成功。
      if (data.type === "auth_success") {
        // 可以发问题了。
        setStatus("connected");
        // 结束这次处理。
        return;
      }
      // 错误。
      if (data.type === "error") {
        // 记一条助手消息。
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", content: data.message || "出错了" }]);
        // 结束。
        return;
      }
      // 阶段、工具、思考、token、回答都写到同一条助手消息上。
      setMessages((prev) => {
        // 还没有正在写的那条。
        if (streamingIdx.current === null || streamingIdx.current >= prev.length) {
          // 记下标。
          streamingIdx.current = prev.length;
          // 新的一条。
          return [
            ...prev,
            {
              // 编号。
              id: crypto.randomUUID(),
              // 助手。
              role: "assistant",
              // token 才是正文。
              content: data.type === "token" || data.type === "response" ? data.message || "" : "",
              // 思考。
              thinking: data.type === "thinking" ? data.message || "" : "",
              // 还没结束。
              isStreaming: data.type !== "response",
              // 阶段说明。
              status: data.type === "node" ? data.message : data.type === "tool" ? `工具 ${data.tool || ""}` : "",
            },
          ];
        }
        // 改已有的那条。
        return prev.map((item, index) => {
          // 不是正在写的。
          if (index !== streamingIdx.current) return item;
          // 阶段。
          if (data.type === "node") return { ...item, status: data.message || item.status };
          // 工具。
          if (data.type === "tool") return { ...item, status: `工具 ${data.tool || ""}` };
          // 思考。
          if (data.type === "thinking") return { ...item, thinking: (item.thinking || "") + (data.message || "") };
          // 增量正文。
          if (data.type === "token") return { ...item, content: item.content + (data.message || "") };
          // 完整回答覆盖正文，避免和 token 重复拼接。
          if (data.type === "response") {
            // 这条写完了。
            streamingIdx.current = null;
            // 用完整正文。
            return { ...item, content: data.message || item.content, isStreaming: false, status: "" };
          }
          // 其它。
          return item;
        });
      });
    };
    // 断开。
    ws.onclose = () => {
      // 状态。
      setStatus("disconnected");
    };
    // 错误。
    ws.onerror = () => {
      // 状态。
      setStatus("error");
    };
  }, [ticker]);

  // 股票变了就重连。
  useEffect(() => {
    // 连接。
    connect();
    // 离开页面时关掉。
    return () => {
      // 关闭。
      wsRef.current?.close();
    };
  }, [connect]);

  // 发送问题。
  function sendMessage(text: string) {
    // 没连上就不发。
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    // 先显示用户的话。
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: text }]);
    // 新的回答从头写。
    streamingIdx.current = null;
    // 发给后端。
    wsRef.current.send(JSON.stringify({ type: "query", message: text }));
  }

  // 交给聊天框。
  return { messages, status, sendMessage };
}
