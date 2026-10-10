// 第 4 阶段 · 顺序 6
// 写在 constants.ts 和 types/index.ts 之后、app/layout.tsx 之前。

// 引入 HTTP 根地址和 WebSocket 根地址。
import { API_BASE, WS_BASE } from "./constants";
// 只引入类型，编译后这行不会变成真正的运行代码。
// 第 6 阶段。同时引入 K 线的返回类型。
import type { ApiKeys, ChartResponse, HealthResponse } from "../types";

// 把已经填写的密钥变成请求头。没填的密钥不放进去。
export function keyHeaders(keys: Partial<ApiKeys>): Record<string, string> {
  // Partial 表示每个字段都可以省略。返回值是「头名称 → 头内容」。
  const headers: Record<string, string> = {};
  // 有 Google 密钥时，放进对应请求头。
  if (keys.google_api_key) headers["X-Google-Api-Key"] = keys.google_api_key;
  // 有 OpenAI 密钥时，放进对应请求头。
  if (keys.openai_api_key) headers["X-Openai-Api-Key"] = keys.openai_api_key;
  // 有 Anthropic 密钥时，放进对应请求头。
  if (keys.anthropic_api_key) headers["X-Anthropic-Api-Key"] = keys.anthropic_api_key;
  // 有研究密钥时才发送。没有的话，后端认为网页研究不可用。
  if (keys.tavily_api_key) headers["X-Tavily-Api-Key"] = keys.tavily_api_key;
  // 有选中的模型时，告诉后端用哪一个。
  if (keys.model_id) headers["X-Model-Id"] = keys.model_id;
  // 把拼好的请求头交给调用方。
  return headers;
}

// 把用户编号变成请求头。还没有用户时不发送这个头。
export function userIdHeader(userId?: string): Record<string, string> {
  // 有编号就返回只含 X-User-Id 的对象，没有就返回空对象。
  return userId ? { "X-User-Id": userId } : {};
}

// 请求存活探针。首页用它确认后端已经启动。
export async function getHealth(): Promise<HealthResponse> {
  // 向「后端根地址 + /health」发一个 GET，并等待响应。
  const res = await fetch(`${API_BASE}/health`);
  // 状态码不是成功时，抛出错误，让页面显示「后端没有连上」。
  if (!res.ok) throw new Error(`API error ${res.status}: /health`);
  // 把响应正文从 JSON 转成 HealthResponse 再交回去。
  return res.json() as Promise<HealthResponse>;
}

// 第 6 阶段。向 /stock/AAPL/chart?period=1y 要 K 线。
export async function getChart(ticker: string, period = "1y"): Promise<ChartResponse> {
  // 拼出第 5 阶段写好的地址。
  const res = await fetch(`${API_BASE}/stock/${ticker}/chart?period=${period}`);
  // 股票不存在或代码不合法时，把状态码抛出去。
  if (!res.ok) throw new Error(`API error ${res.status}: /stock/${ticker}/chart`);
  // 转成只含 candles 的对象。
  return res.json() as Promise<ChartResponse>;
}

// 建立聊天用的 WebSocket。这个地址要到第 9 阶段才存在，现在调用会连不上。
export function connectChat(
  // 股票代码，会放进连接地址，例如 AAPL。
  ticker: string,
  // 要在第一帧里交给后端的密钥，可以只填其中一部分。
  keys: Partial<ApiKeys>,
  // 当前用户编号。匿名访问时调用方可以不传。
  userId?: string,
// 返回值是一条已经开始连接的 WebSocket。
): WebSocket {
  // 拼出形如 ws://localhost:8000/ws/chat/AAPL 的地址并开始连接。
  const ws = new WebSocket(`${WS_BASE}/ws/chat/${ticker}`);
  // 连接一旦打开就执行这个函数。在此之前不能发消息。
  ws.onopen = () => {
    // 把认证对象变成 JSON 文本，作为第一条消息发出。
    ws.send(
      // 协议规定第一帧的 type 必须是 auth，不能先发用户的问题。
      JSON.stringify({
        // 标记这是认证帧。
        type: "auth",
        // 当前用户。没传 userId 时，这里是 undefined。
        user_id: userId,
        // 选中的模型编号。
        model_id: keys.model_id,
        // Google 密钥。没用这家厂商时可以是空的。
        google_api_key: keys.google_api_key,
        // OpenAI 密钥。
        openai_api_key: keys.openai_api_key,
        // Anthropic 密钥。后端只会使用和所选模型匹配的那一个。
        anthropic_api_key: keys.anthropic_api_key,
        // 可选的网页研究密钥。
        tavily_api_key: keys.tavily_api_key,
      }),
    );
  };
  // 把这条连接交给调用方，后面用它接收聊天事件。
  return ws;
}

// 第 7 阶段。密钥头加上用户头。设置页和自选都用它。
export function authHeaders(keys: Partial<ApiKeys>, userId?: string): Record<string, string> {
  // 合并两套头。
  return { ...keyHeaders(keys), ...userIdHeader(userId) };
}

// 第 7 阶段。模型列表。
export async function getModels(): Promise<{ models: import("../types").ModelInfo[] }> {
  // 公开接口。
  const res = await fetch(`${API_BASE}/models`);
  // 失败。
  if (!res.ok) throw new Error(`API error ${res.status}: /models`);
  // JSON。
  return res.json();
}

// 第 7 阶段。缺密钥时后端返回 422。
export async function checkModel(modelId: string, keys: Partial<ApiKeys>, userId?: string): Promise<void> {
  // 提交选中的模型。
  const res = await fetch(`${API_BASE}/models/check`, {
    // 方法。
    method: "POST",
    // 头。
    headers: { "Content-Type": "application/json", ...authHeaders(keys, userId) },
    // 正文。
    body: JSON.stringify({ model_id: modelId }),
  });
  // 422 或其它失败。
  if (!res.ok) {
    // 读原因。
    const body = await res.json().catch(() => ({ detail: "密钥检查失败" }));
    // 抛出给人看的句子。
    throw new Error(typeof body.detail === "string" ? body.detail : "密钥检查失败");
  }
}

// 第 9 阶段。这个用户聊过的股票。
export async function getTickers(keys: Partial<ApiKeys>, userId?: string) {
  // 请求。
  const res = await fetch(`${API_BASE}/tickers`, { headers: authHeaders(keys, userId) });
  // 失败。
  if (!res.ok) throw new Error("历史加载失败");
  // JSON。
  return res.json() as Promise<{ tickers: Array<{ ticker: string; session_count?: number }> }>;
}

// 第 11 阶段。公司概览。
export async function getProfile(ticker: string, keys: Partial<ApiKeys>, userId?: string) {
  // 请求。
  const res = await fetch(`${API_BASE}/api/company/${ticker}/profile`, { headers: authHeaders(keys, userId) });
  // 失败。
  if (!res.ok) throw new Error("概览加载失败");
  // JSON。
  return res.json() as Promise<Record<string, unknown>>;
}

// 第 11 阶段。财报 SSE。用 fetch 才能带上密钥头。
export async function streamFilings(
  // 股票。
  ticker: string,
  // 密钥和用户。
  keys: Partial<ApiKeys>,
  // 用户。
  userId: string | undefined,
  // 每来一条就回调。
  onEvent: (event: { type: string; message?: string; content?: string; section?: string }) => void,
): Promise<void> {
  // 打开流。
  const res = await fetch(`${API_BASE}/api/company/${ticker}/filings/stream`, { headers: authHeaders(keys, userId) });
  // 失败。422 会走这里。
  if (!res.ok || !res.body) {
    // 读原因。
    const body = await res.json().catch(() => ({ detail: "财报分析失败" }));
    // 抛出。
    throw new Error(typeof body.detail === "string" ? body.detail : "财报分析失败");
  }
  // 按块读。
  const reader = res.body.getReader();
  // 文本解码。
  const decoder = new TextDecoder();
  // 还没拼完的半行。
  let buffer = "";
  // 一直读到结束。
  while (true) {
    // 一块。
    const { done, value } = await reader.read();
    // 结束。
    if (done) break;
    // 接上。
    buffer += decoder.decode(value, { stream: true });
    // 按空行分事件。
    const parts = buffer.split("\n\n");
    // 最后一段可能不完整。
    buffer = parts.pop() ?? "";
    // 完整的那些。
    for (const part of parts) {
      // 找到 data 行。
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      // 没有就跳过。
      if (!line) continue;
      // 解析。
      onEvent(JSON.parse(line.slice(6)));
    }
  }
}

// 第 12 阶段。自选列表。
export async function getWatchlist(keys: Partial<ApiKeys>, userId?: string) {
  // 请求。
  const res = await fetch(`${API_BASE}/watchlist`, { headers: authHeaders(keys, userId) });
  // 失败。
  if (!res.ok) throw new Error("自选加载失败");
  // JSON。
  return res.json() as Promise<{ tickers: Array<{ ticker: string; name?: string | null; sector?: string | null }> }>;
}

// 第 12 阶段。加入自选。满 10 只时后端返回 409。
export async function addWatchlist(ticker: string, keys: Partial<ApiKeys>, userId?: string) {
  // 提交。
  const res = await fetch(`${API_BASE}/watchlist`, {
    // 方法。
    method: "POST",
    // 头。
    headers: { "Content-Type": "application/json", ...authHeaders(keys, userId) },
    // 正文。
    body: JSON.stringify({ ticker }),
  });
  // 失败。
  if (!res.ok) {
    // 原因。
    const body = await res.json().catch(() => ({ detail: "加入失败" }));
    // 抛出。
    throw new Error(typeof body.detail === "string" ? body.detail : "加入失败");
  }
}

// 第 12 阶段。移除。
export async function removeWatchlist(ticker: string, keys: Partial<ApiKeys>, userId?: string) {
  // 删除。
  const res = await fetch(`${API_BASE}/watchlist/${ticker}`, { method: "DELETE", headers: authHeaders(keys, userId) });
  // 失败。
  if (!res.ok) throw new Error("移除失败");
}

// 第 12 阶段。生成早报。
export async function getBriefing(keys: Partial<ApiKeys>, userId?: string) {
  // 请求。可能要一两分钟。
  const res = await fetch(`${API_BASE}/watchlist/briefing`, { headers: authHeaders(keys, userId) });
  // 失败。
  if (!res.ok) {
    // 原因。
    const body = await res.json().catch(() => ({ detail: "早报失败" }));
    // 抛出。
    throw new Error(typeof body.detail === "string" ? body.detail : "早报失败");
  }
  // JSON。
  return res.json() as Promise<{ briefing: string }>;
}
