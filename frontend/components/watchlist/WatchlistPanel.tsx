"use client";
// 上一行必须在第一行。自选要在浏览器里改。

// 第 12 阶段。添加、删除和早报。最多 10 只。
import { useEffect, useState } from "react";
// 请求。
import { addWatchlist, getBriefing, getWatchlist, removeWatchlist } from "../../lib/api";
// 密钥。
import { useApiKeys } from "../../hooks/useApiKeys";
// 用户。
import { useUserId } from "../../hooks/useUserId";

// 自选面板。
export function WatchlistPanel() {
  // 密钥。
  const { keys, loaded } = useApiKeys();
  // 用户。
  const { userId } = useUserId();
  // 列表。
  const [tickers, setTickers] = useState<Array<{ ticker: string; name?: string | null }>>([]);
  // 输入。
  const [ticker, setTicker] = useState("");
  // 早报。
  const [briefing, setBriefing] = useState("");
  // 错误。
  const [error, setError] = useState("");

  // 重新加载。
  async function reload() {
    // 请求。
    const body = await getWatchlist(keys, userId);
    // 写入。
    setTickers(body.tickers);
  }

  // 用户准备好再加载。
  useEffect(() => {
    // 还没好。
    if (!loaded || !userId) return;
    // 加载。失败就显示原因。
    reload().catch(() => setError("自选加载失败"));
    // keys 变化时也刷新。
  }, [loaded, userId, keys]);

  // 添加。
  async function handleAdd(event: React.FormEvent) {
    // 不刷新。
    event.preventDefault();
    // 清错误。
    setError("");
    // 提交。
    try {
      // 加入。满 10 只会抛 409 的原因。
      await addWatchlist(ticker, keys, userId);
      // 清空输入。
      setTicker("");
      // 刷新。
      await reload();
    } catch (err) {
      // 原因。
      setError(err instanceof Error ? err.message : "加入失败");
    }
  }

  // 早报。
  async function handleBriefing() {
    // 清错误。
    setError("");
    // 请求。
    try {
      // 生成。
      const body = await getBriefing(keys, userId);
      // 正文。
      setBriefing(body.briefing);
    } catch (err) {
      // 原因。
      setError(err instanceof Error ? err.message : "早报失败");
    }
  }

  // 面板。
  return (
    <section>
      {/* 添加。 */}
      <form onSubmit={handleAdd}>
        {/* 代码。 */}
        <input value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="例如 AAPL" />
        {/* 按钮。 */}
        <button type="submit">加入自选</button>
      </form>
      {/* 错误。 */}
      {error ? <p>{error}</p> : null}
      {/* 列表。 */}
      <ul>
        {tickers.map((item) => (
          <li key={item.ticker}>
            {/* 代码和名称。 */}
            {item.ticker} {item.name || ""}
            {/* 移除。 */}
            <button type="button" onClick={() => removeWatchlist(item.ticker, keys, userId).then(reload)}>移除</button>
          </li>
        ))}
      </ul>
      {/* 早报。 */}
      <button type="button" onClick={handleBriefing}>生成早报</button>
      {/* 正文。 */}
      {briefing ? <pre>{briefing}</pre> : null}
    </section>
  );
}
