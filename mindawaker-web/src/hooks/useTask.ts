'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import type { Locale } from '@/lib/i18n';
import type { MediaPrompt } from '@/lib/promptText';
import { getLocaleDateTime, getStatusLabel, translate } from '@/lib/i18n';

export interface ProjectSnapshot {
  project_id: string;
  project_name?: string;
  project_target?: string;
  project_config?: VideoConfig | Record<string, unknown> | null;
  task_data?: Record<string, unknown>;
  status?: string | null;
  stage?: string | null;
  progress?: number;
  updated_at?: number;
}

export interface ImageItemConfig {
  image_model_name?: string;
  prompt?: string;
  text?: string;
  language?: Locale;
  n?: number;
  size?: string;
}

export interface AudioItemConfig {
  audio_model_name?: string;
  text?: string;
  voice?: string;
  language?: Locale;
}

export interface ImageRedrawCandidate {
  image_path?: string;
  prompt?: string;
  config?: ImageItemConfig;
  created_at?: number;
  is_current?: boolean;
}

export interface AudioRedrawCandidate {
  audio_path?: string;
  duration?: number;
  config?: AudioItemConfig;
  created_at?: number;
  is_current?: boolean;
}

export interface ApplyRedrawSelectionResponse {
  project_id: string;
  saved: boolean;
  project: ProjectSnapshot;
}

export interface ClipItem {
  index: number;
  clip_path?: string;
  image_path?: string;
  audio_path?: string;
  duration?: number;
  prompt?: string;
  text?: string;
  dirty?: boolean;
  script?: string;
  script_file?: string;
}

export interface VideoTaskResult {
  video_path?: string;
  text?: string;
  lines?: string[];
  shot_texts?: string[];
  scene_segment_files?: string[];
  images?: string[];
  audios?: string[];
  durations?: number[];
  prompts?: MediaPrompt[];
  images_configs?: ImageItemConfig[];
  audios_configs?: AudioItemConfig[];
  image_redraw_history?: ImageRedrawCandidate[][];
  audio_redraw_history?: AudioRedrawCandidate[][];
  clips?: ClipItem[];
  video_segments?: string[];
  recoverable?: boolean;
  project_id?: string;
  snapshot?: ProjectSnapshot;
}

export type PipelineStatus = 'in_text_progress' | 'in_audio_progress' | 'in_image_progress' | 'in_video_progress' | 'in_video_rebuild' | 'in_video_concat';

export interface TaskStatus {
  id: string;
  project_id: string;
  type: string;
  status: 'pending' | 'running' | 'cancelled' | 'completed' | 'error';
  pipeline_status?: PipelineStatus | string;
  progress: number;
  stage: string;
  message: string;
  created_at: string;
  updated_at: string;
  result?: VideoTaskResult;
  error?: string;
  done: boolean;
}

export interface SavedProjectSummary {
  project_id: string;
  name: string;
  target?: string;
  status: string;
  stage?: string;
  progress?: number;
  updated_at?: number;
  video_path?: string;
}

export interface LoadProjectResponse {
  project_id: string;
  loaded: boolean;
  project: ProjectSnapshot;
}

export interface RebuildProjectResponse {
  project_id: string;
  task_id: string;
  status: string;
  message: string;
  project: ProjectSnapshot;
}

export interface ListProjectsWarning {
  invalid_meta_count: number;
  invalid_meta_projects: string[];
}

export interface ListProjectsResponse {
  projects: SavedProjectSummary[];
  warning?: ListProjectsWarning | null;
}

export interface SaveProjectResponse {
  project_id: string;
  saved: boolean;
  project: ProjectSnapshot;
}

export interface VideoGeneratorState {
  projectId: string | null;
  config: VideoConfig | null;
  status: TaskStatus | null;
}

export interface VideoConfig {
  clip_mode?: 'static' | 'jimeng';
  clip_video_prompt?: string;
  theme?: string;
  style?: string;
  language?: Locale;
  text_model_name: string;
  image_model_name: string;
  audio_model_name: string;
  voice?: string;
  article?: string;
  size?: string;
  n?: number;
  with_media_prompts?: boolean;
  media_prompt_style?: string;
}

export interface VideoConfigDefaults {
  default_language?: Locale;
  default_text_model_name?: string;
  default_audio_model_name?: string;
  default_image_model_name?: string;
  voices?: Array<{ name: string; file_path: string }>;
}

export function createEmptyVideoConfig(defaults?: VideoConfigDefaults): VideoConfig {
  return {
    theme: '',
    style: '温柔',
    language: defaults?.default_language || 'zh',
    text_model_name: defaults?.default_text_model_name || 'deepseek',
    image_model_name: defaults?.default_image_model_name || 'jimeng',
    audio_model_name: defaults?.default_audio_model_name || 'azure',
    voice: defaults?.voices?.[0]?.name || 'zh-CN-YunxiNeural',
    article: '',
    size: '1024*1024',
    n: 1,
    with_media_prompts: true,
    media_prompt_style: 'image_default',
  };
}

export function createVideoConfigFromDefaults(defaults?: VideoConfigDefaults): VideoConfig {
  return createEmptyVideoConfig(defaults);
}

export function mergeVideoConfig(base: VideoConfig, incoming?: VideoConfig | null): VideoConfig {
  if (!incoming) {
    return base;
  }
  return {
    ...base,
    ...incoming,
  };
}

export async function listProjects(): Promise<ListProjectsResponse> {
  const response = await fetch('/api/project/list');

  if (!response.ok) {
    throw new Error('Failed to list projects');
  }

  return response.json();
}

export async function loadProject(projectId: string): Promise<LoadProjectResponse> {
  const response = await fetch(`/api/project/load?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error('Failed to load project');
  }

  return response.json();
}

export async function saveProject(projectId: string): Promise<SaveProjectResponse> {
  const response = await fetch(`/api/project/save?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error('Failed to save project');
  }

  return response.json();
}

export async function rebuildProject(projectId: string, imagePromptUpdates: Record<string, string> = {}): Promise<RebuildProjectResponse> {
  const response = await fetch(`/api/project/rebuild?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_prompt_updates: imagePromptUpdates }),
  });

  if (!response.ok) {
    throw new Error('Failed to rebuild project');
  }

  return response.json();
}

export async function rebuildClips(projectId: string): Promise<RebuildProjectResponse> {
  const response = await fetch(`/api/project/rebuild-clips?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Failed to rebuild clips');
  }

  return response.json();
}

export async function concatClips(projectId: string): Promise<RebuildProjectResponse> {
  const response = await fetch(`/api/project/concat-clips?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Failed to concat clips');
  }

  return response.json();
}

export async function applyRedrawSelection(
  projectId: string,
  payload: { image_selected_history?: Record<string, number>; audio_selected_history?: Record<string, number> },
): Promise<ApplyRedrawSelectionResponse> {
  const response = await fetch(`/api/project/apply-redraw-selection?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Failed to apply redraw selection');
  }

  return response.json();
}

export function getVideoConfigFromSnapshot(project?: ProjectSnapshot | null): VideoConfig | null {
  const config = project?.project_config;
  if (!config || typeof config !== 'object') {
    return null;
  }
  return config as VideoConfig;
}

export function getVideoStateFromLoadResponse(data: LoadProjectResponse): VideoGeneratorState {
  const snapshot = data.project;
  const taskData = (snapshot.task_data ?? {}) as Record<string, unknown>;

  return {
    projectId: data.project_id,
    config: getVideoConfigFromSnapshot(snapshot),
    status: {
      id: '',
      project_id: data.project_id,
      type: 'video',
      status: ['completed', 'cancelled', 'error'].includes(String(snapshot.status ?? ''))
        ? (snapshot.status as TaskStatus['status'])
        : 'running',
      pipeline_status: (snapshot.status as TaskStatus['pipeline_status']) || undefined,
      progress: Number(snapshot.progress ?? taskData.percent ?? 0),
      stage: String(snapshot.stage ?? taskData.stage ?? ''),
      message: String(taskData.error ?? taskData.stage ?? ''),
      created_at: '',
      updated_at: String(snapshot.updated_at ?? ''),
      result: {
        video_path: (taskData.video_path as string | undefined) || undefined,
        text: (taskData.text as string | undefined) || undefined,
        lines: Array.isArray(taskData.lines) ? (taskData.lines as string[]) : undefined,
        shot_texts: Array.isArray(taskData.shot_texts) ? (taskData.shot_texts as string[]) : undefined,
        scene_segment_files: Array.isArray(taskData.scene_segment_files) ? (taskData.scene_segment_files as string[]) : undefined,
        images: Array.isArray(taskData.images) ? (taskData.images as string[]) : undefined,
        audios: Array.isArray(taskData.audios) ? (taskData.audios as string[]) : undefined,
        durations: Array.isArray(taskData.durations) ? (taskData.durations as number[]) : undefined,
        prompts: Array.isArray(taskData.prompts) ? (taskData.prompts as MediaPrompt[]) : undefined,
        images_configs: Array.isArray(taskData.images_configs) ? (taskData.images_configs as ImageItemConfig[]) : undefined,
        audios_configs: Array.isArray(taskData.audios_configs) ? (taskData.audios_configs as AudioItemConfig[]) : undefined,
        image_redraw_history: Array.isArray(taskData.image_redraw_history) ? (taskData.image_redraw_history as ImageRedrawCandidate[][]) : undefined,
        audio_redraw_history: Array.isArray(taskData.audio_redraw_history) ? (taskData.audio_redraw_history as AudioRedrawCandidate[][]) : undefined,
        clips: Array.isArray(taskData.clips) ? (taskData.clips as ClipItem[]) : undefined,
        video_segments: Array.isArray(taskData.video_segments) ? (taskData.video_segments as string[]) : undefined,
        recoverable: true,
        project_id: data.project_id,
        snapshot,
      },
      error: (taskData.error as string | undefined) || undefined,
      done: ['completed', 'cancelled', 'error'].includes(String(snapshot.status ?? '')),
    },
  };
}


export function formatProjectUpdatedAt(value?: number, locale: Locale = 'zh') {
  if (!value) return translate(locale, 'unknownTime');
  return getLocaleDateTime(locale, value);
}

export function getProjectDisplayStatus(status?: string, locale: Locale = 'zh') {
  return getStatusLabel(locale, status);
}

export function isProjectRecoverable(project: SavedProjectSummary) {
  return project.status === 'error' || project.status?.startsWith('in_');
}

export function normalizeTaskStatus(task: TaskStatus): TaskStatus {
  return {
    ...task,
    pipeline_status: task.pipeline_status || undefined,
    done: task.done ?? ['completed', 'cancelled', 'error'].includes(task.status),
  };
}

export interface UseTaskOptions {
  basePath?: string;
  onProgress?: (status: TaskStatus) => void;
  onComplete?: (result: TaskStatus) => void;
  onError?: (error: string) => void;
  onCancel?: () => void;
}


export function useTask(options: UseTaskOptions = {}) {
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const basePath = options.basePath || '/api/video';

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const connect = useCallback((taskId: string) => {
    disconnect();

    // 使用相对路径，通过 Next.js 代理连接 WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}${basePath}/ws/${taskId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = normalizeTaskStatus(JSON.parse(event.data) as TaskStatus);
        setStatus(data);
        options.onProgress?.(data);

        if (data.status === 'completed') {
          options.onComplete?.(data);
          ws.close();
        } else if (data.status === 'error') {
          options.onError?.(data.error || 'Unknown error');
          ws.close();
        } else if (data.status === 'cancelled') {
          options.onCancel?.();
          ws.close();
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      options.onError?.('WebSocket connection error');
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
    };
  }, [disconnect, options]);

  const cancel = useCallback(async (taskId: string) => {
    try {
      const response = await fetch(`${basePath}/cancel/${taskId}`, {
        method: 'POST',
      });
      const data = await response.json();
      if (!response.ok) return false;
      return data.cancelled as boolean;
    } catch (error) {
      console.error('Failed to cancel task:', error);
      return false;
    }
  }, []);

  useEffect(() => {
    return () => disconnect();
  }, [disconnect]);

  return {
    status,
    setStatus,
    isConnected,
    connect,
    disconnect,
    cancel,
  };
}

export async function createVideoTask(
  config: VideoConfig,
  projectId?: string
): Promise<{ task_id: string; project_id: string }> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId);

  // 将空字符串的 theme 转为 null，当 article 存在时 theme 可为空
  const payload = {
    ...config,
    theme: config.theme || null,
    article: config.article || null,
  };

  const response = await fetch(`/api/video/compose?${params}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error('Failed to create video task');
  }

  return response.json();
}
