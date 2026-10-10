"use client";
// 上一行必须留在第一行。下面要用路由和输入框状态。

// 第 6 阶段。用来跳转到 /company/AAPL。
import { useRouter } from "next/navigation";
// 第 6 阶段。记住输入框里的文字和错误提示。
import { useState } from "react";

// 第 6 阶段。首页改成输入股票代码。第 4 阶段的健康检查页到这里被替换。
export default function HomePage() {
  // 跳转函数。
  const router = useRouter();
  // 输入框当前的文字。
  const [ticker, setTicker] = useState("");
  // 格式不对时显示的提示。空字符串表示没有错误。
  const [error, setError] = useState("");

  // 提交表单时检查代码，再跳转。
  function handleSubmit(event: React.FormEvent) {
    // 阻止浏览器刷新页面。
    event.preventDefault();
    // 去掉空格并转成大写。
    const clean = ticker.trim().toUpperCase();
    // 没填就提示。
    if (!clean) {
      // 把错误写到页面上。
      setError("请输入股票代码");
      // 不再继续跳转。
      return;
    }
    // 只允许字母、数字、点和连字符，最长 10 位。和后端的正则一致。
    if (!/^[A-Z0-9.\-]{1,10}$/.test(clean)) {
      // 格式不对时停在首页。
      setError("股票代码格式不对");
      return;
    }
    // 进入这只股票的公司页。
    router.push(`/company/${clean}`);
  }

  // 首页结构：标题、输入框、错误提示。
  return (
    <main>
      {/* 页面标题。 */}
      <h1>Analyst Agent</h1>
      {/* 提交时走 handleSubmit。 */}
      <form onSubmit={handleSubmit}>
        {/* 受控输入框。每次按键都写回 ticker。 */}
        <input
          // 输入框当前显示的文字。
          value={ticker}
          // 用户输入时更新 ticker。
          onChange={(event) => setTicker(event.target.value)}
          // 没有输入时显示的例子。
          placeholder="例如 AAPL"
        />
        {/* 提交按钮。 */}
        <button type="submit">查看</button>
      </form>
      {/* 有错误时才显示这句。 */}
      {error ? <p>{error}</p> : null}
      {/* 第 7 阶段。去设置密钥。 */}
      <p><a href="/settings">设置密钥</a></p>
      {/* 第 9 阶段。历史。 */}
      <p><a href="/history">历史</a></p>
      {/* 第 12 阶段。自选。 */}
      <p><a href="/watchlist">自选</a></p>
    </main>
  );
}
