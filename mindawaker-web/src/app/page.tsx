'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, History, ImageIcon, Mic2, RefreshCw, Settings, Sparkles, Type, Upload, Video, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import VideoGenerator from '@/components/VideoGenerator';
import TextGenerator from '@/components/TextGenerator';
import AudioGenerator from '@/components/AudioGenerator';
import ImageGenerator from '@/components/ImageGenerator';
import {
  formatProjectUpdatedAt,
  getProjectDisplayStatus,
  getVideoStateFromLoadResponse,
  isProjectRecoverable,
  listProjects,
  loadProject,
  rebuildProject,
  type ListProjectsWarning,
  type SavedProjectSummary,
  type VideoGeneratorState,
} from '@/hooks/useTask';
import {
  createEmptySettings,
  getTemplateNameFromPath,
  listTemplateOptions,
  loadSettings,
  loadSettingsDefaults,
  saveSettings,
  uploadTemplate,
  uploadVoice,
  type SettingsData,
  type SettingsDefaults,
  type TemplateConfigValue,
  type TemplateOption,
} from '@/hooks/useSettings';
import { getStyleLabel, htmlLangMap, localeLabels, translate, type Locale } from '@/lib/i18n';

type MainTab = 'workspace' | 'projects' | 'settings';
type WorkspaceTab = 'video' | 'text' | 'audio' | 'image';

type ThemeTemplateRow = {
  id: string;
  theme: string;
  zhPath: string;
  enPath: string;
};

type MediaPromptTemplateRow = {
  id: string;
  key: string;
  zhPath: string;
  enPath: string;
};

type PendingVoiceUpload = {
  name: string;
  file: File | null;
};

const workspaceTabs: Array<{
  key: WorkspaceTab;
  labelKey: 'videoGeneration' | 'textGeneration' | 'audioGeneration' | 'imageGeneration';
  descriptionKey: 'videoGenerationDesc' | 'textGenerationDesc' | 'audioGenerationDesc' | 'imageGenerationDesc';
  icon: typeof Video;
}> = [
  { key: 'video', labelKey: 'videoGeneration', descriptionKey: 'videoGenerationDesc', icon: Video },
  { key: 'text', labelKey: 'textGeneration', descriptionKey: 'textGenerationDesc', icon: Type },
  { key: 'audio', labelKey: 'audioGeneration', descriptionKey: 'audioGenerationDesc', icon: Mic2 },
  { key: 'image', labelKey: 'imageGeneration', descriptionKey: 'imageGenerationDesc', icon: ImageIcon },
];

const textModels = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openai', label: 'OpenAI GPT' },
];

const imageModels = [
  { value: 'flux', label: 'Flux' },
  { value: 'jimeng', label: '即梦' },
  { value: 'openai', label: 'OpenAI DALL-E' },
  { value: 'sdxl', label: 'Stable Diffusion XL' },
];

const audioModels = [
  { value: 'azure', label: 'Azure TTS' },
  { value: 'auralis', label: 'Auralis' },
  { value: 'microsoft', label: 'Microsoft TTS' },
];

function getLocalizedTemplatePath(value: TemplateConfigValue | undefined, locale: Locale) {
  if (!value) return '';
  if (typeof value === 'string') return locale === 'zh' ? value : '';
  return value[locale] || '';
}

function createThemeTemplateRows(settings: SettingsData): ThemeTemplateRow[] {
  return Object.entries(settings.theme2text_templates || {}).map(([theme, value], index) => ({
    id: `${theme}-${index}`,
    theme,
    zhPath: getLocalizedTemplatePath(value, 'zh'),
    enPath: getLocalizedTemplatePath(value, 'en'),
  }));
}

function createMediaPromptTemplateRows(settings: SettingsData): MediaPromptTemplateRow[] {
  return Object.entries(settings.media_prompt_templates || {}).map(([key, value], index) => ({
    id: `${key}-${index}`,
    key,
    zhPath: getLocalizedTemplatePath(value, 'zh'),
    enPath: getLocalizedTemplatePath(value, 'en'),
  }));
}

function createThemeTemplateMap(rows: ThemeTemplateRow[]) {
  return rows.reduce<Record<string, TemplateConfigValue>>((acc, row) => {
    const theme = row.theme.trim();
    const zhPath = row.zhPath.trim();
    const enPath = row.enPath.trim();
    if (!theme) return acc;
    if (zhPath && enPath) {
      acc[theme] = { zh: zhPath, en: enPath };
    } else if (zhPath) {
      acc[theme] = zhPath;
    } else if (enPath) {
      acc[theme] = { en: enPath };
    }
    return acc;
  }, {});
}

function createMediaPromptTemplateMap(rows: MediaPromptTemplateRow[]) {
  return rows.reduce<Record<string, TemplateConfigValue>>((acc, row) => {
    const key = row.key.trim();
    const zhPath = row.zhPath.trim();
    const enPath = row.enPath.trim();
    if (!key) return acc;
    if (zhPath && enPath) {
      acc[key] = { zh: zhPath, en: enPath };
    } else if (zhPath) {
      acc[key] = zhPath;
    } else if (enPath) {
      acc[key] = { en: enPath };
    }
    return acc;
  }, {});
}

function syncHtmlLanguage(locale: Locale) {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = htmlLangMap[locale];
  document.body.dataset.locale = locale;
}

function getLocalizedError(error: unknown, zh: string, en: string, locale: Locale) {
  const message = error && typeof error === 'object' && 'message' in error ? String((error as { message?: string }).message || '') : '';
  return message || (locale === 'zh' ? zh : en);
}

function formatThemeTemplateSummary(row: ThemeTemplateRow, locale: Locale) {
  const items: string[] = [];
  if (row.zhPath) items.push(`zh→${getTemplateNameFromPath(row.zhPath)}`);
  if (row.enPath) items.push(`en→${getTemplateNameFromPath(row.enPath)}`);
  return `${row.theme}→${items.join(' / ') || (locale === 'zh' ? '未配置' : 'unset')}`;
}

function formatMediaPromptTemplateSummary(row: MediaPromptTemplateRow, locale: Locale) {
  const items: string[] = [];
  if (row.zhPath) items.push(`zh→${getTemplateNameFromPath(row.zhPath)}`);
  if (row.enPath) items.push(`en→${getTemplateNameFromPath(row.enPath)}`);
  return `${row.key}→${items.join(' / ') || (locale === 'zh' ? '未配置' : 'unset')}`;
}

export default function Home() {
  const [locale, setLocale] = useState<Locale>('zh');
  const localeRef = useRef<Locale>('zh');
  const [activeTab, setActiveTab] = useState<MainTab>('workspace');
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>('video');
  const [projects, setProjects] = useState<SavedProjectSummary[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [projectsWarning, setProjectsWarning] = useState<ListProjectsWarning | null>(null);
  const [selectedVideoState, setSelectedVideoState] = useState<VideoGeneratorState | null>(null);
  const [historyBusyProjectId, setHistoryBusyProjectId] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedLocale = params.get('locale');
    if (requestedLocale === 'en' || requestedLocale === 'zh') setLocale(requestedLocale);
    const tab = params.get('tab');
    if (tab === 'projects' || tab === 'workspace' || tab === 'settings') {
      setActiveTab(tab);
    }
    const projectId = params.get('project');
    if (!projectId) return;

    // Restore persisted project data after returning from the story editor.
    // Keep the requested tab instead of switching to the workspace on load.
    let cancelled = false;
    setHistoryBusyProjectId(projectId);
    setProjectsError(null);
    void loadProject(projectId).then(data => {
      if (!cancelled) {
        setSelectedVideoState(getVideoStateFromLoadResponse(data));
        setActiveWorkspaceTab('video');
      }
    }).catch(error => {
      if (!cancelled) {
        setProjectsError(getLocalizedError(error, '恢复项目失败', 'Failed to restore project', localeRef.current));
        setActiveTab('projects');
      }
    }).finally(() => {
      if (!cancelled) setHistoryBusyProjectId(null);
    });
    return () => { cancelled = true; };
  }, []);

  const [settingsData, setSettingsData] = useState<SettingsData>(createEmptySettings());
  const [settingsDefaults, setSettingsDefaults] = useState<SettingsDefaults | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSuccess, setSettingsSuccess] = useState<string | null>(null);
  const [templateOptions, setTemplateOptions] = useState<TemplateOption[]>([]);
  const [templateUploading, setTemplateUploading] = useState(false);
  const [voiceUploading, setVoiceUploading] = useState(false);
  const [themeTemplateRows, setThemeTemplateRows] = useState<ThemeTemplateRow[]>([]);
  const [mediaPromptTemplateRows, setMediaPromptTemplateRows] = useState<MediaPromptTemplateRow[]>([]);
  const [pendingTemplateTheme, setPendingTemplateTheme] = useState('');
  const [pendingTemplateZhSelection, setPendingTemplateZhSelection] = useState('');
  const [pendingTemplateEnSelection, setPendingTemplateEnSelection] = useState('');
  const [pendingVoiceUpload, setPendingVoiceUpload] = useState<PendingVoiceUpload>({ name: '', file: null });

  const t = useCallback(
    (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  );

  useEffect(() => {
    localeRef.current = locale;
    syncHtmlLanguage(locale);
  }, [locale]);

  const refreshProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsError(null);
    try {
      const data = await listProjects();
      setProjects(data.projects.filter((project) => project.target === 'video'));
      setProjectsWarning(data.warning ?? null);
    } catch (error) {
      setProjectsWarning(null);
      setProjectsError(getLocalizedError(error, '加载项目历史失败', 'Failed to load project history', localeRef.current));
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  const refreshSettings = useCallback(async () => {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const [loadedSettings, loadedTemplates, loadedDefaults] = await Promise.all([
        loadSettings(),
        listTemplateOptions(),
        loadSettingsDefaults(),
      ]);
      const requestedLocale = new URLSearchParams(window.location.search).get('locale');
      const nextLocale = requestedLocale === 'en' || requestedLocale === 'zh'
        ? requestedLocale
        : loadedSettings.default_language || loadedDefaults.default_language || 'zh';
      setLocale(nextLocale);
      setSettingsData(loadedSettings);
      setSettingsDefaults(loadedDefaults);
      setTemplateOptions(loadedTemplates);
      setThemeTemplateRows(createThemeTemplateRows(loadedSettings));
      setMediaPromptTemplateRows(createMediaPromptTemplateRows(loadedSettings));
      setPendingTemplateZhSelection(loadedTemplates[0]?.path || '');
      setPendingTemplateEnSelection(loadedTemplates[0]?.path || '');
    } catch (error) {
      setSettingsError(getLocalizedError(error, '加载设置失败', 'Failed to load settings', localeRef.current));
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshProjects();
    void refreshSettings();
  }, [refreshProjects, refreshSettings]);

  const handleLoadProject = useCallback(async (projectId: string) => {
    setHistoryBusyProjectId(projectId);
    setProjectsError(null);
    try {
      const data = await loadProject(projectId);
      setSelectedVideoState(getVideoStateFromLoadResponse(data));
      setActiveTab('workspace');
      setActiveWorkspaceTab('video');
      await refreshProjects();
    } catch (error) {
      setProjectsError(getLocalizedError(error, '加载项目失败', 'Failed to load project', locale));
    } finally {
      setHistoryBusyProjectId(null);
    }
  }, [locale, refreshProjects]);

  const handleRebuildProject = useCallback(async (projectId: string) => {
    setHistoryBusyProjectId(projectId);
    setProjectsError(null);
    try {
      const loaded = await loadProject(projectId);
      const rebuild = await rebuildProject(projectId);
      setSelectedVideoState({
        ...getVideoStateFromLoadResponse(loaded),
        projectId,
        status: {
          ...getVideoStateFromLoadResponse(loaded).status!,
          id: rebuild.task_id,
          status: 'pending',
          pipeline_status: getVideoStateFromLoadResponse(loaded).status?.pipeline_status,
          progress: 0,
          stage: locale === 'zh' ? '正在准备重建项目' : 'Preparing project rebuild',
          message: rebuild.message,
          done: false,
        },
      });
      setActiveTab('workspace');
      setActiveWorkspaceTab('video');
      await refreshProjects();
    } catch (error) {
      setProjectsError(getLocalizedError(error, '重建项目失败', 'Failed to rebuild project', locale));
    } finally {
      setHistoryBusyProjectId(null);
    }
  }, [locale, refreshProjects]);

  const handleThemeTemplateRowChange = useCallback((id: string, key: 'theme' | 'zhPath' | 'enPath', value: string) => {
    setSettingsSuccess(null);
    setThemeTemplateRows((current) => current.map((row) => (row.id === id ? { ...row, [key]: value } : row)));
  }, []);

  const handleVideoProjectChange = useCallback(() => {
    void refreshProjects();
  }, [refreshProjects]);

  const handleWorkspaceTabChange = useCallback((nextTab: WorkspaceTab) => {
    if (nextTab === activeWorkspaceTab) return;
    if (!window.confirm(t('workspaceSwitchConfirm'))) return;
    setActiveWorkspaceTab(nextTab);
    setSelectedVideoState(null);
  }, [activeWorkspaceTab, t]);

  const handleAddThemeTemplateRow = useCallback(() => {
    setSettingsSuccess(null);
    setThemeTemplateRows((current) => [
      ...current,
      {
        id: `row-${Date.now()}`,
        theme: '',
        zhPath: templateOptions[0]?.path || '',
        enPath: templateOptions[0]?.path || '',
      },
    ]);
  }, [templateOptions]);

  const handleRemoveThemeTemplateRow = useCallback((id: string) => {
    setSettingsSuccess(null);
    setThemeTemplateRows((current) => current.filter((row) => row.id !== id));
  }, []);

  const handleMediaPromptTemplateRowChange = useCallback((id: string, key: 'key' | 'zhPath' | 'enPath', value: string) => {
    setSettingsSuccess(null);
    setMediaPromptTemplateRows((current) => current.map((row) => (row.id === id ? { ...row, [key]: value } : row)));
  }, []);

  const handleAddMediaPromptTemplateRow = useCallback(() => {
    setSettingsSuccess(null);
    setMediaPromptTemplateRows((current) => [
      ...current,
      {
        id: `row-${Date.now()}`,
        key: '',
        zhPath: templateOptions[0]?.path || '',
        enPath: templateOptions[0]?.path || '',
      },
    ]);
  }, [templateOptions]);

  const handleRemoveMediaPromptTemplateRow = useCallback((id: string) => {
    setSettingsSuccess(null);
    setMediaPromptTemplateRows((current) => current.filter((row) => row.id !== id));
  }, []);

  const handleUploadTemplate = useCallback(async (file: File | null) => {
    if (!file) return;
    setTemplateUploading(true);
    setSettingsError(null);
    setSettingsSuccess(null);
    try {
      const uploaded = await uploadTemplate(file);
      const templates = await listTemplateOptions();
      setTemplateOptions(templates);
      setPendingTemplateZhSelection(uploaded.path);
      setPendingTemplateEnSelection(uploaded.path);
    } catch (error) {
      setSettingsError(getLocalizedError(error, '上传模板失败', 'Failed to upload template', locale));
    } finally {
      setTemplateUploading(false);
    }
  }, [locale]);

  const handleAddPendingThemeTemplate = useCallback(() => {
    const theme = pendingTemplateTheme.trim();
    if (!theme || (!pendingTemplateZhSelection && !pendingTemplateEnSelection)) {
      setSettingsError(locale === 'zh' ? '请先填写主题名并选择至少一个模板文件' : 'Enter a theme and choose at least one template file');
      return;
    }
    setSettingsError(null);
    setSettingsSuccess(null);
    setThemeTemplateRows((current) => [
      ...current,
      {
        id: `row-${Date.now()}`,
        theme,
        zhPath: pendingTemplateZhSelection,
        enPath: pendingTemplateEnSelection,
      },
    ]);
    setPendingTemplateTheme('');
  }, [locale, pendingTemplateEnSelection, pendingTemplateTheme, pendingTemplateZhSelection]);

  const handleUploadVoice = useCallback(async () => {
    if (!pendingVoiceUpload.name.trim() || !pendingVoiceUpload.file) {
      setSettingsError(locale === 'zh' ? '请先填写音色名称并选择声纹文件' : 'Enter a voice name and choose a voice file');
      return;
    }
    setVoiceUploading(true);
    setSettingsError(null);
    setSettingsSuccess(null);
    try {
      const uploaded = await uploadVoice(pendingVoiceUpload.file);
      setSettingsData((current) => ({
        ...current,
        voices: [...current.voices, { name: pendingVoiceUpload.name.trim(), file_path: uploaded.path }],
      }));
      setPendingVoiceUpload({ name: '', file: null });
    } catch (error) {
      setSettingsError(getLocalizedError(error, '上传声纹失败', 'Failed to upload voice asset', locale));
    } finally {
      setVoiceUploading(false);
    }
  }, [locale, pendingVoiceUpload]);

  const handleRemoveVoice = useCallback((name: string) => {
    setSettingsSuccess(null);
    setSettingsData((current) => ({
      ...current,
      voices: current.voices.filter((voice) => voice.name !== name),
    }));
  }, []);

  const handleSaveSettings = useCallback(async () => {
    setSettingsSaving(true);
    setSettingsError(null);
    setSettingsSuccess(null);
    try {
      const payload: SettingsData = {
        ...settingsData,
        default_language: locale,
        theme2text_templates: createThemeTemplateMap(themeTemplateRows),
        media_prompt_templates: createMediaPromptTemplateMap(mediaPromptTemplateRows),
      };
      const response = await saveSettings(payload);
      setSettingsData(response.settings);
      setSettingsDefaults({
        default_language: response.settings.default_language,
        default_text_model_name: response.settings.default_text_model_name,
        default_audio_model_name: response.settings.default_audio_model_name,
        default_image_model_name: response.settings.default_image_model_name,
        voices: response.settings.voices,
      });
      setThemeTemplateRows(createThemeTemplateRows(response.settings));
      setMediaPromptTemplateRows(createMediaPromptTemplateRows(response.settings));
      setLocale(response.settings.default_language);
      setSettingsSuccess(t('settingsSaved'));
    } catch (error) {
      setSettingsError(getLocalizedError(error, '保存设置失败', 'Failed to save settings', locale));
    } finally {
      setSettingsSaving(false);
    }
  }, [mediaPromptTemplateRows, locale, settingsData, t, themeTemplateRows]);

  const localizedWorkspaceTabs = useMemo(
    () => workspaceTabs.map((tab) => ({ ...tab, label: t(tab.labelKey), description: t(tab.descriptionKey) })),
    [t],
  );
  const languageOptions = useMemo(
    () => (Object.keys(localeLabels) as Locale[]).map((value) => ({ value, label: localeLabels[value] })),
    [],
  );
  const styleOptions = useMemo(
    () => ['温柔', '励志', '科普', '幽默', '严肃'].map((value) => ({ value, label: getStyleLabel(value, locale) })),
    [locale],
  );

  return (
    <div className="container mx-auto max-w-[1600px] px-4 py-8 text-foreground">
      <header className="mb-8 panel-surface px-6 py-6">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 shadow-lg">
              <Video className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="bg-gradient-to-r from-sky-300 via-blue-300 to-violet-300 bg-clip-text text-2xl font-bold text-transparent">
                Mindawaker
              </h1>
              <p className="text-sm text-slate-300">{t('appSubtitle')}</p>
            </div>
          </div>

          <div className="flex flex-col gap-3 lg:items-end">
            <div className="flex items-center gap-2">
              <Label className="text-slate-200">{t('language')}</Label>
              <Select value={locale} onValueChange={(value) => setLocale(value as Locale)}>
                <SelectTrigger className="w-[140px] bg-slate-900/70 text-slate-100">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {languageOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <nav className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-slate-900/70 p-2">
              <Button variant={activeTab === 'workspace' ? 'default' : 'ghost'} onClick={() => setActiveTab('workspace')} className="gap-2">
                <Sparkles className="h-4 w-4" />
                {t('workspace')}
              </Button>
              <Button variant={activeTab === 'projects' ? 'default' : 'ghost'} onClick={() => setActiveTab('projects')} className="gap-2 text-slate-200">
                <History className="h-4 w-4" />
                {t('projects')}
              </Button>
              <Button variant={activeTab === 'settings' ? 'default' : 'ghost'} onClick={() => setActiveTab('settings')} className="gap-2 text-slate-200">
                <Settings className="h-4 w-4" />
                {t('settings')}
              </Button>
            </nav>
          </div>
        </div>
      </header>

      <main className="space-y-6">
        {activeTab === 'workspace' && (
          <>
            <section className="panel-surface space-y-5 px-5 py-5">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-slate-50">{t('generatorModules')}</h2>
                  <p className="text-sm text-slate-300">{t('generatorModulesDesc')}</p>
                </div>
                <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-4 py-2 text-sm text-amber-100">
                  {t('workspaceSwitchWarning')}
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
                {localizedWorkspaceTabs.map((tab) => {
                  const Icon = tab.icon;
                  const selected = activeWorkspaceTab === tab.key;
                  return (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => handleWorkspaceTabChange(tab.key)}
                      className={`rounded-2xl border p-4 text-left transition-all ${
                        selected
                          ? 'border-sky-400/60 bg-sky-500/15 shadow-lg ring-2 ring-sky-400/30'
                          : 'border-white/10 bg-slate-900/70 hover:border-slate-500 hover:bg-slate-800/80'
                      }`}
                    >
                      <div className="mb-3 flex items-center justify-between">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 text-white">
                          <Icon className="h-5 w-5" />
                        </div>
                        {selected && <Badge variant="processing">{t('current')}</Badge>}
                      </div>
                      <h2 className="font-semibold text-slate-50">{tab.label}</h2>
                      <p className="mt-1 text-sm text-slate-300">{tab.description}</p>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="panel-subtle p-1">
              {activeWorkspaceTab === 'video' && (
                <VideoGenerator
                  initialState={selectedVideoState}
                  defaults={settingsDefaults}
                  onProjectChange={handleVideoProjectChange}
                  locale={locale}
                />
              )}
              {activeWorkspaceTab === 'text' && <TextGenerator defaults={settingsDefaults} locale={locale} />}
              {activeWorkspaceTab === 'audio' && <AudioGenerator defaults={settingsDefaults} locale={locale} />}
              {activeWorkspaceTab === 'image' && <ImageGenerator defaults={settingsDefaults} locale={locale} />}
            </section>
          </>
        )}

        {activeTab === 'projects' && (
          <div className="panel-surface space-y-4 px-5 py-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold">{t('projectsTitle')}</h2>
                <p className="text-sm text-muted-foreground">{t('projectsDesc')}</p>
              </div>
              <Button variant="outline" onClick={() => void refreshProjects()} disabled={projectsLoading}>
                <RefreshCw className={`mr-2 h-4 w-4 ${projectsLoading ? 'animate-spin' : ''}`} />
                {t('refresh')}
              </Button>
            </div>

            {projectsError && (
              <Card className="border-red-400/30 bg-red-500/10">
                <CardContent className="pt-6 text-sm text-red-200">{projectsError}</CardContent>
              </Card>
            )}

            {projectsWarning && projectsWarning.invalid_meta_count > 0 && (
              <Card className="border-amber-400/30 bg-amber-500/10">
                <CardContent className="pt-6 text-sm text-amber-100">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
                    <div className="space-y-1">
                      <p>{t('skippedBrokenProjects', { count: projectsWarning.invalid_meta_count })}</p>
                      <p>{t('recoverBrokenProjects')}</p>
                      {projectsWarning.invalid_meta_projects.length > 0 && (
                        <p className="break-all text-xs text-amber-200">
                          {t('projectIds', { ids: projectsWarning.invalid_meta_projects.join('、') })}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {!projectsLoading && projects.length === 0 && (
              <Card>
                <CardContent className="pt-6 text-sm text-muted-foreground">{t('noSavedProjects')}</CardContent>
              </Card>
            )}

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {projects.map((project) => {
                const isBusy = historyBusyProjectId === project.project_id;
                return (
                  <Card key={project.project_id} className="transition-shadow hover:shadow-lg">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <CardTitle className="text-lg">{project.name || project.project_id}</CardTitle>
                          <CardDescription>{formatProjectUpdatedAt(project.updated_at, locale)}</CardDescription>
                        </div>
                        <Badge
                          variant={project.status === 'completed' ? 'success' : project.status === 'error' ? 'destructive' : 'processing'}
                        >
                          {getProjectDisplayStatus(project.status, locale)}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2 text-sm text-muted-foreground">
                        <div>{t('projectIdLabel')}: {project.project_id}</div>
                        <div>{t('stageLabel')}: {project.stage || '-'}</div>
                        <div className="flex items-center justify-between">
                          <span>{t('progressLabel')}</span>
                          <span className="font-medium text-foreground">{project.progress ?? 0}%</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-secondary">
                          <div className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-500" style={{ width: `${project.progress ?? 0}%` }} />
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" disabled={isBusy} onClick={() => void handleLoadProject(project.project_id)}>
                          {isBusy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : null}
                          {t('loadProject')}
                        </Button>
                        {isProjectRecoverable(project) && (
                          <Button size="sm" disabled={isBusy} onClick={() => void handleRebuildProject(project.project_id)}>
                            {isBusy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : null}
                            {t('rebuildProject')}
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="panel-surface space-y-6 px-5 py-5">
            <Card>
              <CardHeader>
                <CardTitle>{t('systemSettings')}</CardTitle>
                <CardDescription>{t('systemSettingsDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {settingsLoading && <p className="text-sm text-muted-foreground">{t('loadingSettings')}</p>}
                {settingsError && <div className="rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{settingsError}</div>}
                {settingsSuccess && <div className="rounded-md border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{settingsSuccess}</div>}

                <section className="space-y-4">
                  <div>
                    <h3 className="font-semibold">{t('defaultModelConfig')}</h3>
                    <p className="text-sm text-muted-foreground">{t('defaultModelConfigDesc')}</p>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <div className="space-y-2">
                      <Label>{t('defaultLanguage')}</Label>
                      <Select
                        value={settingsData.default_language}
                        onValueChange={(value) => {
                          const next = value as Locale;
                          setLocale(next);
                          setSettingsData((current) => ({ ...current, default_language: next }));
                        }}
                      >
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {languageOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>{t('defaultTextModel')}</Label>
                      <Select value={settingsData.default_text_model_name} onValueChange={(value) => setSettingsData((current) => ({ ...current, default_text_model_name: value }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {textModels.map((model) => <SelectItem key={model.value} value={model.value}>{model.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>{t('defaultImageModel')}</Label>
                      <Select value={settingsData.default_image_model_name} onValueChange={(value) => setSettingsData((current) => ({ ...current, default_image_model_name: value }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {imageModels.map((model) => <SelectItem key={model.value} value={model.value}>{model.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>{t('defaultAudioModel')}</Label>
                      <Select value={settingsData.default_audio_model_name} onValueChange={(value) => setSettingsData((current) => ({ ...current, default_audio_model_name: value }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {audioModels.map((model) => <SelectItem key={model.value} value={model.value}>{model.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>

                  </div>
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="font-semibold">{t('imageConsistency')}</h3>
                  </div>
                  <div className="flex items-center gap-3">
                    <input
                      id="enable-image-consistency"
                      type="checkbox"
                      checked={settingsData.enable_image_consistency}
                      onChange={(e) => setSettingsData((current) => ({ ...current, enable_image_consistency: e.target.checked }))}
                    />
                    <Label htmlFor="enable-image-consistency">{t('enableImageConsistency')}</Label>
                  </div>
                  <div className="max-w-xs space-y-2">
                    <Label htmlFor="image-consistency-weight">{t('consistencyWeight')}</Label>
                    <Input
                      id="image-consistency-weight"
                      type="number"
                      step="0.1"
                      value={settingsData.image_consistency_weight}
                      onChange={(e) => setSettingsData((current) => ({ ...current, image_consistency_weight: Number(e.target.value) || 0 }))}
                    />
                  </div>
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="font-semibold">{t('themeTemplateMapping')}</h3>
                    <p className="text-sm text-muted-foreground">{t('themeTemplateMappingDesc')}</p>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_auto]">
                    <div className="space-y-2">
                      <Label htmlFor="pending-theme">{t('themeName')}</Label>
                      <Input id="pending-theme" value={pendingTemplateTheme} onChange={(e) => setPendingTemplateTheme(e.target.value)} placeholder={locale === 'zh' ? '例如：温柔 / 科普' : 'For example: Gentle / Educational'} />
                    </div>
                    <div className="space-y-2">
                      <Label>{t('zhTemplate')}</Label>
                      <Select value={pendingTemplateZhSelection} onValueChange={setPendingTemplateZhSelection}>
                        <SelectTrigger><SelectValue placeholder={t('templateFile')} /></SelectTrigger>
                        <SelectContent>
                          {templateOptions.map((option) => (
                            <SelectItem key={`pending-zh-${option.path}`} value={option.path}>{option.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>{t('enTemplate')}</Label>
                      <Select value={pendingTemplateEnSelection} onValueChange={setPendingTemplateEnSelection}>
                        <SelectTrigger><SelectValue placeholder={t('templateFile')} /></SelectTrigger>
                        <SelectContent>
                          {templateOptions.map((option) => (
                            <SelectItem key={`pending-en-${option.path}`} value={option.path}>{option.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-end">
                      <Button onClick={handleAddPendingThemeTemplate}>{t('addMapping')}</Button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="template-upload">{t('uploadTemplate')}</Label>
                    <Input id="template-upload" type="file" onChange={(e) => void handleUploadTemplate(e.target.files?.[0] || null)} disabled={templateUploading} />
                    {templateUploading && <p className="text-xs text-muted-foreground">{t('templateUploading')}</p>}
                  </div>

                  <div className="space-y-3">
                    {themeTemplateRows.map((row) => (
                      <div key={row.id} className="grid gap-3 rounded-lg border p-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
                        <Input value={row.theme} onChange={(e) => handleThemeTemplateRowChange(row.id, 'theme', e.target.value)} placeholder={t('themeName')} />
                        <Select value={row.zhPath} onValueChange={(value) => handleThemeTemplateRowChange(row.id, 'zhPath', value)}>
                          <SelectTrigger><SelectValue placeholder={t('zhTemplate')} /></SelectTrigger>
                          <SelectContent>
                            {templateOptions.map((option) => (
                              <SelectItem key={`row-zh-${row.id}-${option.path}`} value={option.path}>{option.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Select value={row.enPath} onValueChange={(value) => handleThemeTemplateRowChange(row.id, 'enPath', value)}>
                          <SelectTrigger><SelectValue placeholder={t('enTemplate')} /></SelectTrigger>
                          <SelectContent>
                            {templateOptions.map((option) => (
                              <SelectItem key={`row-en-${row.id}-${option.path}`} value={option.path}>{option.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button type="button" variant="outline" onClick={() => handleRemoveThemeTemplateRow(row.id)}>
                          <X className="mr-2 h-4 w-4" />{t('delete')}
                        </Button>
                      </div>
                    ))}
                    <Button type="button" variant="outline" onClick={handleAddThemeTemplateRow}>{t('addEmptyMapping')}</Button>
                  </div>
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="font-semibold">{t('mediaPromptTemplateMapping')}</h3>
                    <p className="text-sm text-muted-foreground">{t('mediaPromptTemplateMappingDesc')}</p>
                  </div>

                  <div className="space-y-3">
                    {mediaPromptTemplateRows.map((row) => (
                      <div key={row.id} className="grid gap-3 rounded-lg border p-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
                        <Input value={row.key} onChange={(e) => handleMediaPromptTemplateRowChange(row.id, 'key', e.target.value)} placeholder={t('defaultTemplateKey')} />
                        <Select value={row.zhPath} onValueChange={(value) => handleMediaPromptTemplateRowChange(row.id, 'zhPath', value)}>
                          <SelectTrigger><SelectValue placeholder={t('zhTemplate')} /></SelectTrigger>
                          <SelectContent>
                            {templateOptions.map((option) => (
                              <SelectItem key={`media-row-zh-${row.id}-${option.path}`} value={option.path}>{option.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Select value={row.enPath} onValueChange={(value) => handleMediaPromptTemplateRowChange(row.id, 'enPath', value)}>
                          <SelectTrigger><SelectValue placeholder={t('enTemplate')} /></SelectTrigger>
                          <SelectContent>
                            {templateOptions.map((option) => (
                              <SelectItem key={`media-row-en-${row.id}-${option.path}`} value={option.path}>{option.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button type="button" variant="outline" onClick={() => handleRemoveMediaPromptTemplateRow(row.id)}>
                          <X className="mr-2 h-4 w-4" />{t('delete')}
                        </Button>
                      </div>
                    ))}
                    <Button type="button" variant="outline" onClick={handleAddMediaPromptTemplateRow}>{t('addEmptyMapping')}</Button>
                  </div>
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="font-semibold">{t('voiceManagement')}</h3>
                    <p className="text-sm text-muted-foreground">{t('voiceManagementDesc')}</p>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto]">
                    <div className="space-y-2">
                      <Label htmlFor="voice-name">{t('voiceName')}</Label>
                      <Input id="voice-name" value={pendingVoiceUpload.name} onChange={(e) => setPendingVoiceUpload((current) => ({ ...current, name: e.target.value }))} placeholder={locale === 'zh' ? '例如：me2' : 'For example: me2'} />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="voice-upload">{t('voiceFile')}</Label>
                      <Input id="voice-upload" type="file" onChange={(e) => setPendingVoiceUpload((current) => ({ ...current, file: e.target.files?.[0] || null }))} />
                    </div>
                    <div className="flex items-end">
                      <Button onClick={() => void handleUploadVoice()} disabled={voiceUploading}>
                        <Upload className="mr-2 h-4 w-4" />
                        {voiceUploading ? t('uploading') : t('uploadAndAdd')}
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {settingsData.voices.map((voice) => (
                      <div key={`${voice.name}-${voice.file_path}`} className="flex items-center justify-between gap-3 rounded-lg border p-3">
                        <div className="min-w-0">
                          <div className="font-medium">{voice.name}</div>
                          <div className="break-all text-xs text-muted-foreground">{voice.file_path}</div>
                        </div>
                        <Button type="button" variant="outline" onClick={() => handleRemoveVoice(voice.name)}>
                          <X className="mr-2 h-4 w-4" />{t('delete')}
                        </Button>
                      </div>
                    ))}
                  </div>
                </section>

                <div className="flex justify-end">
                  <Button onClick={() => void handleSaveSettings()} disabled={settingsSaving || settingsLoading}>
                    {settingsSaving ? t('saving') : t('saveSettings')}
                  </Button>
                </div>

                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>{t('currentTemplateFiles', { value: templateOptions.map((item) => item.name).join('、') || t('none') })}</p>
                  <p>{t('currentThemeMappings', { value: themeTemplateRows.map((row) => formatThemeTemplateSummary(row, locale)).join('、') || t('none') })}</p>
                  <p>{t('currentMediaPromptMappings', { value: mediaPromptTemplateRows.map((row) => formatMediaPromptTemplateSummary(row, locale)).join('、') || t('none') })}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
