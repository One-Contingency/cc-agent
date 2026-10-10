"use client";
// 上一行必须在第一行。要在浏览器里请求模型列表。

// 第 8 阶段。设置页的下拉框用这个列表。
import { useEffect, useState } from "react";
// 请求。
import { getModels } from "../lib/api";
// 类型。
import type { ModelInfo } from "../types";

// 读清单。
export function useModels() {
  // 列表。
  const [models, setModels] = useState<ModelInfo[]>([]);
  // 错误。
  const [error, setError] = useState("");
  // 挂上之后请求。
  useEffect(() => {
    // 请求。
    getModels()
      // 成功。
      .then((body) => setModels(body.models))
      // 失败。
      .catch(() => setError("模型列表加载失败"));
  }, []);
  // 交给页面。
  return { models, error };
}
