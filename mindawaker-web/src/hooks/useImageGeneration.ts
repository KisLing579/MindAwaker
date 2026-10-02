'use client';

import type { Locale } from '@/lib/i18n';
import type { ProjectSnapshot } from './useTask';

export interface ImageGenerationConfig {
  prompt: string;
  image_model_name: string;
  language?: Locale;
  size?: string;
  n?: number;
}

export interface ImageGenerationResult {
  success: boolean;
  image_paths: string[];
  project?: ProjectSnapshot;
}

export async function generateImage(
  config: ImageGenerationConfig,
  options?: { projectId?: string; index?: number },
): Promise<ImageGenerationResult> {
  const params = new URLSearchParams();
  if (options?.projectId) params.set('project_id', options.projectId);
  if (typeof options?.index === 'number') params.set('index', String(options.index));

  const response = await fetch(`/api/image/generate${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || '图像生成失败');
  }

  return response.json();
}
