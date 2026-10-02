'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { Locale } from '@/lib/i18n';

export default function SceneStudioLink({ projectId, disabled, locale }: {
  projectId: string | null; disabled: boolean; locale: Locale;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function openStudio() {
    if (!projectId) return;
    const tab = window.open('about:blank', '_blank');
    if (tab) tab.opener = null;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/story/${encodeURIComponent(projectId)}/scene-studio`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
      const url = new URL(process.env.NEXT_PUBLIC_SCENE_STUDIO_URL || `${window.location.protocol}//${window.location.hostname}:7200/`);
      url.searchParams.set('project_path', data.project_path);
      url.searchParams.set('locale', locale);
      url.searchParams.set('locale', locale);
      if (tab) tab.location.href = url.toString();
      else window.location.href = url.toString();
    } catch (err) {
      tab?.close();
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  }
  return <section className="space-y-3 rounded border p-3">
    <h3 className="font-semibold">LTX-Scene-Studio</h3>
    <p className="text-sm text-muted-foreground">{locale === 'zh'
      ? '打开关键场景工作台，自动加载当前项目或章节的素材。'
      : 'Open the scene studio with media from the current project or chapter.'}</p>
    <Button variant="outline" disabled={!projectId || disabled || busy} onClick={() => void openStudio()}>
      {busy ? (locale === 'zh' ? '正在打开…' : 'Opening…') : (locale === 'zh' ? '打开 LTX-Scene-Studio' : 'Open LTX-Scene-Studio')}
    </Button>
    {!projectId && <p className="text-xs text-muted-foreground">{locale === 'zh' ? '请先创建或加载项目。' : 'Create or load a project first.'}</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </section>;
}
