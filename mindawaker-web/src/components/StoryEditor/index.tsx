'use client';

import { createContext, useContext, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import ClipSettings, { type ClipConfig } from '@/components/VideoGenerator/ClipSettings';
import { getAssetUrl } from '@/lib/generated-files';
import { loadSettings } from '@/hooks/useSettings';
import { htmlLangMap, type Locale } from '@/lib/i18n';
import { storyTranslator } from '@/lib/story-i18n';

const StoryLocale = createContext<Locale>('zh');

type Character = { character_id: string; name: string; type: string; can_talk: boolean; is_main: boolean; visual_core: string; visual_variants_allowed: string; style_tags: string[] };
type Items = { characters: Character[]; objects: Record<string, string>; locations: { name: string; description: string }[]; time: string[]; emotion: string[] };
type Shot = { shot_id: string; scene_id: number; focus_characters: string[]; focus_objects: string[]; shot_type: string; camera_move: string; lighting: string; additional_detail: string[]; shot_text: string; narration_text?: string | null };
type Scene = { scene_text: string; scene_info: { scene_id: number; location: string; time: string; emotion: string; chain_id: string; characters_in_scene: string[]; objects_in_scene: string[]; scene_visual_overrides: Record<string, string>; environment_description?: string }; shots: Shot[] };
type Document = { revision: number; source_text: string; items: Items; scenes: Scene[]; style_tokens: string; stage: string; dirty_images: number[]; dirty_audio: number[]; error?: string };
type Candidate = { image_path: string; prompt: string; is_current: boolean; story_revision?: number; story_input_snapshot?: string };
type Assets = { images?: string[]; audios?: string[]; durations?: number[]; video_path?: string; clips?: { clip_path?: string; dirty?: boolean; render_mode?: string; generated_at?: number }[]; image_redraw_history?: Candidate[][]; stage?: string; inherited_items?: Items; chapter_items_extracted?: boolean };
type Response = { document: Document; project: { task_data: Assets; project_config?: ClipConfig; active_chapter?: string; chapters?: { id: string; title: string }[] }; busy: boolean; task_id?: string };

async function api<T>(url: string, method = 'GET', data?: unknown): Promise<T> {
  const response = await fetch(`/api/story/${url}`, { method, headers: { 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data), cache: 'no-store' });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail || result));
  return result;
}

function Text({ label, value, onChange, rows = 2, readOnly = false }: { label: string; value?: string; onChange?: (value: string) => void; rows?: number; readOnly?: boolean }) {
  return <label className="block space-y-1 text-sm"><span className="font-medium">{label}</span><textarea rows={rows} className="w-full rounded-md border bg-white p-2 text-sm disabled:bg-slate-100" value={value || ''} readOnly={readOnly} onChange={e => onChange?.(e.target.value)} /></label>;
}

function Choice({ label, value, options, onChange }: { label: string; value?: string; options: string[]; onChange: (v: string) => void }) {
  const t = storyTranslator(useContext(StoryLocale));
  return <label className="block space-y-1 text-sm"><span>{label}</span><select className="w-full rounded-md border bg-white p-2" value={value || ''} onChange={e => onChange(e.target.value)}><option value="">{t("请选择")}</option>{Array.from(new Set([...options, ...(value ? [value] : [])])).map(v => <option key={v}>{v}</option>)}</select></label>;
}

function References({ label, value, options, onChange }: { label: string; value: string[]; options: { id: string; label: string }[]; onChange: (v: string[]) => void }) {
  const t = storyTranslator(useContext(StoryLocale));
  return <fieldset className="space-y-2 rounded-md border p-3"><legend className="px-1 text-sm">{label}</legend><div className="flex flex-wrap gap-3">{options.map(option => <label key={option.id} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={value.includes(option.id)} onChange={e => onChange(e.target.checked ? [...value, option.id] : value.filter(v => v !== option.id))} />{option.label}</label>)}{!options.length && <span className="text-xs text-slate-500">{t("请先在上一级添加元素")}</span>}</div></fieldset>;
}

export default function StoryEditor({ projectId }: { projectId: string }) {
  const [locale, setLocale] = useState<Locale>('zh');
  useEffect(() => {
    let cancelled = false;
    const requestedLocale = new URLSearchParams(window.location.search).get('locale');
    if (requestedLocale === 'en' || requestedLocale === 'zh') {
      setLocale(requestedLocale);
      document.documentElement.lang = htmlLangMap[requestedLocale];
      document.body.dataset.locale = requestedLocale;
      return;
    }
    const inheritedLocale = document.documentElement.lang.startsWith('en') ? 'en' : 'zh';
    setLocale(inheritedLocale);
    void loadSettings().then(settings => {
      if (!cancelled) {
        const next = settings.default_language || inheritedLocale;
        setLocale(next);
        document.documentElement.lang = htmlLangMap[next];
        document.body.dataset.locale = next;
      }
    }).catch(() => { /* Keep the current UI language if settings are unavailable. */ });
    return () => { cancelled = true; };
  }, []);
  return <StoryLocale.Provider value={locale}><StoryEditorContent projectId={projectId} /></StoryLocale.Provider>;
}

function StoryEditorContent({ projectId }: { projectId: string }) {
  const locale = useContext(StoryLocale);
  const t = storyTranslator(locale);
  const projectsHref = `/?tab=projects&project=${encodeURIComponent(projectId)}&locale=${locale}`;
  const [doc, setDoc] = useState<Document | null>(null);
  const [assets, setAssets] = useState<Assets>({});
  const [chapterTitle, setChapterTitle] = useState('');
  const [clipConfig, setClipConfig] = useState<ClipConfig>({});
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState(false);
  const [taskId, setTaskId] = useState<string>();
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tab, setTab] = useState<'items' | 'scenes' | 'shots'>('items');
  const [sceneIndex, setSceneIndex] = useState(0);
  const [shotIndex, setShotIndex] = useState(0);
  const [preview, setPreview] = useState<Record<string, string>>({});
  const [candidateIndex, setCandidateIndex] = useState<number | null>(null);
  const initialized = useRef(false);
  const unsaved = useRef(false);
  const reload = useCallback(async () => {
    const result = await api<Response>(projectId);
    setAssets(result.project.task_data || {});
    setClipConfig(result.project.project_config || {});
    setChapterTitle(result.project.chapters?.find(chapter => chapter.id === result.project.active_chapter)?.title || '');
    setBusy(result.busy); setTaskId(result.task_id);
    if (!unsaved.current) setDoc(result.document);
    if (!initialized.current) {
      initialized.current = true;
      const target = new URLSearchParams(window.location.search).get('shot');
      if (target !== null) {
        let index = 0;
        result.document.scenes.forEach((scene, si) => scene.shots.forEach((shot, shi) => {
          if (shot.shot_id === target || String(index) === target) { setSceneIndex(si); setShotIndex(shi); setTab('shots'); }
          index++;
        }));
      }
    }
  }, [projectId]);
  useEffect(() => { void reload().catch(e => setError(e.message)); }, [reload]);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => { void reload().catch(e => setError(e.message)); }, 1800);
    return () => clearInterval(timer);
  }, [busy, reload]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (unsaved.current) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);
  useEffect(() => { setCandidateIndex(null); }, [sceneIndex, shotIndex]);
  function edit(update: (draft: Document) => void) {
    if (!doc || busy || working) return;
    const draft = structuredClone(doc); update(draft); setDoc(draft); setDirty(true); unsaved.current = true;
    setPreview({}); setNotice('');
  }
  async function action(job: () => Promise<void>) {
    setWorking(true); setError(''); setNotice('');
    try { await job(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setWorking(false); }
  }
  async function save() {
    const result = await api<{ document: Document }>(projectId, 'PUT', doc);
    setDoc(result.document); setDirty(false); unsaved.current = false;
    await reload(); setNotice(t("已保存。修改只在明确生成或提交时更新媒体。"));
  }
  async function stage(value: string, shotId?: string) {
    await api(`${projectId}/stage`, 'POST', { revision: doc!.revision, stage: value, shot_id: shotId });
    setBusy(true); await reload();
  }
  if (!doc) return <main className="p-8"><Link href={projectsHref}>{t("返回项目列表")}</Link><p role="alert">{error || t("正在加载故事…")}</p></main>;
  const selectedScene = doc.scenes[sceneIndex];
  const selectedShot = selectedScene?.shots[shotIndex];
  const allShots = doc.scenes.flatMap(s => s.shots);
  const mediaIndex = selectedShot ? allShots.findIndex(s => s.shot_id === selectedShot.shot_id) : -1;
  const history = assets.image_redraw_history?.[mediaIndex] || [];
  const currentImage = candidateIndex !== null ? history[candidateIndex]?.image_path : assets.images?.[mediaIndex];
  const currentClip = assets.clips?.[mediaIndex];
  const clipPreviewUrl = currentClip?.clip_path ? `${getAssetUrl(currentClip.clip_path)}?v=${currentClip.generated_at || 0}` : '';
  const unsubmittedCandidate = candidateIndex !== null && history[candidateIndex]?.image_path !== assets.images?.[mediaIndex];
  
const debugInfo = {
  mediaIndex,
  shotId: selectedShot?.shot_id,
  currentImage: assets.images?.[mediaIndex],
  dirtyImages: doc.dirty_images,
  imageIsDirty: doc.dirty_images.includes(mediaIndex),
  candidateIndex,
};
  const shotClipReason = dirty ? t("请先保存修改") : unsubmittedCandidate ? t("请先提交选中图片，再生成视频段") :
    !assets.images?.[mediaIndex] || doc.dirty_images.includes(mediaIndex) ? t("请先生成并提交当前分镜图片") :
    !assets.audios?.[mediaIndex] || !Number.isFinite(assets.durations?.[mediaIndex]) || (assets.durations?.[mediaIndex] || 0) <= 0 || doc.dirty_audio.includes(mediaIndex) ? t("请先生成当前分镜配音") : '';
  const audioReady = allShots.length > 0 && allShots.every((_, i) => !!assets.audios?.[i] && Number.isFinite(assets.durations?.[i]) && (assets.durations?.[i] || 0) > 0);
  const imagesReady = allShots.length > 0 && allShots.every((_, i) => !!assets.images?.[i]);
  const complete = doc.scenes.length > 0 && doc.scenes.every(s => s.shots.length > 0);
  const disabled = busy || working;
  const charOptions = doc.items.characters.map(c => ({ id: c.character_id, label: `${c.name} · ${c.character_id}` }));
  const objectOptions = Object.keys(doc.items.objects).map(id => ({ id, label: id }));
  const info = selectedScene?.scene_info;
  const patchScene = (key: keyof Scene['scene_info'], value: unknown) => edit(d => { Object.assign(d.scenes[sceneIndex].scene_info, { [key]: value }); });
  const patchShot = (key: keyof Shot, value: unknown) => edit(d => { Object.assign(d.scenes[sceneIndex].shots[shotIndex], { [key]: value }); });
  const hasMedia = !!assets.images?.some(Boolean) || !!assets.audios?.some(Boolean);
  const pendingImages = allShots.flatMap((_, i) => !assets.images?.[i] || doc.dirty_images.includes(i) ? [i] : []);
  const pendingAudio = allShots.flatMap((_, i) => !assets.audios?.[i] || !Number.isFinite(assets.durations?.[i]) || (assets.durations?.[i] || 0) <= 0 || doc.dirty_audio.includes(i) ? [i] : []);
  const composeReasons = [
    disabled ? t("任务或保存正在进行，请等待完成") : '',
    dirty ? t("请先保存修改") : '',
    !complete ? t("请先补齐场景和分镜") : '',
    pendingImages.length ? t("第 {0} 个分镜的图片缺失或待更新，请生成图片或提交候选图", [pendingImages.map(i => i + 1).join('、')]) : '',
    pendingAudio.length ? t("第 {0} 个分镜的音频缺失或待更新，请生成音频", [pendingAudio.map(i => i + 1).join('、')]) : '',
  ].filter(Boolean);
  function focusMedia(index: number) {
    let offset = 0;
    for (let si = 0; si < doc!.scenes.length; si++) {
      const count = doc!.scenes[si].shots.length;
      if (index < offset + count) {
        setSceneIndex(si); setShotIndex(index - offset); setTab('shots'); setCandidateIndex(null);
        return;
      }
      offset += count;
    }
  }
  const needsChapterItems = !!assets.inherited_items && !assets.chapter_items_extracted && !doc.scenes.length;
  return <main className="story-editor-surface mx-auto min-h-screen max-w-7xl space-y-5 bg-white px-4 py-8 text-slate-900 md:px-8">
    <header className="space-y-3"><Link href={projectsHref} className="text-sm text-blue-700">{t("← 返回项目列表")}</Link><h1 className="text-2xl font-semibold">{t("故事元素与分镜编辑")}</h1><p className="text-sm text-slate-500">{t("项目")}{' '}{projectId} {' '}{t("· 版本")}{' '}{doc.revision} · {dirty ? t("有未保存修改") : t("已保存")}</p>
      <p className="text-sm">{t("先审阅元素，再生成场景和分镜。每个阶段独立保存，生成素材前可以反复调整。")}</p>
      {/* <pre className="text-xs bg-gray-100 p-2">{JSON.stringify(debugInfo, null, 2)}</pre> */}
      {chapterTitle && <p className="font-medium">{t("当前章节：")}{chapterTitle}</p>}
      <ClipSettings locale={locale} config={clipConfig} projectId={projectId} disabled={disabled || dirty} onChange={next => { setClipConfig(next); void reload().catch(e => setError(e.message)); }} />
      {needsChapterItems && <p role="status" className="rounded-md bg-amber-50 p-3 text-sm">{t("本章正文已加载。下方暂时显示从前章继承的元素，本章新增人物和物品尚未抽取。")}{busy ? t("抽取完成后将自动刷新。") : t("请点击“抽取本章新增元素”，完成后会合并显示。")}</p>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={disabled || !dirty} onClick={() => void action(save)}>{t("保存修改")}</Button>
        <Button variant="outline" disabled={disabled} onClick={() => { if (dirty && !window.confirm(t("丢弃未保存修改并重新加载？"))) return; unsaved.current = false; setDirty(false); void action(reload); }}>{t("重新加载")}</Button>
        <Button variant="outline" disabled={disabled || dirty || doc.scenes.length > 0 || !doc.source_text.trim()} onClick={() => void action(() => stage('items'))}>{assets.inherited_items ? t("1. 抽取本章新增元素") : t("1. 抽取元素")}</Button>
        <Button variant="outline" disabled={disabled || dirty || needsChapterItems || doc.scenes.length > 0 || !doc.items.locations.length} onClick={() => void action(() => stage('scenes'))}>{t("2. 生成场景")}</Button>
        <Button variant="outline" disabled={disabled || dirty || !doc.scenes.length || complete} onClick={() => void action(() => stage('shots'))}>{t("3. 生成缺失分镜")}</Button>
        <Button disabled={disabled || dirty || !complete} onClick={() => void action(() => stage('images'))}>{t("4. 批量生成图片")}</Button>
        <Button disabled={disabled || dirty || !complete} onClick={() => void action(() => stage('audio'))}>{t("5. 批量生成音频")}</Button>
        <Button variant="outline" disabled={disabled || dirty || !complete || !!doc.dirty_images.length || !!doc.dirty_audio.length || !imagesReady || !audioReady} onClick={() => void action(() => stage('compose'))}>{t("6. 合成视频")}</Button>
      </div>
      <p className="text-xs text-slate-500">{doc.items.characters.length} {' '}{t("人物 ·")}{' '}{Object.keys(doc.items.objects).length} {' '}{t("物品 ·")}{' '}{doc.scenes.length} {' '}{t("场景 ·")}{' '}{allShots.length} {' '}{t("分镜 · 待更新图片")}{' '}{doc.dirty_images.length} {' '}{t("/ 配音")}{' '}{doc.dirty_audio.length}</p>
      {composeReasons.length > 0 && <div role="status" className="space-y-2 rounded-md bg-amber-50 p-3 text-sm">
        <p className="font-medium">{t("合成视频前还需完成：")}</p>
        <ul className="list-inside list-disc">{composeReasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
        {pendingImages.length > 0 && <Button size="sm" variant="outline" onClick={() => focusMedia(pendingImages[0])}>{t("定位第")}{' '}{pendingImages[0] + 1} {' '}{t("个分镜，检查并提交图片")}</Button>}
        {!pendingImages.length && pendingAudio.length > 0 && <Button size="sm" variant="outline" onClick={() => focusMedia(pendingAudio[0])}>{t("定位第")}{' '}{pendingAudio[0] + 1} {' '}{t("个分镜，检查音频")}</Button>}
      </div>}
      {busy && <div role="status" className="rounded-md bg-blue-50 p-3 text-sm">{t("正在执行：")}{assets.stage || t("准备中")}{t("。完成后自动加载，编辑暂时锁定。")}{taskId && <Button size="sm" variant="outline" className="ml-3" onClick={() => void action(async () => { const r = await fetch(`/api/video/cancel/${taskId}`, { method: 'POST' }); if (!r.ok) throw new Error(t("取消失败")); setNotice(t("已请求取消，等待当前步骤结束。")); })}>{t("取消任务")}</Button>}</div>}
      {(error || doc.error) && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error || doc.error}</p>}
      {notice && <p role="status" className="text-sm text-green-700">{notice}</p>}
    </header>
    <div className="sticky top-0 z-20 space-y-2 border-b bg-white py-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav className="flex flex-wrap gap-2">{(['items', 'scenes', 'shots'] as const).map((value, i) => <Button key={value} variant={tab === value ? 'default' : 'outline'} onClick={() => setTab(value)}>{[t("故事元素"), t("场景列表"), t("分镜列表")][i]}</Button>)}</nav>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600">{busy ? t("任务进行中") : dirty ? t("有未保存修改") : t("已保存")}</span>
          <Button disabled={disabled || !dirty} onClick={() => void action(save)}>{t("保存修改")}</Button>
        </div>
      </div>
      {dirty && <p className="text-xs text-amber-700">{t("保存本页所有修改后，即可生成候选或重抽。")}</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
    <fieldset disabled={disabled} className="min-w-0 space-y-5 disabled:opacity-70">
      {tab === 'items' && <div className="space-y-5">
        <details open={!doc.scenes.length}><summary className="cursor-pointer font-medium">{t("故事原文")}</summary><Text label={t("原文（修改后场景和分镜必须保持完整覆盖）")} value={doc.source_text} rows={8} onChange={v => edit(d => { d.source_text = v; })} /></details>
        <section className="space-y-3"><h2 className="text-lg font-semibold">{t("人物")}</h2><div className="grid gap-4 md:grid-cols-2">{doc.items.characters.map((c, index) => <article key={index} className="space-y-3 rounded-lg border p-4">
          <div className="grid grid-cols-2 gap-3"><Text label={t("编号")} value={c.character_id} onChange={v => edit(d => { d.items.characters[index].character_id = v; })} /><Text label={t("名称")} value={c.name} onChange={v => edit(d => { d.items.characters[index].name = v; })} /></div>
          <Text label={t("固定外貌 visual_core")} value={c.visual_core} rows={4} onChange={v => edit(d => { d.items.characters[index].visual_core = v; })} />
          <Text label={t("允许变化的特征")} value={c.visual_variants_allowed} onChange={v => edit(d => { d.items.characters[index].visual_variants_allowed = v; })} />
          <Choice label={t("类型")} value={c.type} options={['human', 'animal', 'object']} onChange={v => edit(d => { d.items.characters[index].type = v; })} />
          <div className="flex gap-4">{(['can_talk', 'is_main'] as const).map((key, i) => <label key={key} className="text-sm"><input type="checkbox" checked={c[key]} onChange={e => edit(d => { d.items.characters[index][key] = e.target.checked; })} /> {[t("可以说话"), t("主要人物")][i]}</label>)}</div>
          <Button size="sm" variant="outline" onClick={() => edit(d => { d.items.characters.splice(index, 1); })}>{t("移除人物")}</Button>
        </article>)}</div><Button variant="outline" onClick={() => edit(d => { d.items.characters.push({ character_id: `person_${crypto.randomUUID().slice(0, 8)}`, name: '', type: 'human', can_talk: true, is_main: false, visual_core: '', visual_variants_allowed: '', style_tags: [] }); })}>{t("添加人物")}</Button></section>
        <section className="space-y-3"><h2 className="text-lg font-semibold">{t("物品")}</h2>{Object.entries(doc.items.objects).map(([name, description], index) => <div key={index} className="grid gap-3 rounded-lg border p-4 md:grid-cols-[1fr_3fr_auto]">
          <Text label={t("名称（用于引用）")} value={name} onChange={v => edit(d => { if (v !== name && v in d.items.objects) return; d.items.objects = Object.fromEntries(Object.entries(d.items.objects).map(([k, desc]) => [k === name ? v : k, desc])); })} />
          <Text label={t("物品描述")} value={description} onChange={v => edit(d => { d.items.objects[name] = v; })} /><Button variant="outline" onClick={() => edit(d => { delete d.items.objects[name]; })}>{t("移除")}</Button>
        </div>)}<Button variant="outline" onClick={() => edit(d => { d.items.objects[`object_${crypto.randomUUID().slice(0, 8)}`] = ''; })}>{t("添加物品")}</Button></section>
        <section className="space-y-3"><h2 className="text-lg font-semibold">{t("地点")}</h2>{doc.items.locations.map((location, index) => <div key={index} className="grid gap-3 rounded-lg border p-4 md:grid-cols-[1fr_3fr_auto]"><Text label={t("名称")} value={location.name} onChange={v => edit(d => { d.items.locations[index].name = v; })} /><Text label={t("环境描述")} value={location.description} onChange={v => edit(d => { d.items.locations[index].description = v; })} /><Button variant="outline" onClick={() => edit(d => { d.items.locations.splice(index, 1); })}>{t("移除")}</Button></div>)}<Button variant="outline" onClick={() => edit(d => { d.items.locations.push({ name: '', description: '' }); })}>{t("添加地点")}</Button></section>
        <div className="grid gap-4 md:grid-cols-2"><Text label={t("时间词表（每行一项）")} value={doc.items.time.join('\n')} onChange={v => edit(d => { d.items.time = v.split('\n'); })} /><Text label={t("情绪词表（每行一项）")} value={doc.items.emotion.join('\n')} onChange={v => edit(d => { d.items.emotion = v.split('\n'); })} /></div>
        <Text label={t("统一画风")} value={doc.style_tokens} onChange={v => edit(d => { d.style_tokens = v; })} />
        <p className="text-xs text-slate-500">{t("编号和名称被场景引用。重命名或移除后，请同步调整引用；保存时会检查。")}</p>
      </div>}
      {tab !== 'items' && <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
        <aside className="space-y-3"><h2 className="font-semibold">{t("场景导航")}</h2>{doc.scenes.map((scene, index) => <button type="button" key={scene.scene_info.scene_id} onClick={() => { setSceneIndex(index); setShotIndex(0); }} className={`block w-full rounded-md border p-3 text-left text-sm ${index === sceneIndex ? 'border-blue-500 bg-blue-50' : ''}`}>{t("场景")}{' '}{scene.scene_info.scene_id} · {scene.scene_info.location}<span className="mt-1 block text-xs text-slate-500">{scene.shots.length} {' '}{t("个分镜 ·")}{' '}{scene.scene_text.slice(0, 45)}</span></button>)}
          {!hasMedia && <Button variant="outline" onClick={() => edit(d => { const id = Math.max(0, ...d.scenes.map(s => s.scene_info.scene_id)) + 1; d.scenes.push({ scene_text: '', scene_info: { scene_id: id, location: d.items.locations[0]?.name || '', time: d.items.time[0] || '', emotion: d.items.emotion[0] || '', chain_id: '', characters_in_scene: [], objects_in_scene: [], scene_visual_overrides: {} }, shots: [] }); setSceneIndex(d.scenes.length - 1); })}>{t("添加场景")}</Button>}
        </aside>
        <div className="min-w-0 space-y-4">{!selectedScene ? <p className="rounded-lg border border-dashed p-8 text-slate-500">{t("先保存元素并生成场景，或手动添加场景。")}</p> : <>
          {tab === 'scenes' && <>
            <h2 className="text-lg font-semibold">{t("场景")}{' '}{info.scene_id}</h2><Text label={t("场景原文")} rows={6} value={selectedScene.scene_text} onChange={v => edit(d => { d.scenes[sceneIndex].scene_text = v; })} />
            <div className="grid gap-3 md:grid-cols-3"><Choice label={t("地点")} value={info.location} options={doc.items.locations.map(l => l.name)} onChange={v => patchScene('location', v)} /><Choice label={t("时间")} value={info.time} options={doc.items.time} onChange={v => patchScene('time', v)} /><Choice label={t("情绪")} value={info.emotion} options={doc.items.emotion} onChange={v => patchScene('emotion', v)} /></div>
            <Text label={t("叙事线 chain_id")} value={info.chain_id} onChange={v => patchScene('chain_id', v)} />
            <References label={t("出场人物")} value={info.characters_in_scene} options={charOptions} onChange={v => patchScene('characters_in_scene', v)} /><References label={t("场景物品")} value={info.objects_in_scene} options={objectOptions} onChange={v => patchScene('objects_in_scene', v)} />
            <h3 className="font-medium">{t("场景人物变化 scene_visual_overrides")}</h3>{Array.from(new Set([...info.characters_in_scene, ...Object.keys(info.scene_visual_overrides)])).map(cid => <Text key={cid} label={`${doc.items.characters.find(c => c.character_id === cid)?.name || cid} · ${cid}`} value={info.scene_visual_overrides[cid]} rows={3} onChange={v => edit(d => { if (v) d.scenes[sceneIndex].scene_info.scene_visual_overrides[cid] = v; else delete d.scenes[sceneIndex].scene_info.scene_visual_overrides[cid]; })} />)}
            <Text label={t("环境布置")} value={info.environment_description || ''} rows={3} onChange={v => patchScene('environment_description', v)} />
            <p className="text-xs text-slate-500">{t("场景描述修改影响该场景的相关分镜。人物稳定外貌在“故事元素”中编辑。")}</p>
            {!hasMedia && <Button variant="outline" onClick={() => edit(d => { d.scenes.splice(sceneIndex, 1); setSceneIndex(0); setShotIndex(0); })}>{t("移除此场景及其分镜")}</Button>}
          </>}
          {tab === 'shots' && <>
            <div className="flex flex-wrap gap-2">{selectedScene.shots.map((shot, index) => <Button key={shot.shot_id} size="sm" variant={shotIndex === index ? 'default' : 'outline'} onClick={() => setShotIndex(index)}>{t("分镜")}{' '}{index + 1}</Button>)}{!hasMedia && <Button size="sm" variant="outline" onClick={() => edit(d => { d.scenes[sceneIndex].shots.push({ shot_id: `scene${info.scene_id}-${crypto.randomUUID().slice(0, 8)}`, scene_id: info.scene_id, focus_characters: [], focus_objects: [], shot_type: 'medium', camera_move: 'static', lighting: '', additional_detail: [], shot_text: '' }); setShotIndex(d.scenes[sceneIndex].shots.length - 1); })}>{t("添加分镜")}</Button>}</div>
            {selectedShot ? <>
              <div className="grid gap-5 xl:grid-cols-2"><div className="space-y-3">
                {currentImage ? <img className="max-h-[500px] w-full rounded-lg bg-slate-50 object-contain" src={getAssetUrl(currentImage)} alt={t("分镜 {0}", [selectedShot.shot_id])} /> : <div className="flex aspect-square items-center justify-center rounded-lg border border-dashed text-slate-400">{t("尚未生成图片")}</div>}
                {doc.dirty_images.includes(mediaIndex) && <p className="text-sm text-amber-700">{t("此分镜提示词已更新，图片待生成或提交。")}</p>}
                <div className="flex gap-2"><Button disabled={dirty || disabled} onClick={() => void action(() => stage('redraw', selectedShot.shot_id))}>{t("生成候选 / 重抽")}</Button><Button variant="outline" disabled={dirty || disabled || candidateIndex === null} onClick={() => void action(async () => { await api(`${projectId}/selection`, 'POST', { revision: doc.revision, shot_id: selectedShot.shot_id, history_index: candidateIndex }); await reload(); setNotice(t("已提交当前图片。")); })}>{t("提交选中图片")}</Button></div>
                <div className="grid grid-cols-4 gap-2">{history.map((candidate, index) => candidate.image_path && <button type="button" key={index} aria-pressed={candidateIndex === index} className={`rounded border p-1 ${candidateIndex === index ? 'border-blue-600 ring-2 ring-blue-100' : ''}`} onClick={() => setCandidateIndex(index)}><img src={getAssetUrl(candidate.image_path)} alt={t("候选 {0}", [index + 1])} className="aspect-square w-full object-contain" /><span className="text-xs">{candidate.is_current ? t("当前使用") : t("候选 {0}", [index + 1])}</span></button>)}</div>
                <section className="space-y-2 rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <Button disabled={disabled || !!shotClipReason} onClick={() => void action(() => stage('clip', selectedShot.shot_id))}>{t("生成视频段")}</Button>
                    <span className="text-sm text-slate-500">{clipConfig.clip_mode === 'jimeng' ? t("即梦首帧视频＋配音") : t("静态图片＋配音")}</span>
                  </div>
                  <p className="text-xs text-slate-500">{t("使用本分镜当前已提交图片和配音，按页面上方已应用的视频段设置生成。")}</p>
                  {shotClipReason && <p className="text-xs text-amber-700">{shotClipReason}</p>}
                  {clipPreviewUrl && <>
                    <video key={`${selectedShot.shot_id}-${clipPreviewUrl}`} controls preload="metadata" src={clipPreviewUrl} className="max-h-[500px] w-full rounded bg-black" />
                    {currentClip?.dirty && <p className="text-xs text-amber-700">{t("素材或生成方式已修改，当前预览为旧视频段，请重新生成。")}</p>}
                  </>}
                </section>
                {candidateIndex !== null && history[candidateIndex] && <details><summary className="cursor-pointer text-sm">{t("查看此版本生成输入")}</summary><p className="text-xs text-slate-500">{t("结构化版本：")}{history[candidateIndex].story_revision ?? t("旧版未记录")}</p><Text label={t("当时的提示词")} value={history[candidateIndex].prompt} rows={6} readOnly />{history[candidateIndex].story_input_snapshot && <a className="text-sm text-blue-700" target="_blank" rel="noreferrer" href={getAssetUrl(`app/assets/projects/${projectId}/${history[candidateIndex].story_input_snapshot}`)}>{t("查看结构化输入快照")}</a>}</details>}
              </div><div className="space-y-4">
                <h2 className="font-semibold">{selectedShot.shot_id}</h2>
                <Text label={t("旁白文本（用于生成音频，可自由编辑）")} value={selectedShot.narration_text ?? selectedShot.shot_text} rows={4} onChange={v => patchShot('narration_text', v)} />
                <p className="text-xs text-slate-500">{t("保存旁白后，点击上方“批量生成音频”。只补齐缺失或待更新的音频。")}</p>
                {selectedShot.narration_text != null && <Button size="sm" variant="outline" onClick={() => patchShot('narration_text', null)}>{t("恢复原文旁白")}</Button>}
                {assets.audios?.[mediaIndex] && <div className="space-y-1"><audio controls preload="none" src={getAssetUrl(assets.audios[mediaIndex])} className="w-full" /><p className="text-xs text-slate-500">{doc.dirty_audio.includes(mediaIndex) ? t("旁白已修改，此处为旧音频，待重新生成。") : t("当前分镜配音")}</p></div>}
                <details><summary className="cursor-pointer text-sm text-slate-500">{t("查看 / 调整分镜原文范围")}</summary><Text label={t("分镜原文（需完整覆盖场景）")} value={selectedShot.shot_text} rows={4} onChange={v => patchShot('shot_text', v)} /></details>
                <References label={t("关注人物")} value={selectedShot.focus_characters} options={charOptions.filter(c => info.characters_in_scene.includes(c.id))} onChange={v => patchShot('focus_characters', v)} />
                {selectedShot.focus_characters.map(cid => <div key={cid} className="rounded-md bg-slate-50 p-3 text-sm"><strong>{doc.items.characters.find(c => c.character_id === cid)?.name} · {cid}</strong><p>{doc.items.characters.find(c => c.character_id === cid)?.visual_core}</p><p className="mt-2">{t("场景变化：")}{info.scene_visual_overrides[cid] || t("无")}</p></div>)}
                <References label={t("关注物品")} value={selectedShot.focus_objects} options={objectOptions.filter(o => info.objects_in_scene.includes(o.id))} onChange={v => patchShot('focus_objects', v)} />
                {selectedShot.focus_objects.map(name => <p key={name} className="rounded bg-slate-50 p-2 text-sm">{name}：{doc.items.objects[name]}</p>)}
                <div className="rounded-md bg-blue-50 p-3 text-sm"><p>{t("继承场景：")}{info.location} · {info.time} · {info.emotion}</p><p>{doc.items.locations.find(l => l.name === info.location)?.description}</p><button type="button" className="mt-2 text-blue-700 underline" onClick={() => setTab('scenes')}>{t("编辑此场景及 scene_visual_overrides")}</button><button type="button" className="ml-3 text-blue-700 underline" onClick={() => setTab('items')}>{t("编辑人物 / 物品描述")}</button></div>
                <div className="grid grid-cols-2 gap-3"><Text label={t("景别 shot_type")} value={selectedShot.shot_type} onChange={v => patchShot('shot_type', v)} /><Text label={t("运镜 camera_move")} value={selectedShot.camera_move} onChange={v => patchShot('camera_move', v)} /></div>
                <Text label={t("光照 lighting")} value={selectedShot.lighting} onChange={v => patchShot('lighting', v)} /><Text label={t("额外细节 additional_detail（每行一项，人物用编号、物品用名称）")} rows={6} value={selectedShot.additional_detail.join('\n')} onChange={v => patchShot('additional_detail', v.split('\n'))} />
                {!hasMedia && <Button variant="outline" onClick={() => edit(d => { d.scenes[sceneIndex].shots.splice(shotIndex, 1); setShotIndex(0); })}>{t("移除此分镜")}</Button>}
              </div></div>
              <Button variant="outline" disabled={disabled || !complete} onClick={() => void action(async () => { const result = await api<{ segments: { shot_id: string; image_prompt: string }[] }>(`${projectId}/preview`, 'POST', doc); setPreview(Object.fromEntries(result.segments.map(s => [s.shot_id, s.image_prompt]))); })}>{t("预览最终提示词（不调用模型）")}</Button>
              {preview[selectedShot.shot_id] && <Text label={t("编译后的最终提示词")} value={preview[selectedShot.shot_id]} rows={7} readOnly />}
            </> : <p className="rounded border border-dashed p-6 text-slate-500">{t("先保存场景并生成分镜，或手动添加。")}</p>}
          </>}
        </>}</div>
      </div>}
    </fieldset>
    {assets.video_path && <section><h2 className="mb-3 font-semibold">{t("已合成视频")}</h2><video controls src={getAssetUrl(assets.video_path)} className="max-h-[600px] w-full" /></section>}
  </main>;
}
