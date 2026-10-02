export function getAssetUrl(filePath?: string | null) {
  if (!filePath) return '';

  const normalized = filePath.replaceAll('\\', '/');
  const marker = 'app/assets/';
  const index = normalized.indexOf(marker);

  if (index === -1) {
    return `/api/${normalized.replace(/^\/+/, '')}`;
  }

  return `/api/files/${normalized.slice(index + marker.length)}`;
}

export function downloadTextFile(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function triggerDownload(url: string, filename?: string) {
  const link = document.createElement('a');
  link.href = url;
  if (filename) link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
