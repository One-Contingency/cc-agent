"use client";
// 上一行必须在第一行。历史要从浏览器请求。

// 第 9 阶段。这个用户聊过哪些股票。
import { useEffect, useState } from "react";
// 链接。
import Link from "next/link";
// 请求。
import { getTickers } from "../../lib/api";
// 密钥。
import { useApiKeys } from "../../hooks/useApiKeys";
// 用户。
import { useUserId } from "../../hooks/useUserId";

// 历史页。
export default function HistoryPage() {
  // 密钥。
  const { keys, loaded } = useApiKeys();
  // 用户。
  const { userId } = useUserId();
  // 列表。
  const [tickers, setTickers] = useState<Array<{ ticker: string }>>([]);
  // 错误。
  const [error, setError] = useState("");

  // 用户准备好再请求。
  useEffect(() => {
    // 还没读完。
    if (!loaded || !userId) return;
    // 请求。
    getTickers(keys, userId)
      // 成功。
      .then((body) => setTickers(body.tickers))
      // 失败。
      .catch(() => setError("历史加载失败"));
  }, [loaded, userId, keys]);

  // 页面。
  return (
    <main>
      {/* 标题。 */}
      <h1>历史</h1>
      {/* 错误。 */}
      {error ? <p>{error}</p> : null}
      {/* 空。 */}
      {!error && tickers.length === 0 ? <p>还没有聊过。</p> : null}
      {/* 列表。 */}
      <ul>
        {tickers.map((item) => (
          <li key={item.ticker}>
            {/* 进公司页。 */}
            <Link href={`/company/${item.ticker}`}>{item.ticker}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
