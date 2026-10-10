"use client";
// 上一行必须在第一行。自选页在浏览器里请求。

// 第 12 阶段。自选页。
import { WatchlistPanel } from "../../components/watchlist/WatchlistPanel";

// 页面。
export default function WatchlistPage() {
  // 结构。
  return (
    <main>
      {/* 标题。 */}
      <h1>自选</h1>
      {/* 面板。 */}
      <WatchlistPanel />
    </main>
  );
}
