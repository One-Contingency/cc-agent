// 第 4 阶段 · 顺序 4
// 写在 tsconfig.json 之后、lib/constants.ts 之前。api.ts 会引用这里的类型。

// 描述浏览器里保存的一套密钥。服务端不把这些值写入数据库。
export interface ApiKeys {
  // Google Gemini 的密钥，对应请求头 X-Google-Api-Key。
  google_api_key: string;
  // OpenAI 的密钥，对应请求头 X-Openai-Api-Key。
  openai_api_key: string;
  // Anthropic 的密钥，对应请求头 X-Anthropic-Api-Key。
  anthropic_api_key: string;
  // 访问 SEC 时使用的「姓名 邮箱」。
  sec_header: string;
  // 网页研究用的密钥。这一步可以空着。
  tavily_api_key: string;
  // 设置页选中的模型编号，对应请求头 X-Model-Id。
  model_id: string;
}

// 描述 GET /health 返回的 JSON。
export interface HealthResponse {
  // 进程正常时，这个字段的值是 healthy。
  status: string;
}

// 第 6 阶段。一根 K 线。time 是 YYYY-MM-DD。
export interface Candle {
  // 交易日。
  time: string;
  // 开盘价。
  open: number;
  // 最高价。
  high: number;
  // 最低价。
  low: number;
  // 收盘价。
  close: number;
  // 成交量。
  volume: number;
}

// 第 6 阶段。GET /stock/{ticker}/chart 的返回。
export interface ChartResponse {
  // 按时间排列的 K 线。
  candles: Candle[];
}

// 第 7 阶段。清单里的一条模型。
export interface ModelInfo {
  // 编号。
  id: string;
  // 厂商。
  provider: string;
  // 设置页上的名字。
  display_name: string;
  // 能不能思考。
  thinking_capable: boolean;
  // 是不是默认。
  default: boolean;
}

// 第 9 阶段。聊天里的一条消息。
export interface StreamingMessage {
  // 页面上的编号。
  id: string;
  // 谁说的。
  role: "user" | "assistant";
  // 正文。
  content: string;
  // 思考。
  thinking?: string;
  // 还在往下接字。
  isStreaming?: boolean;
  // 当前阶段，例如正在拆步骤。
  status?: string;
}
