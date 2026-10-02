'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import type { Locale } from '@/lib/i18n';
import { storyTranslator } from '@/lib/story-i18n';

export type ClipConfig = { clip_mode?: 'static' | 'jimeng'; clip_video_prompt?: string };

export default function ClipSettings({ config, projectId, disabled, onChange, locale = 'zh' }: {
  config: ClipConfig; projectId?: string | null; disabled: boolean; onChange: (config: ClipConfig) => void;
  locale?: Locale;
}) {
  const t = storyTranslator(locale);
  const [mode, setMode] = useState<'static' | 'jimeng'>(config.clip_mode || 'static');
  const [prompt, setPrompt] = useState(config.clip_video_prompt || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setMode(config.clip_mode || 'static'); setPrompt(config.clip_video_prompt || ''); }, [config.clip_mode, config.clip_video_prompt]);
  const changed = mode !== (config.clip_mode || 'static') || prompt !== (config.clip_video_prompt || '');
  return <section className="space-y-2 rounded border p-3">
    <label className="flex items-center gap-3 text-sm">{t("视频段生成方式")}{' '}<select className="rounded border bg-white p-2 text-slate-900" value={mode} disabled={disabled || busy} onChange={e => setMode(e.target.value as 'static' | 'jimeng')}>
        <option value="static">{t("静态图片＋配音")}</option><option value="jimeng">{t("即梦首帧视频＋配音")}</option>
      </select>
    </label>
    {mode === 'jimeng' && <>
      <p className="text-xs text-slate-500">{t("按配音时长生成 5 秒或 10 秒视频，长配音由多个子段接续。使用现有即梦凭据，图生视频会产生接口调用费用。")}</p>
      <textarea aria-label={t("视频运动提示词")} className="w-full rounded border bg-white p-2 text-sm text-slate-900" maxLength={800} value={prompt} disabled={disabled || busy} onChange={e => setPrompt(e.target.value)} placeholder={t("视频运动提示词（可选，留空根据分镜生成）")} />
    </>}
    <Button size="sm" variant="outline" disabled={disabled || busy || !changed} onClick={async () => {
      setBusy(true); setError('');
      const next = { clip_mode: mode, clip_video_prompt: prompt };
      try {
        if (projectId) {
          const response = await fetch(`/api/story/${projectId}/clip-config`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next) });
          const data = await response.json();
          if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
        }
        onChange(next);
      } catch (error) { setError(error instanceof Error ? error.message : String(error)); }
      finally { setBusy(false); }
    }}>{busy ? t("保存中…") : t("应用视频段设置")}</Button>
    {changed && <p className="text-xs text-amber-700">{t("请先应用设置，再生成或重建视频段。")}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </section>;
}
