import type { Locale } from '@/lib/i18n';

export interface VoiceConfig {
  name: string;
  file_path: string;
}

export type TemplateLanguageMap = Partial<Record<Locale, string>>;
export type TemplateConfigValue = string | TemplateLanguageMap;

export interface SettingsData {
  voices: VoiceConfig[];
  enable_image_consistency: boolean;
  image_consistency_weight: number;
  default_language: Locale;
  theme2text_mode: string;
  theme2text_template_global: TemplateConfigValue;
  theme2text_templates: Record<string, TemplateConfigValue>;
  media_prompt_template_global: TemplateConfigValue;
  media_prompt_templates: Record<string, TemplateConfigValue>;
  default_text_model_name: string;
  default_audio_model_name: string;
  default_image_model_name: string;
}

export interface TemplateOption {
  name: string;
  path: string;
}

export interface SettingsDefaults {
  default_language: Locale;
  default_text_model_name: string;
  default_audio_model_name: string;
  default_image_model_name: string;
  voices: VoiceConfig[];
}

export function createEmptySettings(): SettingsData {
  return {
    voices: [],
    enable_image_consistency: false,
    image_consistency_weight: 0.7,
    default_language: 'zh',
    theme2text_mode: 'default',
    theme2text_template_global: '',
    theme2text_templates: {},
    media_prompt_template_global: '',
    media_prompt_templates: {},
    default_text_model_name: 'deepseek',
    default_audio_model_name: 'azure',
    default_image_model_name: 'jimeng',
  };
}

export async function loadSettings(): Promise<SettingsData> {
  const response = await fetch('/api/setting/load', { method: 'POST' });
  if (!response.ok) {
    throw new Error('Failed to load settings');
  }
  return response.json();
}

export async function saveSettings(settings: SettingsData): Promise<{ saved: boolean; settings: SettingsData }> {
  const response = await fetch('/api/setting/save', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    throw new Error('Failed to save settings');
  }
  return response.json();
}

export async function listTemplateOptions(): Promise<TemplateOption[]> {
  const response = await fetch('/api/setting/templates');
  if (!response.ok) {
    throw new Error('Failed to load templates');
  }
  const data = await response.json();
  return data.templates ?? [];
}

export async function uploadTemplate(file: File): Promise<TemplateOption> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/api/setting/templates/upload', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error('Failed to upload template');
  }
  return response.json();
}

export async function uploadVoice(file: File): Promise<{ name: string; path: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/api/setting/voices/upload', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error('Failed to upload voice');
  }
  return response.json();
}

export async function loadSettingsDefaults(): Promise<SettingsDefaults> {
  const response = await fetch('/api/setting/defaults');
  if (!response.ok) {
    throw new Error('Failed to load setting defaults');
  }
  return response.json();
}

export function getTemplateNameFromPath(path: string) {
  return path.split('/').pop() || path;
}
