"use client";
// 上一行必须在第一行。这个页面要在浏览器里请求 K 线。

// 第 6 阶段 · 公司页。写在图表组件之后，本阶段最后一个文件。
import { useEffect, useState } from "react";
// 从地址 /company/AAPL 里取出 AAPL。
import { useParams } from "next/navigation";
// 周期按钮。
import { ChartControls } from "../../../components/chart/ChartControls";
// K 线图。
import { StockChart } from "../../../components/chart/StockChart";
// 第 9 阶段。聊天。
import { ChatWindow } from "../../../components/chat/ChatWindow";
// 第 11 阶段。概览。
import { OverviewPanel } from "../../../components/company/OverviewPanel";
// 第 11 阶段。财报。
import { FilingsPanel } from "../../../components/company/FilingsPanel";
// 取 K 线的函数。
import { getChart } from "../../../lib/api";
// 按钮文字和接口参数的对应关系。
import { PERIOD_MAP, type Period } from "../../../lib/constants";
// K 线响应的类型。
import type { ChartResponse } from "../../../types";

// 公司页。这一阶段只有标题、周期和 K 线。
export default function CompanyPage() {
  // 地址里的 ticker 可能是字符串。
  const params = useParams<{ ticker: string }>();
  // 统一转成大写。地址里没有时用空字符串。
  const ticker = (params.ticker ?? "").toUpperCase();
  // 当前周期，默认一年。
  const [period, setPeriod] = useState<Period>("1Y");
  // 接口返回的 K 线。还没返回时是 null。
  const [data, setData] = useState<ChartResponse | null>(null);
  // 请求失败时的提示。
  const [error, setError] = useState("");

  // ticker 或周期变化时重新请求。
  useEffect(() => {
    // 没有代码就不请求。
    if (!ticker) return;
    // 开始新请求前清掉上一次的错误。
    setError("");
    // period 用按钮文字，接口要的是 1y 这种值，所以先查表。
    getChart(ticker, PERIOD_MAP[period])
      // 成功后把 K 线存进状态，页面就会画出图。
      .then((result) => setData(result))
      // 失败时显示这句，不把上一张图留在错误状态下。
      .catch(() => {
        // 清掉旧图，避免失败后还显示上一只股票。
        setData(null);
        // 显示失败原因。
        setError("K 线加载失败");
      });
  }, [ticker, period]);

  // 公司页结构。
  return (
    <main>
      {/* 显示当前股票代码。 */}
      <h1>{ticker}</h1>
      {/* 切换周期后，上面的 effect 会重新请求。 */}
      <ChartControls period={period} onPeriodChange={setPeriod} />
      {/* 失败时显示原因。 */}
      {error ? <p>{error}</p> : null}
      {/* 数据到了才画图。第 6 阶段的 K 线留在这里。 */}
      {data ? <StockChart data={data} /> : null}
      {/* 第 11 阶段。概览。 */}
      <OverviewPanel ticker={ticker} />
      {/* 第 11 阶段。财报。 */}
      <FilingsPanel ticker={ticker} />
      {/* 第 9 阶段。聊天框，里面会显示分析阶段。 */}
      <ChatWindow ticker={ticker} />
    </main>
  );
}
