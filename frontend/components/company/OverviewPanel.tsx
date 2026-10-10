"use client";
// 上一行必须在第一行。概览在浏览器里请求。

// 第 11 阶段。公司介绍、价格和大盘。不调用模型。
import { useEffect, useState } from "react";
// 请求。
import { getProfile } from "../../lib/api";
// 密钥。
import { useApiKeys } from "../../hooks/useApiKeys";
// 用户。
import { useUserId } from "../../hooks/useUserId";

// 概览。
export function OverviewPanel({ ticker }: { ticker: string }) {
  // 密钥。
  const { keys } = useApiKeys();
  // 用户。
  const { userId } = useUserId();
  // 数据。
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  // 错误。
  const [error, setError] = useState("");

  // 股票变了就重新请求。
  useEffect(() => {
    // 没有代码。
    if (!ticker) return;
    // 请求。
    getProfile(ticker, keys, userId)
      // 成功。
      .then(setProfile)
      // 失败。
      .catch(() => setError("概览加载失败"));
  }, [ticker, keys, userId]);

  // 错误。
  if (error) return <p>{error}</p>;
  // 还没到。
  if (!profile) return <p>正在加载概览</p>;
  // 介绍。
  const company = (profile.company || {}) as Record<string, string | null>;
  // 现价。
  const quote = (profile.quote || {}) as Record<string, number | null>;
  // 大盘。
  const regime = (profile.regime || {}) as Record<string, string>;
  // 展示。
  return (
    <section>
      {/* 名称。 */}
      <h2>{company.name || ticker}</h2>
      {/* 行业。 */}
      <p>{company.sector}</p>
      {/* 现价。 */}
      <p>现价 {quote.price ?? "未知"}</p>
      {/* 大盘。 */}
      <p>大盘 {regime.trend} / {regime.volatility} / {regime.phase}</p>
      {/* 简介。 */}
      <p>{company.summary}</p>
    </section>
  );
}
