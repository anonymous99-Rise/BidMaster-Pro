import { Check, AlertTriangle, Info } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning';
export interface ToastState { type: ToastType; text: string }

const COLORS: Record<ToastType, { bg: string; border: string }> = {
  success: { bg: '#f0fdf4', border: '#a7f3d0' },
  warning: { bg: '#fffbeb', border: '#fbbf24' },
  error: { bg: '#fef2f2', border: '#fecaca' },
};

export function Toast({ toast }: { toast: ToastState | null }) {
  if (!toast) return null;
  const c = COLORS[toast.type] ?? COLORS.error;
  return (
    <div style={{
      position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
      background: c.bg, border: `1px solid ${c.border}`, color: '#334155',
      padding: '9px 16px', borderRadius: 10, fontSize: 13,
      display: 'flex', alignItems: 'center', gap: 7, zIndex: 9999,
      boxShadow: '0 4px 16px rgba(0,0,0,0.10)',
    }}>
      {toast.type === 'success' ? <Check size={15} color="#059669" />
        : toast.type === 'warning' ? <AlertTriangle size={15} color="#d97706" />
        : <Info size={15} color="#dc2626" />}
      {toast.text}
    </div>
  );
}
