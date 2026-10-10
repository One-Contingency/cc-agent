"use client";
// 上一行必须在第一行。设置页要写浏览器里的密钥。

// 第 7 阶段。填写密钥和模型。服务器不保存这些密钥。
import { useState } from "react";
// 检查缺密钥会不会被拒绝。
import { checkModel } from "../../lib/api";
// 密钥。
import { useApiKeys } from "../../hooks/useApiKeys";
// 模型。
import { useModels } from "../../hooks/useModels";
// 用户。
import { useUserId } from "../../hooks/useUserId";
// 类型。
import type { ApiKeys } from "../../types";

// 设置页。
export default function SettingsPage() {
  // 已保存的密钥。
  const { keys, setKeys, loaded } = useApiKeys();
  // 清单。
  const { models, error: modelError } = useModels();
  // 用户。
  const { userId } = useUserId();
  // 表单草稿。还没读完时用已保存的。
  const [draft, setDraft] = useState<ApiKeys | null>(null);
  // 保存结果。
  const [message, setMessage] = useState("");
  // 实际编辑的那一套。
  const form = draft ?? keys;

  // 改一个字段。
  function update(field: keyof ApiKeys, value: string) {
    // 写回草稿。
    setDraft({ ...form, [field]: value });
  }

  // 保存并让后端检查密钥。
  async function handleSave(event: React.FormEvent) {
    // 不刷新。
    event.preventDefault();
    // 先存到浏览器。
    setKeys(form);
    // 再问后端。
    try {
      // 缺密钥会抛错。
      await checkModel(form.model_id, form, userId);
      // 通过。
      setMessage("已保存，密钥可用。");
    } catch (err) {
      // 422 的原因。
      setMessage(err instanceof Error ? err.message : "保存失败");
    }
  }

  // 还没读完。
  if (!loaded) return <main><p>正在读取本机密钥</p></main>;

  // 表单。
  return (
    <main>
      {/* 标题。 */}
      <h1>设置</h1>
      {/* 模型列表失败时显示。 */}
      {modelError ? <p>{modelError}</p> : null}
      {/* 提交。 */}
      <form onSubmit={handleSave}>
        {/* 模型。 */}
        <label>
          模型
          <select value={form.model_id} onChange={(event) => update("model_id", event.target.value)}>
            {/* 没选。 */}
            <option value="">默认</option>
            {/* 清单。 */}
            {models.map((model) => (
              <option key={model.id} value={model.id}>{model.display_name}</option>
            ))}
          </select>
        </label>
        {/* Google。 */}
        <label>
          Google 密钥
          <input value={form.google_api_key} onChange={(event) => update("google_api_key", event.target.value)} />
        </label>
        {/* OpenAI。 */}
        <label>
          OpenAI 密钥
          <input value={form.openai_api_key} onChange={(event) => update("openai_api_key", event.target.value)} />
        </label>
        {/* Anthropic。 */}
        <label>
          Anthropic 密钥
          <input value={form.anthropic_api_key} onChange={(event) => update("anthropic_api_key", event.target.value)} />
        </label>
        {/* 研究。 */}
        <label>
          Tavily 密钥
          <input value={form.tavily_api_key} onChange={(event) => update("tavily_api_key", event.target.value)} />
        </label>
        {/* 保存。 */}
        <button type="submit">保存</button>
      </form>
      {/* 结果。 */}
      {message ? <p>{message}</p> : null}
    </main>
  );
}
