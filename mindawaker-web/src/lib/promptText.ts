export interface StoryPrompt {
  image_prompt?: string;
  media_prompt?: string;
  text?: string;
  [key: string]: unknown;
}

export type MediaPrompt = string | StoryPrompt;

/** Project snapshots may contain complete story shots instead of plain prompts. */
export function getPromptText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '';
  const item = value as Record<string, unknown>;
  for (const key of ['image_prompt', 'media_prompt', 'prompt', 'text']) {
    if (typeof item[key] === 'string' && item[key]) return item[key] as string;
  }
  return '';
}
