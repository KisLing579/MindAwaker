'use client';

import type { Locale } from '@/lib/i18n';

export interface AudioGenerationConfig {
  text: string;
  voice?: string;
  audio_model_name: string;
  language?: Locale;
}

export interface AudioGenerationResult {
  success: boolean;
  audio_path: string;
  duration: number;
}

export async function generateAudio(
  config: AudioGenerationConfig,
  options?: { projectId?: string; index?: number },
): Promise<AudioGenerationResult> {
  const params = new URLSearchParams();
  if (options?.projectId) params.set('project_id', options.projectId);
  if (typeof options?.index === 'number') params.set('index', String(options.index));

  const response = await fetch(`/api/audio/generate${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || '音频生成失败');
  }

  return response.json();
}
