"use client";
// 上一行必须在第一行。dynamic 的 ssr: false 只能用在客户端组件里。

// 第 6 阶段 · 图表组件 3。写在 StockChartInner 之后。
import dynamic from "next/dynamic";
// 数据类型。真正的画图文件由下一行再加载。
import type { ChartResponse } from "../../types";

// 关闭服务端渲染。加载完成前先显示这句。
const StockChartInner = dynamic(() => import("./StockChartInner"), {
  // 不在服务端执行画图库。
  ssr: false,
  // 画图库还没加载完时显示的占位。
  loading: () => <p>正在绘制 K 线...</p>,
});

// 外面的页面只跟这个组件打交道。
export function StockChart({ data }: { data: ChartResponse }) {
  // 把数据原样交给内部的画图组件。
  return <StockChartInner data={data} />;
}
