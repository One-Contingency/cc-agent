// 第 4 阶段 · 顺序 5
// 写在 types/index.ts 之后、lib/api.ts 之前。api.ts 从这里取地址。

// 导出后端的 HTTP 根地址。首页请求 /health 时拼在这个地址后面。
export const API_BASE =
  // 优先使用环境变量 NEXT_PUBLIC_API_URL。没设置时用本机 8000 端口。
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 导出 WebSocket 根地址。聊天连接用它，不另开一个端口。
export const WS_BASE =
  // 只替换开头的 http：http 变成 ws，https 变成 wss。
  API_BASE.replace(/^http/, "ws");

// 第 6 阶段。按钮上显示的五个周期。
export const PERIODS = ["1W", "1M", "3M", "6M", "1Y"] as const;
// 从上面那个数组推出的类型，只能是这五个字符串之一。
export type Period = (typeof PERIODS)[number];

// 第 6 阶段。按钮文字对应第 5 阶段接口接受的 period。
export const PERIOD_MAP: Record<Period, string> = {
  // 近一周。
  "1W": "1w",
  // 近一月。
  "1M": "1mo",
  // 近三月。
  "3M": "3mo",
  // 近六月。
  "6M": "6mo",
  // 近一年。
  "1Y": "1y",
};
