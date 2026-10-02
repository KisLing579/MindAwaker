'use client';

import type { Locale } from '@/lib/i18n';

export interface TextGenerationConfig {
  theme: string;
  text_model_name: string;
  style?: string;
  language?: Locale;
  with_media_prompts?: boolean;
  media_prompt_style?: string;
}

export interface TextGenerationResult {
  theme: string;
  model_name: string;
  content: string;
  success: boolean;
  prompts?: string[] | null;
}

export async function generateText(
  config: TextGenerationConfig,
): Promise<TextGenerationResult> {
  const response = await fetch('/api/text/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || '文本生成失败');
  }

  return response.json();
}
