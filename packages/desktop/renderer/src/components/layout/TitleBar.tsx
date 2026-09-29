import { Minus, Square, X } from 'lucide-react';

declare global {
  interface Window {
    electronAPI?: {
      platform?: string;
      minimizeWindow?: () => void;
      maximizeWindow?: () => void;
      closeWindow?: () => void;
      [key: string]: unknown;
    };
  }
}

// Windows 上 titleBarStyle:'hidden' 去掉了系统标题栏,必须自绘拖拽区,
// 否则无边框窗口无法拖动;web 端和 macOS(原生标题栏)不渲染
export default function TitleBar() {
  const api = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!api || api.platform === 'darwin') return null;

  return (
    <div
      style={{
        height: '32px',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border)',
        WebkitAppRegion: 'drag',
      } as React.CSSProperties}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '12px' }}>
        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--color-primary)' }}>
          BidMaster Pro
        </span>
      </div>
      <div style={{ display: 'flex', height: '100%' }}>
        <button
          onClick={() => api.minimizeWindow?.()}
          aria-label="最小化"
          style={{
            width: '44px', height: '100%', border: 'none', cursor: 'pointer',
            background: 'transparent', color: 'var(--color-text-secondary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            WebkitAppRegion: 'no-drag',
          } as React.CSSProperties}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#f1f5f9'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
        >
          <Minus size={14} />
        </button>
        <button
          onClick={() => api.maximizeWindow?.()}
          aria-label="最大化/还原"
          style={{
            width: '44px', height: '100%', border: 'none', cursor: 'pointer',
            background: 'transparent', color: 'var(--color-text-secondary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            WebkitAppRegion: 'no-drag',
          } as React.CSSProperties}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#f1f5f9'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
        >
          <Square size={11} />
        </button>
        <button
          onClick={() => api.closeWindow?.()}
          aria-label="关闭"
          style={{
            width: '44px', height: '100%', border: 'none', cursor: 'pointer',
            background: 'transparent', color: 'var(--color-text-secondary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            WebkitAppRegion: 'no-drag',
          } as React.CSSProperties}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = '#dc2626';
            (e.currentTarget as HTMLButtonElement).style.color = 'white';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-secondary)';
          }}
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
