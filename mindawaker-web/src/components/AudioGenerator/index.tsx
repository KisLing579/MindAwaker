'use client';

import { useEffect, useState } from 'react';
import { Download, Loader2, Mic2, PlayCircle } from 'lucide-react';
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
import { generateAudio } from '@/hooks/useAudioGeneration';
import type { SettingsDefaults } from '@/hooks/useSettings';

interface AudioGeneratorProps {
  defaults?: SettingsDefaults | null;
  locale: Locale;
}

const audioModels = [
  { value: 'azure', label: 'Azure TTS' },
  { value: 'auralis', label: 'Auralis' },
  { value: 'microsoft', label: 'Microsoft TTS' },
];

export default function AudioGenerator({ defaults, locale }: AudioGeneratorProps) {
  const [text, setText] = useState('');
  const [audioModelName, setAudioModelName] = useState(defaults?.default_audio_model_name || 'azure');
  const [voice, setVoice] = useState(defaults?.voices?.[0]?.name || 'zh-CN-YunxiNeural');
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);
  const [audioPath, setAudioPath] = useState('');
  const [duration, setDuration] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars);

  useEffect(() => {
    if (!defaults || didApplyDefaults) return;
    setAudioModelName((current) => current || defaults.default_audio_model_name || 'azure');
    setVoice((current) => current || defaults.voices?.[0]?.name || 'zh-CN-YunxiNeural');
    setDidApplyDefaults(true);
  }, [defaults, didApplyDefaults]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await generateAudio({
        text,
        audio_model_name: audioModelName,
        voice,
        language: locale,
      });
      setAudioPath(data.audio_path);
      setDuration(data.duration);
    } catch (err: any) {
      setError(err.message || (locale === 'zh' ? '音频生成失败' : 'Failed to generate audio'));
    } finally {
      setLoading(false);
    }
  };

  const audioUrl = getAssetUrl(audioPath);

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Mic2 className="w-5 h-5 text-purple-500" />
          {t('audioGeneratorTitle')}
        </CardTitle>
        <CardDescription>{t('audioGeneratorDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="audio-text">{t('textContent')}</Label>
          <textarea
            id="audio-text"
            className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            placeholder={locale === 'zh' ? '输入要转换成语音的文本' : 'Enter the text to synthesize'}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('audioModel')}</Label>
            <Select value={audioModelName} onValueChange={setAudioModelName}>
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
            <Label htmlFor="audio-voice">{t('voice')}</Label>
            <Input
              id="audio-voice"
              placeholder={locale === 'zh' ? '例如：me2 / alloy' : 'e.g. me2 / alloy'}
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
            />
          </div>
        </div>



        <div className="flex gap-3">
          <Button onClick={handleGenerate} disabled={loading || !text} className="flex-1">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-2" />}
            {t('generateAudio')}
          </Button>
          <Button variant="outline" onClick={() => triggerDownload(audioUrl)} disabled={!audioUrl}>
            <Download className="w-4 h-4 mr-2" />
            {t('downloadAudio')}
          </Button>
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {audioUrl && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">{t('generationResult')}</h3>
                <p className="text-sm text-muted-foreground">{t('audioReady')}</p>
              </div>
              <Badge variant="success">{duration ? `${duration}s` : t('done')}</Badge>
            </div>
            <audio controls src={audioUrl} className="w-full" />
            <div className="rounded-md bg-white p-3 text-xs text-muted-foreground break-all">
              {audioPath}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
