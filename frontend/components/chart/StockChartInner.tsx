"use client";
// 上一行必须在第一行。lightweight-charts 会访问 window。

// 第 6 阶段 · 图表组件 2。写在 ChartControls 之后。
import { useEffect, useRef } from "react";
// 创建图表、K 线序列、成交量柱，以及颜色类型。
import { createChart, CandlestickSeries, HistogramSeries, ColorType } from "lightweight-charts";
// K 线数据的类型。
import type { ChartResponse } from "../../types";

// 接收第 5 阶段接口返回的数据。
export default function StockChartInner({ data }: { data: ChartResponse }) {
  // 图表要挂载到的 div。
  const containerRef = useRef<HTMLDivElement>(null);

  // data 变化时拆掉旧图，再画一张新图。
  useEffect(() => {
    // 容器还没出现，或没有 K 线，就不画。
    if (!containerRef.current || data.candles.length === 0) return;
    // 在这个 div 里创建一张 340 像素高的图。
    const chart = createChart(containerRef.current, {
      // 图的高度。
      height: 340,
      // 深色背景和浅色刻度文字。
      layout: { background: { type: ColorType.Solid, color: "#0d1220" }, textColor: "#94a3b8" },
    });
    // 添加 K 线序列。涨为绿色，跌为红色。
    const candles = chart.addSeries(CandlestickSeries, {
      // 阳线实体颜色。
      upColor: "#10b981",
      // 阴线实体颜色。
      downColor: "#ef4444",
      // 阳线边框。
      borderUpColor: "#10b981",
      // 阴线边框。
      borderDownColor: "#ef4444",
      // 阳线影线。
      wickUpColor: "#10b981",
      // 阴线影线。
      wickDownColor: "#ef4444",
    });
    // 把接口里的 K 线填进去。这里只取画蜡烛需要的五个字段。
    candles.setData(data.candles.map((item) => ({
      // 交易日。
      time: item.time,
      // 开盘价。
      open: item.open,
      // 最高价。
      high: item.high,
      // 最低价。
      low: item.low,
      // 收盘价。
      close: item.close,
    })));
    // 成交量用柱状图，单独放在下方的刻度上。
    const volume = chart.addSeries(HistogramSeries, { priceScaleId: "volume" });
    // 让成交量只占图表底部大约 20% 的高度。
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    // 涨的柱子偏绿，跌的柱子偏红。
    volume.setData(data.candles.map((item) => ({
      // 和 K 线同一天。
      time: item.time,
      // 当天成交量。
      value: item.volume,
      // 收盘不低于开盘就算涨。
      color: item.close >= item.open ? "#10b98188" : "#ef444488",
    })));
    // 让 K 线撑满宽度。
    chart.timeScale().fitContent();
    // 组件卸载或数据更新前，销毁这张图，避免重复叠加。
    return () => chart.remove();
  }, [data]);

  // 图表挂在这个空 div 上。
  return <div ref={containerRef} />;
}
