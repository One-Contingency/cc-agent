"use client";
// 上一行必须在第一行。密钥只放在浏览器里。

// 第 7 阶段。读写 localStorage 里的密钥。
import { useEffect, useState } from "react";
// 类型。
import type { ApiKeys } from "../types";

// 存储键。
const STORAGE_KEY = "analyst_agent_keys";

// 全空的一套。
const EMPTY: ApiKeys = {
  // Google。
  google_api_key: "",
  // OpenAI。
  openai_api_key: "",
  // Anthropic。
  anthropic_api_key: "",
  // SEC 联系人留在服务器 .env，这里的字段只是类型里有。
  sec_header: "",
  // 研究。
  tavily_api_key: "",
  // 模型。
  model_id: "",
};

// 读密钥。
export function useApiKeys() {
  // 当前一套。
  const [keys, setKeysState] = useState<ApiKeys>(EMPTY);
  // 是否已经从浏览器读过。
  const [loaded, setLoaded] = useState(false);
  // 挂上之后读。
  useEffect(() => {
    // 解析失败就用空的。
    try {
      // 原文。
      const raw = localStorage.getItem(STORAGE_KEY);
      // 有内容。
      if (raw) {
        // 合并，避免旧数据缺字段。
        setKeysState({ ...EMPTY, ...(JSON.parse(raw) as Partial<ApiKeys>) });
      }
    } catch {
      // 忽略坏数据。
    }
    // 标记读完。
    setLoaded(true);
  }, []);
  // 保存。
  function setKeys(next: ApiKeys) {
    // 更新页面。
    setKeysState(next);
    // 写入浏览器。服务器不保存密钥。
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }
  // 交给页面。
  return { keys, setKeys, loaded };
}
