'use client';

import { useEffect, useMemo, useState } from 'react';
import { Download, FileText, Loader2, Sparkles } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { downloadTextFile } from '@/lib/generated-files';
import { getStyleLabel, translate, type Locale } from '@/lib/i18n';
import { generateText } from '@/hooks/useTextGeneration';
import type { SettingsDefaults } from '@/hooks/useSettings';

interface TextGeneratorProps {
  defaults?: SettingsDefaults | null;
  locale: Locale;
}

const textModels = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openai', label: 'OpenAI GPT' },
];

const textStyles = ['温柔', '励志', '科普', '幽默', '严肃', 'math', 'story'];

export default function TextGenerator({ defaults, locale }: TextGeneratorProps) {
  const [theme, setTheme] = useState('');
  const [style, setStyle] = useState('温柔');
  const [textModelName, setTextModelName] = useState(defaults?.default_text_model_name || 'deepseek');
  const [withMediaPrompts, setWithMediaPrompts] = useState(true);
  const [mediaPromptStyle, setMediaPromptStyle] = useState('image_default');
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);
  const [result, setResult] = useState('');
  const [prompts, setPrompts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars);
  const mediaPromptStyleOptions = useMemo(
    () => [
      { value: 'image_default', label: t('mediaPromptStyleImageDefault') },
    ],
    [t],
  );

  useEffect(() => {
    if (!defaults || didApplyDefaults) return;
    setTextModelName((current) => current || defaults.default_text_model_name || 'deepseek');
    setDidApplyDefaults(true);
  }, [defaults, didApplyDefaults]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await generateText({
        theme,
        style,
        text_model_name: textModelName,
        language: locale,
        with_media_prompts: withMediaPrompts,
        media_prompt_style: mediaPromptStyle,
      });
      setResult(data.content);
      setPrompts(data.prompts ?? []);
    } catch (err: any) {
      setError(err.message || (locale === 'zh' ? '文本生成失败' : 'Failed to generate text'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <FileText className="w-5 h-5 text-blue-500" />
          {t('textGeneratorTitle')}
        </CardTitle>
        <CardDescription>{t('textGeneratorDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="text-theme">{t('theme')}</Label>
          <Input
            id="text-theme"
            placeholder={locale === 'zh' ? '例如：春天来了、科技改变生活' : 'e.g. Spring arrives, technology changes life'}
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('textModel')}</Label>
            <Select value={textModelName} onValueChange={setTextModelName}>
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
          <div className="space-y-2">
            <Label>{t('writingStyle')}</Label>
            <Select value={style} onValueChange={setStyle}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {textStyles.map((item) => (
                  <SelectItem key={item} value={item}>
                    {getStyleLabel(item, locale)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>



        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
            <input type="checkbox" checked={withMediaPrompts} onChange={(e) => setWithMediaPrompts(e.target.checked)} />
            {t('enableMediaPrompts')}
          </label>
          <div className="space-y-2">
            <Label>{t('mediaPromptStyle')}</Label>
            <Select value={mediaPromptStyle} onValueChange={setMediaPromptStyle}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {mediaPromptStyleOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex gap-3">
          <Button onClick={handleGenerate} disabled={loading || !theme} className="flex-1">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
            {t('generateText')}
          </Button>
          <Button
            variant="outline"
            onClick={() => downloadTextFile(result, `${theme || 'mindawaker-text'}.txt`)}
            disabled={!result}
          >
            <Download className="w-4 h-4 mr-2" />
            {t('downloadTxt')}
          </Button>
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">{t('generationResult')}</h3>
                <p className="text-sm text-muted-foreground">{t('returnedFullText')}</p>
              </div>
              <Badge variant="success">{t('done')}</Badge>
            </div>
            <div className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-white p-3 text-sm text-slate-700">
              {result}
            </div>
            {prompts.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">{t('attachedMediaPrompts')}</p>
                <div className="space-y-2">
                  {prompts.map((prompt, index) => (
                    <div key={`${index}-${prompt.slice(0, 12)}`} className="rounded-md bg-white p-3 text-xs text-muted-foreground">
                      {index + 1}. {prompt}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
