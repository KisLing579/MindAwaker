'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { LoadProjectResponse } from '@/hooks/useTask';
import type { Locale } from '@/lib/i18n';
import { storyTranslator } from '@/lib/story-i18n';

export default function StoryChapters({ projectId, disabled, onLoad, locale = 'zh' }: {
  projectId: string; disabled: boolean; onLoad: (data: LoadProjectResponse & { task_id?: string }) => void;
  locale?: Locale;
}) {
  const t = useMemo(() => storyTranslator(locale), [locale]);
  const [chapters, setChapters] = useState<{ id: string; title: string }[]>([]);
  const [active, setActive] = useState('');
  const [title, setTitle] = useState('');
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/story/${projectId}/chapters`).then(async response => {
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || t('章节加载失败'));
      if (!cancelled) { setChapters(data.chapters); setActive(data.active_chapter); }
    }).catch(error => { if (!cancelled) setError(String(error)); });
    return () => { cancelled = true; };
  }, [projectId, t]);
  async function submit(chapterId?: string, mode: 'generate' | 'review' = 'generate') {
    if (!chapterId && mode === 'review' && !source.trim()) {
      window.location.href = `/story/${projectId}?locale=${locale}`;
      return;
    }
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/story/${projectId}/chapters${chapterId ? `/${chapterId}/load` : ''}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: chapterId ? undefined : JSON.stringify({ title, source_text: source, mode }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
      if (mode === 'review') {
        window.location.href = `/story/${projectId}?locale=${locale}`;
        return;
      }
      setChapters(data.project.chapters); setActive(data.project.active_chapter);
      setTitle(''); setSource(''); onLoad(data);
    } catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3 rounded-lg border p-4">
    <h3 className="font-semibold">{t('章节续建')}</h3>
    <p className="text-sm text-muted-foreground">{t('创建续章后自动抽取元素、划分场景、生成分镜和视频，仅补齐当前章缺失或待更新的素材。分阶段编辑使用下方上传或粘贴的正文创建新章；正文为空时编辑当前章。各章独立保存场景、分镜和素材，共享故事元素。')}</p>
    <label className="block text-sm">{t('当前章节')}
      <select className="ml-2 rounded border bg-background p-2" value={active} disabled={disabled || busy} onChange={event => void submit(event.target.value)}>
        {chapters.map(chapter => <option key={chapter.id} value={chapter.id}>{chapter.title}</option>)}
      </select>
    </label>
    <Input aria-label={t('新章节名称')} placeholder={t('新章节名称（可选）')} value={title} disabled={disabled || busy} onChange={event => setTitle(event.target.value)} />
    <input aria-label={t('上传后续章节 TXT')} type="file" accept=".txt,text/plain" disabled={disabled || busy} onChange={async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        if (file.size > 6 * 1024 * 1024) throw new Error(t('章节文件不能超过 6 MB'));
        const text = await file.text();
        if (text.includes('\uFFFD')) throw new Error(t('请将文件保存为 UTF-8 编码后上传'));
        setSource(text); setTitle(file.name.replace(/\.txt$/i, '')); setError('');
      } catch (error) { setError(String(error)); }
      event.target.value = '';
    }} />
    <textarea aria-label={t('后续章节正文')} className="min-h-32 w-full rounded border bg-background p-3" placeholder={t('上传 UTF-8 TXT，或粘贴后续章节正文')} value={source} disabled={disabled || busy} onChange={event => setSource(event.target.value)} />
    <div className="flex flex-wrap gap-3">
      <Button disabled={disabled || busy || !source.trim()} onClick={() => void submit()}>{busy ? t('正在加载…') : t('创建并加载续章')}</Button>
      <Button variant="outline" disabled={disabled || busy} onClick={() => void submit(undefined, 'review')}>{t('新建/编辑分阶段故事')}</Button>
    </div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </section>;
}
