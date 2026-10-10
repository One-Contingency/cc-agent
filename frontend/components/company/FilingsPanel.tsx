"use client";
// 上一行必须在第一行。财报流在浏览器里读。

// 第 11 阶段。进度、元数据和风险摘要。
import { useState } from "react";
// 流。
import { streamFilings } from "../../lib/api";
// 密钥。
import { useApiKeys } from "../../hooks/useApiKeys";
// 用户。
import { useUserId } from "../../hooks/useUserId";

// 财报。
export function FilingsPanel({ ticker }: { ticker: string }) {
  // 密钥。
  const { keys } = useApiKeys();
  // 用户。
  const { userId } = useUserId();
  // 进度。
  const [progress, setProgress] = useState("");
  // 摘要。
  const [content, setContent] = useState("");
  // 错误。
  const [error, setError] = useState("");

  // 点击后才分析，避免一进页面就花钱。
  async function start() {
    // 清掉上次。
    setError("");
    // 清掉摘要。
    setContent("");
    // 读流。
    try {
      // 逐条。
      await streamFilings(ticker, keys, userId, (event) => {
        // 进度。
        if (event.type === "progress") setProgress(event.message || "");
        // 章节。
        if (event.type === "section") setContent(event.content || "");
        // 错误事件。
        if (event.type === "error") setError(event.message || "分析失败");
        // 完成。
        if (event.type === "complete") setProgress("完成");
      });
    } catch (err) {
      // 请求本身失败，例如缺密钥。
      setError(err instanceof Error ? err.message : "分析失败");
    }
  }

  // 面板。
  return (
    <section>
      {/* 标题。 */}
      <h2>财报</h2>
      {/* 开始。 */}
      <button type="button" onClick={start}>分析最新 10-K 风险</button>
      {/* 进度。 */}
      {progress ? <p>{progress}</p> : null}
      {/* 错误。 */}
      {error ? <p>{error}</p> : null}
      {/* 摘要。 */}
      {content ? <p>{content}</p> : null}
    </section>
  );
}
