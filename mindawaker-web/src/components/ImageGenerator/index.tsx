'use client';

import { useEffect, useState } from 'react';
import { Download, Image as ImageIcon, Loader2, Wand2 } from 'lucide-react';
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
import { getAssetUrl, triggerDownload } from '@/lib/generated-files';
import { translate, type Locale } from '@/lib/i18n';
import { generateImage } from '@/hooks/useImageGeneration';
import type { SettingsDefaults } from '@/hooks/useSettings';

interface ImageGeneratorProps {
  defaults?: SettingsDefaults | null;
  locale: Locale;
}

const imageModels = [
  { value: 'flux', label: 'Flux' },
  { value: 'jimeng', label: '即梦' },
  { value: 'openai', label: 'OpenAI DALL-E' },
  { value: 'sdxl', label: 'Stable Diffusion XL' },
];

export default function ImageGenerator({ defaults, locale }: ImageGeneratorProps) {
  const [prompt, setPrompt] = useState('');
  const [imageModelName, setImageModelName] = useState(defaults?.default_image_model_name || 'jimeng');
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);
  const [size, setSize] = useState('1024*1024');
  const [count, setCount] = useState(1);
  const [imagePaths, setImagePaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars);

  useEffect(() => {
    if (!defaults || didApplyDefaults) return;
    setImageModelName((current) => current || defaults.default_image_model_name || 'jimeng');
    setDidApplyDefaults(true);
  }, [defaults, didApplyDefaults]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await generateImage({
        prompt,
        image_model_name: imageModelName,
        size,
        n: count,
        language: locale,
      });
      setImagePaths(data.image_paths || []);
    } catch (err: any) {
      setError(err.message || (locale === 'zh' ? '图像生成失败' : 'Failed to generate image'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <ImageIcon className="w-5 h-5 text-pink-500" />
          {t('imageGeneratorTitle')}
        </CardTitle>
        <CardDescription>{t('imageGeneratorDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="image-prompt">Prompt</Label>
          <textarea
            id="image-prompt"
            className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            placeholder={locale === 'zh' ? '例如：一只坐在沙发上的橘猫，电影感光影' : 'e.g. an orange cat on a sofa, cinematic lighting'}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('imageModel')}</Label>
            <Select value={imageModelName} onValueChange={setImageModelName}>
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
          <div className="space-y-2">
            <Label>{t('imageSize')}</Label>
            <Select value={size} onValueChange={setSize}>
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
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('imageCount')}</Label>
            <Select value={String(count)} onValueChange={(value) => setCount(Number(value))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">{locale === 'zh' ? '1 张' : '1 image'}</SelectItem>
                <SelectItem value="2">{locale === 'zh' ? '2 张' : '2 images'}</SelectItem>
                <SelectItem value="4">{locale === 'zh' ? '4 张' : '4 images'}</SelectItem>
              </SelectContent>
            </Select>
          </div>

        </div>

        <Button onClick={handleGenerate} disabled={loading || !prompt} className="w-full">
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Wand2 className="w-4 h-4 mr-2" />}
          {t('generateImage')}
        </Button>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {imagePaths.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">{t('generationResult')}</h3>
              <Badge variant="success">{t('imageReadyCount', { count: imagePaths.length })}</Badge>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {imagePaths.map((path, index) => {
                const imageUrl = getAssetUrl(path);
                return (
                  <div key={`${index}-${path}`} className="space-y-3 rounded-lg border bg-slate-50 p-3">
                    <img src={imageUrl} alt={t('imageLabel', { index: index + 1 })} className="aspect-square w-full rounded-md object-cover bg-white" />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-muted-foreground">{t('imageLabel', { index: index + 1 })}</span>
                      <Button variant="outline" size="sm" onClick={() => triggerDownload(imageUrl)}>
                        <Download className="w-4 h-4 mr-1" />
                        {t('download')}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
