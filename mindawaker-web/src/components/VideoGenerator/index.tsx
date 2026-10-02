'use client';

import { useState, useCallback, ChangeEvent, useEffect, useMemo } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import StoryChapters from './StoryChapters';
import ClipSettings from './ClipSettings';
import SceneStudioLink from './SceneStudioLink';
import { getPromptText } from '@/lib/promptText';
import { Play, Pause, RotateCcw, CheckCircle2, AlertCircle, Loader2, Upload, X, Download, Mic2, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useTask,
  applyRedrawSelection,
  createVideoTask,
  rebuildProject,
  rebuildClips,
  concatClips,
  saveProject,
  createEmptyVideoConfig,
  getVideoConfigFromSnapshot,
  getVideoStateFromLoadResponse,
  mergeVideoConfig,
  type AudioItemConfig,
  type ImageItemConfig,
  type VideoConfig,
  type VideoConfigDefaults,
  type VideoGeneratorState,
} from '@/hooks/useTask';
import { getStyleLabel, translate, type Locale } from '@/lib/i18n';

const isStoryStyle = (style?: string) => style === 'story';

type AssetTab = 'images' | 'audios' | 'clips';

import type { SettingsDefaults } from '@/hooks/useSettings';

function toVideoDefaults(defaults?: SettingsDefaults | null): VideoConfigDefaults | undefined {
  if (!defaults) return undefined;
  return defaults;
}

function applyDefaultVideoConfig(config: VideoConfig, defaults?: SettingsDefaults | null): VideoConfig {
  if (!defaults) return config;
  return {
    ...config,
    text_model_name: config.text_model_name || defaults.default_text_model_name || 'deepseek',
    image_model_name: config.image_model_name || defaults.default_image_model_name || 'jimeng',
    audio_model_name: config.audio_model_name || defaults.default_audio_model_name || 'azure',
    voice: config.voice || defaults.voices?.[0]?.name || 'zh-CN-YunxiNeural',
  };
}


interface VideoGeneratorProps {
  initialState?: VideoGeneratorState | null;
  onProjectChange?: (projectId: string | null) => void;
  defaults?: SettingsDefaults | null;
  locale?: Locale;
}

function formatDurationLabel(duration?: number) {
  if (typeof duration !== 'number' || Number.isNaN(duration)) return '--';
  return `${duration.toFixed(1)}s`;
}

function formatHistoryTime(locale: Locale, value?: number) {
  if (!value) return locale === 'zh' ? '刚刚' : 'Just now';
  return new Date(value * 1000).toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en', { hour: '2-digit', minute: '2-digit' });
}


























































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































import { generateAudio } from '@/hooks/useAudioGeneration';
import { generateImage } from '@/hooks/useImageGeneration';
import { getAssetUrl, triggerDownload } from '@/lib/generated-files';

const stepKeys = [
  { id: 'text', labelKey: 'videoStepText', descriptionKey: 'videoStepTextDesc' },
  { id: 'audio', labelKey: 'videoStepAudio', descriptionKey: 'videoStepAudioDesc' },
  { id: 'image', labelKey: 'videoStepImage', descriptionKey: 'videoStepImageDesc' },
  { id: 'video', labelKey: 'videoStepClip', descriptionKey: 'videoStepClipDesc' },
  { id: 'concat', labelKey: 'videoStepConcat', descriptionKey: 'videoStepConcatDesc' },
] as const;

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

export default function VideoGenerator({ initialState, onProjectChange, defaults, locale = 'zh' }: VideoGeneratorProps = {}) {
  const t = useCallback(
    (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  );

  const steps = stepKeys.map((step) => ({
    id: step.id,
    label: t(step.labelKey),
    description: t(step.descriptionKey),
  }));

  const [config, setConfig] = useState<VideoConfig>(() =>
    mergeVideoConfig(createEmptyVideoConfig(toVideoDefaults(defaults)), initialState?.config)
  );

  const requiredFieldLabels = [
    !config.theme && !config.article ? t('themeOrUploadDoc') : null,
  ].filter(Boolean) as string[];
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);

  const [taskId, setTaskId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(initialState?.projectId ?? null);
  const [showResult, setShowResult] = useState(Boolean(initialState?.status?.result?.video_path));
  const [fileName, setFileName] = useState<string>('');
  const [fileError, setFileError] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [isRebuildingClips, setIsRebuildingClips] = useState(false);
  const [isConcatingClips, setIsConcatingClips] = useState(false);
  const [isApplyingUpdate, setIsApplyingUpdate] = useState(false);
  const [manualStatus, setManualStatus] = useState<VideoGeneratorState['status']>(initialState?.status ?? null);
  const [imageRevisions, setImageRevisions] = useState<Record<number, number>>({});
  const [redrawingImageIndex, setRedrawingImageIndex] = useState<number | null>(null);
  const [redrawingAudioIndex, setRedrawingAudioIndex] = useState<number | null>(null);
  const [expandedImageSettingsIndex, setExpandedImageSettingsIndex] = useState<number | null>(null);
  const [expandedAudioSettingsIndex, setExpandedAudioSettingsIndex] = useState<number | null>(null);
  const [imageDraftConfigs, setImageDraftConfigs] = useState<Record<number, ImageItemConfig>>({});
  const [audioDraftConfigs, setAudioDraftConfigs] = useState<Record<number, AudioItemConfig>>({});
  const [selectedImageHistory, setSelectedImageHistory] = useState<Record<number, number>>({});
  const [selectedAudioHistory, setSelectedAudioHistory] = useState<Record<number, number>>({});
  const [lastAppliedImageHistory, setLastAppliedImageHistory] = useState<Record<number, number>>({});
  const [lastAppliedAudioHistory, setLastAppliedAudioHistory] = useState<Record<number, number>>({});
  const [hasPendingSelectionChanges, setHasPendingSelectionChanges] = useState(false);
  const [assetTab, setAssetTab] = useState<AssetTab>(initialState?.status?.result?.clips?.length ? 'clips' : (initialState?.status?.result?.images?.length ? 'images' : 'audios'));

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleProgress = useCallback((status: any) => {
    console.log('Progress:', status);
  }, []);

  const handleComplete = useCallback((completedStatus?: any) => {
    const pipelineStatus = completedStatus?.pipeline_status;
      if (pipelineStatus === 'in_video_concat' || completedStatus?.result?.video_path) {
      setAssetTab('clips');
      setShowResult(true);
      return;
    }
    if (pipelineStatus === 'in_video_rebuild' || completedStatus?.result?.clips) {
      setAssetTab('clips');
      setShowResult(false);
      return;
    }
    setShowResult(true);
  }, []);

  const handleError = useCallback((error: string) => {
    console.error('Task error:', error);
    setErrorMessage(error);
  }, []);

  const { status, setStatus, connect, disconnect, cancel } = useTask({
    onProgress: handleProgress,
    onComplete: handleComplete,
    onError: handleError,
  });

  const currentStatus = status ?? manualStatus;
  const videoAssetUrl = getAssetUrl(currentStatus?.result?.video_path);
  const videoUrl = videoAssetUrl && currentStatus?.status === 'completed'
    ? `${videoAssetUrl}${videoAssetUrl.includes('?') ? '&' : '?'}v=${encodeURIComponent(currentStatus.id + currentStatus.updated_at)}`
    : videoAssetUrl;
  const imageHistoryItems = currentStatus?.result?.image_redraw_history ?? [];
  const audioHistoryItems = currentStatus?.result?.audio_redraw_history ?? [];
  const statusForRender = currentStatus;
  const currentProjectId = currentStatus?.project_id || projectId || null;
  const result = statusForRender?.result;
  const imageItems = result?.images ?? [];
  const audioItems = result?.audios ?? [];
  const clipItems = result?.clips ?? [];
  const expectedClipCount = Math.max(imageItems.length, audioItems.length, result?.lines?.length ?? 0);
  const dirtyClipCount = clipItems.filter((item) => item?.dirty || !item?.clip_path).length
    + Math.max(0, expectedClipCount - clipItems.length);
  const promptItems = useMemo(() => (result?.prompts ?? []).map(getPromptText), [result?.prompts]);
  const lineItems = result?.lines ?? [];
  const durationItems = result?.durations ?? [];
  const imageConfigItems = useMemo(() => (result?.images_configs ?? []).map((item) => ({
    ...item,
    prompt: getPromptText(item?.prompt) || getPromptText(item?.text),
    text: getPromptText(item?.text) || getPromptText(item?.prompt),
  })), [result?.images_configs]);
  const audioConfigItems = result?.audios_configs ?? [];
  const isRunning = !!statusForRender?.id && (statusForRender.status === 'running' || statusForRender.status === 'pending');
  const mediaReady = expectedClipCount > 0 && imageItems.length === expectedClipCount
    && audioItems.length === expectedClipCount && durationItems.length === expectedClipCount
    && imageItems.every(Boolean) && audioItems.every(Boolean);
  const canRebuildClips = !!currentProjectId && mediaReady && dirtyClipCount > 0 && !isRunning;
  const canConcatClips = !!currentProjectId && clipItems.length > 0 && dirtyClipCount === 0 && !isRunning;

  useEffect(() => {
    if (!initialState) return;
    setProjectId(initialState.projectId);
    setConfig(mergeVideoConfig(createEmptyVideoConfig(toVideoDefaults(defaults)), initialState.config));
    setManualStatus(initialState.status);
    setShowResult(Boolean(initialState.status?.result?.video_path));
  }, [defaults, initialState]);

  useEffect(() => {
    if (!defaults || didApplyDefaults || initialState?.config) return;
    setConfig((current) => applyDefaultVideoConfig(current, defaults));
    setDidApplyDefaults(true);
  }, [defaults, didApplyDefaults, initialState?.config]);

  useEffect(() => {
    const imageHistory = currentStatus?.result?.image_redraw_history ?? [];
    const audioHistory = currentStatus?.result?.audio_redraw_history ?? [];
    const nextImageConfigs: Record<number, ImageItemConfig> = {};
    const nextAudioConfigs: Record<number, AudioItemConfig> = {};

    const nextImageSelection: Record<number, number> = {};
    imageHistory.forEach((items, index) => {
      const selectedIndex = items.findIndex((item) => item?.is_current);
      nextImageSelection[index] = selectedIndex >= 0 ? selectedIndex : 0;
    });

    const nextAudioSelection: Record<number, number> = {};
    audioHistory.forEach((items, index) => {
      const selectedIndex = items.findIndex((item) => item?.is_current);
      nextAudioSelection[index] = selectedIndex >= 0 ? selectedIndex : 0;
    });

    (currentStatus?.result?.images_configs ?? []).forEach((item, index) => {
      nextImageConfigs[index] = {
        image_model_name: item?.image_model_name || config.image_model_name,
        prompt: getPromptText(item?.prompt) || getPromptText(item?.text) || getPromptText(currentStatus?.result?.prompts?.[index]),
        text: getPromptText(item?.text) || getPromptText(item?.prompt) || getPromptText(currentStatus?.result?.prompts?.[index]),
        n: item?.n || 1,
        size: item?.size || config.size,
      };
    });

    (currentStatus?.result?.audios_configs ?? []).forEach((item, index) => {
      nextAudioConfigs[index] = {
        audio_model_name: item?.audio_model_name || config.audio_model_name,
        text: item?.text || currentStatus?.result?.lines?.[index] || '',
        voice: item?.voice || config.voice,
      };
    });

    setImageDraftConfigs(nextImageConfigs);
    setAudioDraftConfigs(nextAudioConfigs);
    setSelectedImageHistory(nextImageSelection);
    setSelectedAudioHistory(nextAudioSelection);
    setLastAppliedImageHistory(nextImageSelection);
    setLastAppliedAudioHistory(nextAudioSelection);
    setHasPendingSelectionChanges(false);
  }, [config.audio_model_name, config.image_model_name, config.size, config.voice, currentStatus]);

  useEffect(() => {
    const imageChanged = Object.keys(selectedImageHistory).some((key) => selectedImageHistory[Number(key)] !== lastAppliedImageHistory[Number(key)]);
    const audioChanged = Object.keys(selectedAudioHistory).some((key) => selectedAudioHistory[Number(key)] !== lastAppliedAudioHistory[Number(key)]);
    setHasPendingSelectionChanges(imageChanged || audioChanged);
  }, [lastAppliedAudioHistory, lastAppliedImageHistory, selectedAudioHistory, selectedImageHistory]);


  useEffect(() => {
    onProjectChange?.(projectId);
  }, [onProjectChange, projectId]);


  useEffect(() => {
    if (currentStatus?.project_id) {
      setProjectId(currentStatus.project_id);
    }
  }, [currentStatus?.project_id]);

  useEffect(() => {
    if (status) {
      setManualStatus(status);
    }
  }, [status]);

  const getErrorMessage = useCallback(
    (error: unknown, key: Parameters<typeof translate>[1]) => {
      const message = error && typeof error === 'object' && 'message' in error ? String((error as { message?: string }).message || '') : '';
      return message || t(key);
    },
    [t],
  );

  const getDirtyClipLabel = useCallback(
    (count: number) => t('dirtyClipsCount', { count }),
    [t],
  );

  const getCandidateLabel = useCallback(
    (index: number) => (index === 0 ? t('currentVersion') : t('candidateVersion', { index })),
    [t],
  );

  const getRequiredFieldMessage = useCallback(() => requiredFieldLabels.join(locale === 'zh' ? '、' : ', '), [locale, requiredFieldLabels]);

  const formatImageCountLabel = useCallback(
    (count: number) => (locale === 'zh' ? `${count} 张` : String(count)),
    [locale],
  );

  const formatCharacterCount = useCallback(
    (count: number) => (locale === 'zh' ? `${count} 字符` : `${count} characters`),
    [locale],
  );

  const formatImageMeta = useCallback(
    (modelName?: string, size?: string) => (locale === 'zh' ? `模型：${modelName || '-'} · 尺寸：${size || '-'}` : `Model: ${modelName || '-'} · Size: ${size || '-'}`),
    [locale],
  );

  const formatAudioMeta = useCallback(
    (modelName?: string, voiceName?: string) => (locale === 'zh' ? `模型：${modelName || '-'} · 音色：${voiceName || '-'}` : `Model: ${modelName || '-'} · Voice: ${voiceName || '-'}`),
    [locale],
  );

  useEffect(() => {
    if (initialState?.status?.id && (initialState.status.status === 'pending' || initialState.status.status === 'running')) {
      setTaskId(initialState.status.id);
      connect(initialState.status.id);
    }
  }, [connect, initialState]);

  const handleFileUpload = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setFileError('');
    setFileName(file.name);

    if (!file.name.endsWith('.txt')) {
      setFileError(t('uploadTxtOnlyError'));
      return;
    }

    if (!config.style?.includes('story') && file.size > 50 * 1024) {
      setFileError(t('fileTooLargeError'));
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;

      if (!config.style?.includes('story') && content.length > 2400) {
        setFileError(t('articleTooLongError'));
        return;
      }

      setConfig((prev: VideoConfig) => ({ ...prev, article: content, theme: '' }));
    };

    reader.onerror = () => {
      setFileError(t('fileReadFailedError'));
    };

    reader.readAsText(file);
  }, [t, config.style]);

  const handleClearFile = useCallback(() => {
    setConfig((prev: VideoConfig) => ({ ...prev, article: '' }));
    setFileName('');
    setFileError('');
  }, []);

  const resetGenerator = useCallback(() => {
    setTaskId(null);
    setShowResult(false);
    setManualStatus(null);
    setProjectId(null);
    setConfig(createEmptyVideoConfig(toVideoDefaults(defaults)));
    setFileName('');
    setFileError('');
    setErrorMessage(null);
  }, []);

  const handleSaveProject = useCallback(async () => {
    if (!currentProjectId) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      await saveProject(currentProjectId);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'saveProjectFailed'));
    } finally {
      setIsSaving(false);
    }
  }, [currentProjectId, getErrorMessage]);

  const handleRebuild = useCallback(async () => {
    if (!currentProjectId) return;
    setIsRebuilding(true);
    setErrorMessage(null);
    setShowResult(false);
    try {
      const promptUpdates = Object.fromEntries(Object.entries(imageDraftConfigs)
        .filter(([index]) => !imageItems[Number(index)])
        .map(([index, draft]) => [index, draft.prompt || draft.text || ''])
        .filter(([, prompt]) => Boolean(prompt)));
      const result = await rebuildProject(currentProjectId, promptUpdates);
      setTaskId(result.task_id);
      connect(result.task_id);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'rebuildProjectFailed'));
    } finally {
      setIsRebuilding(false);
    }
  }, [connect, currentProjectId, getErrorMessage, imageDraftConfigs, imageItems]);

  const handleApplyUpdate = useCallback(async (imageIndex?: number) => {
    if (!currentProjectId || !hasPendingSelectionChanges) return;
    setIsApplyingUpdate(true);
    setErrorMessage(null);
    try {
      const imagePayload = Object.fromEntries(
        Object.entries(selectedImageHistory).filter(([key, value]) => lastAppliedImageHistory[Number(key)] !== value && (imageIndex === undefined || Number(key) === imageIndex)),
      );
      const audioPayload = Object.fromEntries(
        Object.entries(selectedAudioHistory).filter(([key, value]) => imageIndex === undefined && lastAppliedAudioHistory[Number(key)] !== value),
      );
      const response = await applyRedrawSelection(currentProjectId, {
        image_selected_history: imagePayload,
        audio_selected_history: audioPayload,
      });
      const nextState = mergeVideoConfig(createEmptyVideoConfig(), getVideoConfigFromSnapshot(response.project));
      setConfig(nextState);
      const snapshotStatus = getVideoStateFromLoadResponse({
        project_id: response.project_id,
        loaded: true,
        project: response.project,
      }).status;
      const nextStatus = snapshotStatus ? { ...snapshotStatus, status: 'completed' as const, done: true } : null;
      setStatus(nextStatus);
      setManualStatus(nextStatus);
      setImageRevisions((previous) => ({
        ...previous,
        ...Object.fromEntries(Object.keys(imagePayload).map((index) => [index, Date.now()])),
      }));
      setProjectId(response.project_id);
      setLastAppliedImageHistory((previous) => ({ ...previous, ...imagePayload }));
      setLastAppliedAudioHistory((previous) => ({ ...previous, ...audioPayload }));
      setHasPendingSelectionChanges(false);
      setShowResult(false);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'updateAssetsFailed'));
    } finally {
      setIsApplyingUpdate(false);
    }
  }, [currentProjectId, getErrorMessage, hasPendingSelectionChanges, lastAppliedAudioHistory, lastAppliedImageHistory, selectedAudioHistory, selectedImageHistory, setStatus]);

  const handleRebuildClips = useCallback(async () => {
    if (!currentProjectId) return;
    setIsRebuildingClips(true);
    setErrorMessage(null);
    setShowResult(false);
    try {
      const result = await rebuildClips(currentProjectId);
      setTaskId(result.task_id);
      setAssetTab('clips');
      connect(result.task_id);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'rebuildClipsFailed'));
    } finally {
      setIsRebuildingClips(false);
    }
  }, [connect, currentProjectId, getErrorMessage]);

  const handleConcatClips = useCallback(async () => {
    if (!currentProjectId) return;
    setIsConcatingClips(true);
    setErrorMessage(null);
    try {
      const result = await concatClips(currentProjectId);
      setTaskId(result.task_id);
      setAssetTab('clips');
      connect(result.task_id);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'concatClipsFailed'));
    } finally {
      setIsConcatingClips(false);
    }
  }, [connect, currentProjectId, getErrorMessage]);


  const handleStart = async () => {
    setErrorMessage(null);
    setShowResult(false);
    try {
      console.log('Starting task with config:', config);
      const result = await createVideoTask(config, projectId || undefined);
      console.log('Task created:', result);
      setProjectId(result.project_id);
      setTaskId(result.task_id);
      connect(result.task_id);
    } catch (error: any) {
      console.error('Failed to create task:', error);
      setErrorMessage(getErrorMessage(error, 'createTaskFailed'));
    }
  };

  const [isStopping, setIsStopping] = useState(false);
  const [uploadingBackground, setUploadingBackground] = useState<number | null>(null);
  const handleBackgroundUpload = async (index: number, file: File) => {
    if (!currentProjectId) return;
    setUploadingBackground(index);
    setErrorMessage(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch(`/api/project/clip-background?project_id=${encodeURIComponent(currentProjectId)}&index=${index}`, { method: 'POST', body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
      const loaded = getVideoStateFromLoadResponse({ project_id: currentProjectId, loaded: true, project: result.project }).status;
      const nextStatus = loaded ? { ...loaded, status: 'completed' as const, done: true } : null;
      setStatus(nextStatus);
      setManualStatus(nextStatus);
      setShowResult(false);
      setImageRevisions(previous => ({ ...previous, [index]: Date.now() }));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setUploadingBackground(null);
    }
  };
  useEffect(() => { if (!isRunning) setIsStopping(false); }, [isRunning]);
  const handleCancel = async () => {
    const activeTaskId = taskId || statusForRender?.id;
    if (!activeTaskId || isStopping) return;
    setIsStopping(true);
    setErrorMessage(null);
    if (!await cancel(activeTaskId)) {
      setIsStopping(false);
      setErrorMessage(locale === 'zh' ? '停止失败，请重试。' : 'Failed to stop. Please retry.');
    }
  };

  const getCurrentStepId = () => {
    if (!statusForRender) return null;

    const pipelineStatus = statusForRender.pipeline_status;
    if (pipelineStatus === 'in_text_progress') return 'text';
    if (pipelineStatus === 'in_audio_progress') return 'audio';
    if (pipelineStatus === 'in_image_progress') return 'image';
    if (pipelineStatus === 'in_video_progress') return 'video';
    if (pipelineStatus === 'in_video_rebuild') return 'video';
    if (pipelineStatus === 'in_video_concat') return 'concat';

    const stageText = `${statusForRender.stage || ''} ${statusForRender.message || ''}`.toLowerCase();

    if (stageText.includes('提示词') || stageText.includes('文案')) return 'text';
    if (stageText.includes('配音') || stageText.includes('音频')) return 'audio';
    if (stageText.includes('图像')) return 'image';
    if (stageText.includes('拼接') || stageText.includes('整片')) return 'concat';
    if (stageText.includes('字幕') || stageText.includes('视频')) return 'video';

    if (statusForRender.progress >= 100) return 'concat';
    if (statusForRender.progress >= 90) return 'concat';
    if (statusForRender.progress >= 75) return 'video';
    if (statusForRender.progress >= 50) return 'image';
    if (statusForRender.progress > 0) return 'text';

    return null;
  };

  const getStepStatus = (stepId: string) => {
    if (!statusForRender) return 'pending';

    if (statusForRender.status === 'completed') return 'completed';

    const currentStepId = getCurrentStepId();
    const stepIndex = steps.findIndex((s) => s.id === stepId);
    const currentIndex = steps.findIndex((s) => s.id === currentStepId);

    if (currentIndex === -1) return 'pending';
    if (stepIndex < currentIndex) return 'completed';
    if (stepIndex === currentIndex) return 'processing';
    return 'pending';
  };

  const handleImageDraftChange = useCallback((index: number, updates: Partial<ImageItemConfig>) => {
    setImageDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        ...(prev[index] || {}),
        ...updates,
      },
    }));
  }, []);

  const handleAudioDraftChange = useCallback((index: number, updates: Partial<AudioItemConfig>) => {
    setAudioDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        ...(prev[index] || {}),
        ...updates,
      },
    }));
  }, []);

  const handleResetImageDraft = useCallback((index: number) => {
    const imageConfig = imageConfigItems[index] as ImageItemConfig | undefined;
    const prompt = promptItems[index] || imageConfig?.prompt || imageConfig?.text || '';
    setImageDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        image_model_name: config.image_model_name,
        prompt,
        text: prompt,
        n: config.n || 1,
        size: config.size,
      },
    }));
  }, [config.image_model_name, config.n, config.size, imageConfigItems, promptItems]);

  const handleResetAudioDraft = useCallback((index: number) => {
    const audioConfig = audioConfigItems[index] as AudioItemConfig | undefined;
    const text = lineItems[index] || audioConfig?.text || '';
    setAudioDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        audio_model_name: config.audio_model_name,
        text,
        voice: config.voice,
      },
    }));
  }, [audioConfigItems, config.audio_model_name, config.voice, lineItems]);

  const handleRedrawImage = useCallback(async (index: number) => {
    if (!currentProjectId) return;
    const imageConfig = imageConfigItems[index] as ImageItemConfig | undefined;
    const draft = imageDraftConfigs[index] || {};
    const prompt = draft.prompt ?? draft.text ?? promptItems[index] ?? imageConfig?.prompt ?? imageConfig?.text;
    const modelName = draft.image_model_name || imageConfig?.image_model_name || config.image_model_name;
    const size = draft.size || imageConfig?.size || config.size;
    const n = draft.n || imageConfig?.n || 1;
    if (!prompt?.trim() || !modelName) {
      setErrorMessage(t('missingImageRedrawParams'));
      return;
    }

    setRedrawingImageIndex(index);
    setErrorMessage(null);
    try {
      const response = await generateImage(
        {
          prompt,
          image_model_name: modelName,
          size,
          n,
          language: locale,
        },
        { projectId: currentProjectId, index },
      );

      const nextImagePath = response.image_paths?.[0];
      if (!nextImagePath) {
        throw new Error(t('imageRedrawNoResult'));
      }

      if (response.project) {
        const snapshotStatus = getVideoStateFromLoadResponse({
          project_id: currentProjectId,
          loaded: true,
          project: response.project,
        }).status;
        // The synchronous redraw is finished; dirty video clips are waiting for user action.
        const nextStatus = snapshotStatus ? { ...snapshotStatus, status: 'completed' as const, done: true } : null;
        setStatus(nextStatus);
        setManualStatus(nextStatus);
      }
      setImageRevisions((previous) => ({ ...previous, [index]: Date.now() }));
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'imageRedrawFailed'));
    } finally {
      setRedrawingImageIndex(null);
    }
  }, [config.image_model_name, config.size, currentProjectId, getErrorMessage, setStatus, imageConfigItems, imageDraftConfigs, promptItems, t]);

  const handleRedrawAudio = useCallback(async (index: number) => {
    if (!currentProjectId) return;
    const audioConfig = audioConfigItems[index] as AudioItemConfig | undefined;
    const draft = audioDraftConfigs[index] || {};
    const text = lineItems[index] || audioConfig?.text;
    const modelName = draft.audio_model_name || audioConfig?.audio_model_name || config.audio_model_name;
    const voice = draft.voice || audioConfig?.voice || config.voice;
    if (!text || !modelName) {
      setErrorMessage(t('missingAudioRedrawParams'));
      return;
    }

    setRedrawingAudioIndex(index);
    setErrorMessage(null);
    try {
      const response = await generateAudio(
        {
          text,
          audio_model_name: modelName,
          voice,
          language: locale,
        },
        { projectId: currentProjectId, index },
      );

      if (!response.audio_path) {
        throw new Error(t('audioRedrawNoResult'));
      }

      await handleSaveProject();
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'audioRedrawFailed'));
    } finally {
      setRedrawingAudioIndex(null);
    }
  }, [audioConfigItems, audioDraftConfigs, config.audio_model_name, config.voice, currentProjectId, getErrorMessage, handleSaveProject, lineItems, t]);

  const newStoryAction = <Button disabled={isRunning || !config.article?.trim()} onClick={async () => {
    try {
      const response = await fetch('/api/story/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
      window.location.href = `/story/${result.project_id}?locale=${locale}`;
    } catch (error) { setErrorMessage(error instanceof Error ? error.message : String(error)); }
  }}>{locale === 'zh' ? '新建/编辑分阶段故事' : 'Create / edit staged story'}</Button>;

  return (
    <div className="space-y-6">
      {currentProjectId && isStoryStyle(config.style) && <StoryChapters locale={locale} key={currentProjectId} projectId={currentProjectId} disabled={isRunning} onLoad={data => {
        disconnect();
        const next = getVideoStateFromLoadResponse(data);
        setTaskId(null); setStatus(null); setManualStatus(next.status);
        setConfig(mergeVideoConfig(createEmptyVideoConfig(toVideoDefaults(defaults)), next.config));
        setProjectId(next.projectId); setShowResult(Boolean(next.status?.result?.video_path));
        setSelectedImageHistory({}); setSelectedAudioHistory({});
        setLastAppliedImageHistory({}); setLastAppliedAudioHistory({});
        setImageDraftConfigs({}); setAudioDraftConfigs({});
        setExpandedImageSettingsIndex(null); setExpandedAudioSettingsIndex(null);
        setRedrawingImageIndex(null); setRedrawingAudioIndex(null);
        setHasPendingSelectionChanges(false); setImageRevisions({});
        setAssetTab('images'); setFileName(''); setFileError(''); setErrorMessage(null);
        onProjectChange?.(next.projectId);
        if (data.task_id) {
          setTaskId(data.task_id);
          const pending = next.status ? { ...next.status, id: data.task_id, status: 'pending' as const, done: false, stage: locale === 'zh' ? '正在生成当前章节视频' : 'Generating the current chapter video' } : null;
          setStatus(pending); setManualStatus(pending);
          connect(data.task_id);
        }
      }} />}
      {isStoryStyle(config.style) && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ClipSettings locale={locale} config={config} projectId={currentProjectId} disabled={isRunning} onChange={next => { setConfig(current => ({ ...current, ...next })); setShowResult(false); }} />
          <SceneStudioLink locale={locale} projectId={currentProjectId} disabled={isRunning} />
          </div>
          {!currentProjectId && newStoryAction}
        </div>
      )}
      {/* Progress Steps */}
      {statusForRender && (
        <Card className="border-blue-100 bg-blue-50/50">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  {isRunning ? (
                    <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                  ) : statusForRender.status === 'completed' ? (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  ) : statusForRender.status === 'error' ? (
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  ) : null}
                  {t('videoProgress')}
                </CardTitle>
                <CardDescription>{statusForRender.message || statusForRender.stage || t('preparing')}</CardDescription>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-2xl font-bold text-blue-600">{statusForRender.progress}%</span>
                {currentProjectId && (
                  <Badge variant="outline">{t('projectId')}: {currentProjectId}</Badge>
                )}
                {isRunning && (
                  <Button variant="destructive" size="sm" onClick={handleCancel} disabled={isStopping}>
                    <Pause className="w-4 h-4 mr-1" />
                    {isStopping ? (locale === 'zh' ? '正在停止…' : 'Stopping…') : t('cancelTask')}
                  </Button>
                )}
                {statusForRender.status === 'completed' && (
                  <Button variant="outline" size="sm" onClick={resetGenerator}>
                    <RotateCcw className="w-4 h-4 mr-1" />
                    {t('createAnother')}
                  </Button>
                )}
                {currentProjectId && !isRunning && (
                  <Button variant="outline" size="sm" onClick={handleSaveProject} disabled={isSaving}>
                    {isSaving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
                    {t('saveProject')}
                  </Button>
                )}
                {currentProjectId && !isRunning && (
                  <Button variant="default" size="sm" onClick={() => void handleApplyUpdate()} disabled={isApplyingUpdate || !hasPendingSelectionChanges}>
                    {isApplyingUpdate ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
                    {t('updateAssets')}
                  </Button>
                )}
                {currentProjectId && statusForRender.status === 'error' && (
                  <Button variant="default" size="sm" onClick={handleRebuild} disabled={isRebuilding}>
                    {isRebuilding ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RotateCcw className="w-4 h-4 mr-1" />}
                    {t('rebuildProject')}
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={statusForRender.progress} variant="gradient" className="h-3" />
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {steps.map((step) => {
                const stepStatus = getStepStatus(step.id);
                return (
                  <div
                    key={step.id}
                    className={`p-3 rounded-lg border transition-all ${
                      stepStatus === 'completed'
                        ? 'bg-green-50 border-green-200'
                        : stepStatus === 'processing'
                        ? 'bg-blue-50 border-blue-200 ring-2 ring-blue-100'
                        : 'bg-white border-gray-100'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {stepStatus === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                      ) : stepStatus === 'processing' ? (
                        <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border-2 border-gray-200" />
                      )}
                      <span
                        className={`font-medium text-sm ${
                          stepStatus === 'processing' ? 'text-blue-700' : 'text-gray-700'
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{step.description}</p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Configuration Form */}
      {!statusForRender && (
        <Tabs defaultValue="content" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="content">{t('contentSettings')}</TabsTrigger>
            <TabsTrigger value="text">{t('textModel')}</TabsTrigger>
            <TabsTrigger value="audio">{t('audioModel')}</TabsTrigger>
            <TabsTrigger value="image">{t('imageModel')}</TabsTrigger>
          </TabsList>

          <TabsContent value="content" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('videoContentTitle')}</CardTitle>
                <CardDescription>{t('videoContentDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="theme" className="flex items-center gap-1">
                    {t('theme')}
                    {!config.article && <span className="text-red-500">*</span>}
                    {!config.theme && !config.article && (
                      <span className="text-xs text-red-500 font-normal">({t('required')})</span>
                    )}
                  </Label>
                  <Input
                    id="theme"
                    placeholder={t('videoThemePlaceholder')}
                    value={config.theme}
                    onChange={(e) => setConfig({ ...config, theme: e.target.value })}
                    disabled={!!config.article}
                    className={
                      !config.theme && !config.article ? "border-red-300 focus:border-red-500" :
                      config.article ? "bg-gray-50 text-gray-500 cursor-not-allowed" : ""
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="style">{t('writingStyle')}</Label>
                  <Select
                    value={config.style}
                    onValueChange={(value) => setConfig({ ...config, style: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {['温柔', '励志', '科普', '幽默', '严肃', 'story'].map((item) => (
                        <SelectItem key={item} value={item}>
                          {getStyleLabel(item, locale)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {isStoryStyle(config.style) && (
                  <div className="space-y-2">
                    <Label htmlFor="file-upload" className="flex items-center gap-1">
                      {t('uploadDocumentTxt')}
                    </Label>
                    <div className={`border-2 border-dashed border-gray-200 rounded-lg p-4 transition-colors ${config.theme ? 'opacity-60' : 'hover:border-blue-300'}`}>
                      <input
                        id="file-upload"
                        type="file"
                        accept=".txt"
                        onChange={handleFileUpload}
                        className="hidden"
                        disabled={!!config.theme}
                      />
                      <label htmlFor="file-upload" className={`flex flex-col items-center gap-2 ${config.theme ? 'pointer-events-none' : 'cursor-pointer'}`}>
                        <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center">
                          <Upload className="w-6 h-6 text-blue-500" />
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-medium">{t('uploadTxtCta')}</p>
                          <p className="text-xs text-muted-foreground mt-1">{t(config.style.includes('story') ? 'uploadStoryTxtHint' : 'uploadTxtHint')}</p>
                        </div>
                      </label>

                      {config.theme && (
                        <div className="mt-3 p-2 bg-amber-50 border border-amber-200 rounded-md">
                          <p className="text-xs text-amber-700">{t('clearThemeToUpload')}</p>
                        </div>
                      )}

                      {fileName && (
                        <div className="mt-3 p-3 bg-blue-50 rounded-md flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded bg-blue-100 flex items-center justify-center">
                              <span className="text-xs font-medium text-blue-700">TXT</span>
                            </div>
                            <div>
                              <p className="text-sm font-medium">{fileName}</p>
                              <p className="text-xs text-muted-foreground">
                                {config.article ? formatCharacterCount(config.article.length) : t('unreadContent')}
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={handleClearFile}
                            className="p-1 hover:bg-red-100 rounded-full transition-colors"
                          >
                            <X className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      )}

                      {fileError && (
                        <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded-md">
                          <p className="text-xs text-red-600">{fileError}</p>
                        </div>
                      )}

                      {config.article && !fileError && (
                        <div className="mt-3 p-2 bg-green-50 border border-green-200 rounded-md">
                          <p className="text-xs text-green-700">✅ {t('documentReadSuccess', { count: config.article.length })}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {config.article && isStoryStyle(config.style) && (
                  <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                    <p className="text-xs text-yellow-700">
                      {t('storyDocumentNotice')}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="text" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('textConfigTitle')}</CardTitle>
                <CardDescription>{t('textConfigDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('textModel')}</Label>
                  <Select
                    value={config.text_model_name}
                    onValueChange={(value) => setConfig({ ...config, text_model_name: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {textModels.map((model) => (
                        <SelectItem key={model.value} value={model.value}>
                          {model.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={Boolean(config.with_media_prompts)}
                      onChange={(e) => setConfig({ ...config, with_media_prompts: e.target.checked })}
                    />
                    {t('enableMediaPrompts')}
                  </label>
                  <div className="space-y-2">
                    <Label>{t('mediaPromptStyle')}</Label>
                    <Select
                      value={config.media_prompt_style || 'image_default'}
                      onValueChange={(value) => setConfig({ ...config, media_prompt_style: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="image_default">{t('mediaPromptStyleImageDefault')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="audio" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('audioConfigTitle')}</CardTitle>
                <CardDescription>{t('audioConfigDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('audioModel')}</Label>
                  <Select
                    value={config.audio_model_name}
                    onValueChange={(value) => setConfig({ ...config, audio_model_name: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {audioModels.map((model) => (
                        <SelectItem key={model.value} value={model.value}>
                          {model.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="voice">{t('voice')}</Label>
                  <Input
                    id="voice"
                    placeholder={t('voicePlaceholder')}
                    value={config.voice}
                    onChange={(e) => setConfig({ ...config, voice: e.target.value })}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="image" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('imageConfigTitle')}</CardTitle>
                <CardDescription>{t('imageConfigDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('imageModel')}</Label>
                  <Select
                    value={config.image_model_name}
                    onValueChange={(value) => setConfig({ ...config, image_model_name: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {imageModels.map((model) => (
                        <SelectItem key={model.value} value={model.value}>
                          {model.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>{t('imageSize')}</Label>
                    <Select
                      value={config.size}
                      onValueChange={(value) => setConfig({ ...config, size: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1024*1024">1024 × 1024</SelectItem>
                        <SelectItem value="1024*720">1024 × 720</SelectItem>
                        <SelectItem value="720*1024">720 × 1024</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>{t('imageCount')}</Label>
                    <Select
                      value={String(config.n)}
                      onValueChange={(value) => setConfig({ ...config, n: Number(value) })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[1, 2, 4, 8].map((count) => (
                          <SelectItem key={count} value={String(count)}>{formatImageCountLabel(count)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {!!currentProjectId && (!!imageItems.length || !!audioItems.length || !!clipItems.length) && (
        <Card>
          <CardHeader>
            <CardTitle>{t('assetSequence')}</CardTitle>
            <CardDescription>{t('assetSequenceDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={assetTab} onValueChange={(value) => setAssetTab(value as AssetTab)} className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="images">{t('imageSequence')}</TabsTrigger>
                <TabsTrigger value="audios">{t('audioSequence')}</TabsTrigger>
                <TabsTrigger value="clips">{t('clips')}</TabsTrigger>
              </TabsList>

              <TabsContent value="images" className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">{getDirtyClipLabel(dirtyClipCount)}</span>
                </div>
                {imageItems.length === 0 ? (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-muted-foreground">{t('noImageAssets')}</div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {imageItems.map((path, index) => {
                      const assetUrl = getAssetUrl(path);
                      const imageUrl = imageRevisions[index]
                        ? `${assetUrl}${assetUrl.includes('?') ? '&' : '?'}v=${imageRevisions[index]}`
                        : assetUrl;
                      const imageConfig = imageConfigItems[index] as ImageItemConfig | undefined;
                      const imageDraft = imageDraftConfigs[index] || imageConfig || {
                        image_model_name: config.image_model_name,
                        prompt: promptItems[index] || '',
                        text: promptItems[index] || '',
                        n: config.n || 1,
                        size: config.size,
                      };
                      const prompt = promptItems[index] || imageConfig?.prompt || imageConfig?.text || '-';
                      const isRedrawing = redrawingImageIndex === index;
                      const isSettingsOpen = expandedImageSettingsIndex === index;
                      const history = imageHistoryItems[index] ?? [];
                      const selectedHistoryIndex = selectedImageHistory[index] ?? Math.max(0, history.findIndex((item) => item?.is_current));
                      return (
                        <Dialog.Root key={`image-${index}`} open={isSettingsOpen} onOpenChange={(open) => setExpandedImageSettingsIndex(open ? index : null)}>
                          <Dialog.Trigger asChild>
                            <button type="button" className="overflow-hidden rounded-lg border focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" aria-label={t('imageLabel', { index: index + 1 })}>
                              {path ? <img src={imageUrl} alt={t('imageLabel', { index: index + 1 })} className="aspect-square w-full object-contain bg-slate-50" /> : (
                                <div className="flex aspect-square items-center justify-center bg-red-50 p-4 text-sm text-red-700">{t('imageLabel', { index: index + 1 })}: {t('missingShotImage')}</div>
                              )}
                            </button>
                          </Dialog.Trigger>
                          <Dialog.Portal>
                            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
                            <Dialog.Content className="story-editor-surface fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[95vw] max-w-4xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-white p-6 text-slate-900 shadow-xl">
                              <div className="mb-4 flex items-center justify-between">
                                <Dialog.Title className="text-lg font-semibold">{t('imageLabel', { index: index + 1 })}</Dialog.Title>
                                <Dialog.Close asChild><Button variant="ghost" size="sm" aria-label={locale === 'zh' ? '\u5173\u95ed' : 'Close'}><X className="h-4 w-4" /></Button></Dialog.Close>
                              </div>
                              <Dialog.Description className="sr-only">{t('imageItemSettings')}</Dialog.Description>
                              <div className="space-y-4">
                                {isStoryStyle(config.style) && <Button variant="outline" onClick={() => { window.location.href = `/story/${currentProjectId}?shot=${index}&locale=${locale}`; }}>{locale === 'zh' ? '编辑人物、场景和分镜信息' : 'Edit structured shot information'}</Button>}
                                {path && <img src={imageUrl} alt={t('imageLabel', { index: index + 1 })} className="max-h-[45vh] w-full rounded-md object-contain bg-slate-50" />}
                                {errorMessage && <p role="alert" className="text-sm text-red-600">{errorMessage}</p>}
                          <div className="space-y-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-sm font-medium">{t('imageLabel', { index: index + 1 })}</span>
                              <Badge variant="outline">{imageConfig?.size || config.size || '-'}</Badge>
                            </div>
                            <p className="line-clamp-3 text-xs text-muted-foreground">{prompt}</p>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Button size="sm" onClick={() => void handleRedrawImage(index)} disabled={redrawingImageIndex !== null || isApplyingUpdate || isRunning}>
                              {isRedrawing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Wand2 className="mr-1 h-4 w-4" />}
                              {t('redrawItem')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => handleResetImageDraft(index)}>
                              {t('resetSettings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => triggerDownload(imageUrl)}>
                              <Download className="mr-1 h-4 w-4" />
                              {t('download')}
                            </Button>
                          </div>
                          {isSettingsOpen && (
                            <div className="space-y-3 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('imageItemSettings')}</div>
                              <div className="space-y-2">
                                <Label>{t('imageModel')}</Label>
                                <Select value={imageDraft.image_model_name || config.image_model_name} onValueChange={(value) => handleImageDraftChange(index, { image_model_name: value })}>
                                  <SelectTrigger>
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {imageModels.map((model) => (
                                      <SelectItem key={`image-item-model-${index}-${model.value}`} value={model.value}>
                                        {model.label}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>

                              <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-2">
                                  <Label>{t('imageSize')}</Label>
                                  <Select value={imageDraft.size || config.size} onValueChange={(value) => handleImageDraftChange(index, { size: value })}>
                                    <SelectTrigger>
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="1024*1024">1024 × 1024</SelectItem>
                                      <SelectItem value="1024*720">1024 × 720</SelectItem>
                                      <SelectItem value="720*1024">720 × 1024</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </div>
                                <div className="space-y-2">
                                  <Label>{t('imageCount')}</Label>
                                  <Select value={String(imageDraft.n || 1)} onValueChange={(value) => handleImageDraftChange(index, { n: Number(value) })}>
                                    <SelectTrigger>
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {[1, 2, 4, 8].map((count) => (
                                        <SelectItem key={`image-item-count-${index}-${count}`} value={String(count)}>{formatImageCountLabel(count)}</SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </div>
                              </div>
                              <div className="space-y-2">
                                <Label>{t('prompt')}</Label>
                                <textarea aria-label={t('prompt')} rows={8} className="w-full rounded-md border p-3 text-sm" value={imageDraft.prompt ?? imageDraft.text ?? ''} onChange={(e) => handleImageDraftChange(index, { prompt: e.target.value, text: e.target.value })} placeholder={t('itemImagePromptPlaceholder')} />
                              </div>
                            </div>
                          )}
                          {history.length > 0 && (
                            <div className="space-y-2 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('redrawHistory')}</div>
                              <div className="grid gap-2">
                                {history.map((candidate, historyIndex) => {
                                  const candidateUrl = getAssetUrl(candidate.image_path);
                                  return (
                                    <button
                                      key={`image-history-${index}-${historyIndex}`}
                                      type="button"
                                      aria-pressed={selectedHistoryIndex === historyIndex}
                                      disabled={isApplyingUpdate || isRedrawing}
                                      onClick={() => setSelectedImageHistory((prev) => ({ ...prev, [index]: historyIndex }))}
                                      className={`flex items-center gap-3 rounded-md border p-2 text-left ${selectedHistoryIndex === historyIndex ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-slate-50'}`}
                                    >
                                      <img src={candidateUrl} alt={getCandidateLabel(historyIndex)} className="h-14 w-14 rounded object-cover bg-white" />
                                      <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                          <span className="text-xs font-medium">{getCandidateLabel(historyIndex)}</span>
                                          {candidate.is_current && <Badge variant="secondary">{t('applied')}</Badge>}
                                          {selectedHistoryIndex === historyIndex && !candidate.is_current && <Badge>{t('pendingUpdate')}</Badge>}
                                        </div>
                                        <p className="line-clamp-2 text-xs text-muted-foreground">{getPromptText(candidate.prompt) || getPromptText(candidate.config?.prompt) || getPromptText(candidate.config?.text) || '-'}</p>
                                        <p className="text-[11px] text-muted-foreground">{formatImageMeta(candidate.config?.image_model_name, candidate.config?.size)}</p>
                                        <p className="text-[11px] text-muted-foreground">{formatHistoryTime(locale, candidate.created_at)}</p>
                                      </div>
                                    </button>
                                  );
                                })}
                              </div>
                              <Button size="sm" onClick={() => void handleApplyUpdate(index)}
                                disabled={isApplyingUpdate || isRedrawing || isRunning || selectedHistoryIndex === lastAppliedImageHistory[index]}>
                                {isApplyingUpdate ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                                {locale === 'zh' ? '\u63d0\u4ea4\u9009\u4e2d\u56fe\u7247' : 'Submit selected image'}
                              </Button>
                            </div>
                          )}
                              </div>
                            </Dialog.Content>
                          </Dialog.Portal>
                        </Dialog.Root>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="audios" className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">{getDirtyClipLabel(dirtyClipCount)}</span>
                </div>
                {audioItems.length === 0 ? (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-muted-foreground">{t('noAudioAssets')}</div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {audioItems.map((path, index) => {
                      const audioUrl = getAssetUrl(path);
                      const audioConfig = audioConfigItems[index] as AudioItemConfig | undefined;
                      const audioDraft = audioDraftConfigs[index] || audioConfig || {
                        audio_model_name: config.audio_model_name,
                        text: lineItems[index] || '',
                        voice: config.voice,
                      };
                      const text = lineItems[index] || audioConfig?.text || '-';
                      const isRedrawing = redrawingAudioIndex === index;
                      const isSettingsOpen = expandedAudioSettingsIndex === index;
                      const history = audioHistoryItems[index] ?? [];
                      const selectedHistoryIndex = selectedAudioHistory[index] ?? history.findIndex((item) => item?.is_current) ?? 0;
                      return (
                        <div key={`audio-${index}-${path}`} className="space-y-3 rounded-lg border bg-slate-50 p-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <Mic2 className="h-4 w-4 text-purple-500" />
                              <span className="text-sm font-medium">{t('audioItem', { index: index + 1 })}</span>
                            </div>
                            <Badge variant="outline">{formatDurationLabel(durationItems[index])}</Badge>
                          </div>
                          <p className="line-clamp-3 text-xs text-muted-foreground">{text}</p>
                          <audio controls src={audioUrl} className="w-full" />
                          <div className="flex flex-wrap items-center gap-2">
                            <Button size="sm" onClick={() => void handleRedrawAudio(index)} disabled={isRedrawing}>
                              {isRedrawing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Wand2 className="mr-1 h-4 w-4" />}
                              {t('redrawItem')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => setExpandedAudioSettingsIndex((current) => current === index ? null : index)}>
                              {t('settings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => handleResetAudioDraft(index)}>
                              {t('resetSettings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => triggerDownload(audioUrl)}>
                              <Download className="mr-1 h-4 w-4" />
                              {t('download')}
                            </Button>
                          </div>
                          {isSettingsOpen && (
                            <div className="space-y-3 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('audioItemSettings')}</div>
                              <div className="space-y-2">
                                <Label>{t('audioModel')}</Label>
                                <Select value={audioDraft.audio_model_name || config.audio_model_name} onValueChange={(value) => handleAudioDraftChange(index, { audio_model_name: value })}>
                                  <SelectTrigger>
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {audioModels.map((model) => (
                                      <SelectItem key={`audio-item-model-${index}-${model.value}`} value={model.value}>
                                        {model.label}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>

                              <div className="space-y-2">
                                <Label>{t('voice')}</Label>
                                <Input value={audioDraft.voice || ''} onChange={(e) => handleAudioDraftChange(index, { voice: e.target.value })} placeholder={t('itemVoicePlaceholder')} />
                              </div>
                              <div className="space-y-2">
                                <Label>{t('textContent')}</Label>
                                <Input value={lineItems[index] || audioConfig?.text || ''} readOnly disabled placeholder={t('originalTextFixed')} />
                              </div>
                            </div>
                          )}
                          {history.length > 0 && (
                            <div className="space-y-2 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('redrawHistory')}</div>
                              <div className="grid gap-2">
                                {history.map((candidate, historyIndex) => (
                                  <button
                                    key={`audio-history-${index}-${historyIndex}`}
                                    type="button"
                                    onClick={() => setSelectedAudioHistory((prev) => ({ ...prev, [index]: historyIndex }))}
                                    className={`rounded-md border p-2 text-left ${selectedHistoryIndex === historyIndex ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-slate-50'}`}
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-medium">{getCandidateLabel(historyIndex)}</span>
                                      {candidate.is_current && <Badge variant="secondary">{t('applied')}</Badge>}
                                      {selectedHistoryIndex === historyIndex && <Badge>{t('pendingUpdate')}</Badge>}
                                      <Badge variant="outline">{formatDurationLabel(candidate.duration)}</Badge>
                                    </div>
                                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{candidate.config?.text || '-'}</p>
                                    <p className="mt-1 text-[11px] text-muted-foreground">{formatAudioMeta(candidate.config?.audio_model_name, candidate.config?.voice)}</p>
                                    <p className="mt-1 text-[11px] text-muted-foreground">{formatHistoryTime(locale, candidate.created_at)}</p>
                                    {candidate.audio_path && <audio controls src={getAssetUrl(candidate.audio_path)} className="mt-2 w-full" />}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="clips" className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2 rounded-md border bg-white p-3">
                  <Button size="sm" onClick={() => void handleRebuildClips()} disabled={!canRebuildClips || isRebuildingClips}>
                    {isRebuildingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-1 h-4 w-4" />}
                    {t('rebuildClipsButton')}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => void handleConcatClips()} disabled={!canConcatClips || isConcatingClips}>
                    {isConcatingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                    {t('concatClips')}
                  </Button>
                  <span className="text-xs text-muted-foreground">{getDirtyClipLabel(dirtyClipCount)}</span>
                  <p className="w-full text-xs text-muted-foreground">{t('updateVideoHelp')}</p>
                </div>
                {clipItems.length === 0 ? (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-muted-foreground">{t('noVideoClips')}</div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {clipItems.map((clip) => {
                      const clipUrl = getAssetUrl(clip.clip_path);
                      const imageUrl = getAssetUrl(clip.image_path);
                      const audioUrl = getAssetUrl(clip.audio_path);
                      return (
                        <div key={`clip-${clip.index}-${clip.clip_path || 'empty'}`} className="space-y-3 rounded-lg border bg-slate-50 p-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">{t('videoClip', { index: clip.index + 1 })}</span>
                            {clip.dirty || !clip.clip_path ? <Badge variant="destructive">{t('dirty')}</Badge> : <Badge variant="secondary">{t('synced')}</Badge>}
                          </div>
                          {(clip.dirty || !clip.clip_path) && (
                            <Button size="sm" onClick={() => void handleRebuildClips()} disabled={!canRebuildClips || isRebuildingClips}>
                              {isRebuildingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-1 h-4 w-4" />}
                              {t('rebuildClipsButton')}
                            </Button>
                          )}
                          {clip.clip_path ? <video src={clipUrl} controls className="w-full rounded-md bg-black" /> : <div className="rounded-md border bg-white p-4 text-xs text-muted-foreground">{t('videoClipNotGenerated')}</div>}
                          <div className="grid gap-3 text-xs text-muted-foreground grid-cols-2">
                            <div className="space-y-2">
                              <div className="font-medium text-foreground">{t('imageSequence')}</div>
                              {clip.image_path ? <img src={imageUrl} alt={t('imageLabel', { index: clip.index + 1 })} className="aspect-video w-full rounded-md object-cover bg-white" /> : <div>{t('none')}</div>}
                              <label className="block space-y-1 text-sm">
                                <span>{uploadingBackground === clip.index ? (locale === 'zh' ? '正在保存背景图…' : 'Saving background…') : (locale === 'zh' ? '更换背景图片' : 'Replace background')}</span>
                                <input type="file" accept="image/png,image/jpeg,image/webp,image/bmp" className="block w-full text-xs" disabled={isRunning || isRebuildingClips || isConcatingClips || uploadingBackground !== null} onChange={event => {
                                  const file = event.currentTarget.files?.[0];
                                  event.currentTarget.value = '';
                                  if (file) void handleBackgroundUpload(clip.index, file);
                                }} />
                              </label>
                            </div>
                            <div className="space-y-2">
                              <div className="font-medium text-foreground">{t('audioSequence')}</div>
                              {clip.audio_path ? <audio controls src={audioUrl} className="w-full" /> : <div>{t('none')}</div>}
                              <div>{t('duration')}: {formatDurationLabel(clip.duration)}</div>
                            </div>
                          </div>
                          <p className="line-clamp-3 text-xs text-muted-foreground">{clip.text || clip.prompt || '-'}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* Result Card */}
      {showResult && statusForRender?.result && (
        <Card className="border-green-200 bg-green-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-700">
              <CheckCircle2 className="w-5 h-5" />
              {t('videoCompleted')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {videoUrl && (
              <video
                src={videoUrl}
                controls
                className="w-full rounded-lg"
                style={{ maxHeight: '400px' }}
              />
            )}
            {statusForRender.result.text && (
              <div className="bg-white p-4 rounded-lg">
                <h4 className="font-medium mb-2">{t('generatedCopy')}</h4>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {statusForRender.result.text}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Start Button */}
      {!statusForRender && (
        <div className="flex flex-col items-center pt-4 gap-3">
          <Button
            size="lg"
            variant="gradient"
            onClick={handleStart}
            disabled={(!config.theme && !config.article)}
            className="px-8 py-6 text-lg shadow-lg hover:shadow-xl transition-shadow"
          >
            <Play className="w-5 h-5 mr-2" />
            {t('startGenerateVideo')}
          </Button>
          {((!config.theme && !config.article)) && (
            <p className="text-sm text-muted-foreground">
              {t('fillRequiredFields')}
              <span className="text-red-500 ml-1">{getRequiredFieldMessage()}</span>
            </p>
          )}
          {errorMessage && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-600 text-sm max-w-md">
              <strong>{t('error')}:</strong> {errorMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
