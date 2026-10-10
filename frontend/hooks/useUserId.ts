"use client";
// 上一行必须在第一行。这个钩子要读写浏览器里的用户编号。

// 第 7 阶段。本地用户编号。Clerk 登录留到生产环境，这里用小写 UUID。
import { useEffect, useState } from "react";

// 存在浏览器里的键。
const STORAGE_KEY = "analyst_agent_user_id";

// 生成一个小写 UUID，符合后端的用户编号格式。
function createId(): string {
  // 浏览器提供的随机编号。
  return crypto.randomUUID().toLowerCase();
}

// 读出或新建用户编号。
export function getUserId(): string {
  // 服务端渲染时没有 localStorage。
  if (typeof window === "undefined") return "";
  // 读。
  const existing = localStorage.getItem(STORAGE_KEY);
  // 已经有。
  if (existing) return existing;
  // 新建。
  const created = createId();
  // 存起来，刷新后还是同一个人。
  localStorage.setItem(STORAGE_KEY, created);
  // 返回。
  return created;
}

// 页面里用的版本。第一次渲染后再读，避免服务端和浏览器不一致。
export function useUserId() {
  // 先空着。
  const [userId, setUserId] = useState("");
  // 挂上之后再读。
  useEffect(() => {
    // 写入状态。
    setUserId(getUserId());
  }, []);
  // 交给页面。
  return { userId, loaded: userId !== "" };
}
