"use client";
// 上一行必须在第一行。按钮点击发生在浏览器里。

// 第 6 阶段 · 图表组件 1。写在改完 constants.ts 之后。
import { PERIODS, type Period } from "../../lib/constants";

// 父组件传进来的当前周期，以及周期改变时要调用的函数。
export function ChartControls({
  period,
  onPeriodChange,
}: {
  // 当前选中的周期，例如 1Y。
  period: Period;
  // 用户点了另一个周期时通知父组件。
  onPeriodChange: (next: Period) => void;
}) {
  // 五个周期按钮排成一行。
  return (
    <div>
      {/* 五个周期各一个按钮。 */}
      {PERIODS.map((item) => (
        <button
          // 用周期文字做列表键。
          key={item}
          // 点击后把这个周期交给父组件。
          onClick={() => onPeriodChange(item)}
          // 选中的按钮禁用，避免重复请求。
          disabled={item === period}
        >
          {/* 按钮上的文字就是 1W、1M 这类周期。 */}
          {item}
        </button>
      ))}
    </div>
  );
}
