import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { htmlLangMap } from '@/lib/i18n';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Mindawaker - AI Video Generator',
  description: 'Generate AI-powered videos with text, image, and audio synthesis',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang={htmlLangMap.zh} className="dark">
      <body className={inter.className} data-locale="zh">
        <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.18),_transparent_28%),radial-gradient(circle_at_right,_rgba(168,85,247,0.14),_transparent_24%),linear-gradient(180deg,_#020617_0%,_#0f172a_45%,_#111827_100%)]">
          {children}
        </div>
      </body>
    </html>
  );
}
