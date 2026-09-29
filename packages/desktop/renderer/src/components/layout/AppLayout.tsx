import { useEffect } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import { useAppStore } from '../../stores/appStore';
import { projectApi } from '../../services/api';

export default function AppLayout() {
  const token = useAppStore((s) => s.token);
  const hydrated = useAppStore((s) => s._hydrated);
  const setProjects = useAppStore((s) => s.setProjects);

  useEffect(() => {
    let aborted = false;
    projectApi.list()
      .then((res) => {
        if (aborted) return;
        const list = res.data?.projects || res.data || [];
        setProjects(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        if (!aborted) setProjects([]);
      });
    return () => { aborted = true; };
  }, [setProjects]);

  if (!hydrated) {
    const lsToken = localStorage.getItem('bidmaster_token');
    if (!lsToken) {
      return <Navigate to="/login" replace />;
    }
  } else if (!token) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--color-bg)' }}>
        <Header />
        <main style={{ flex: 1, overflow: 'auto', padding: '20px 24px', background: 'var(--color-bg)' }}>
          <Outlet />
        </main>
        <footer style={{
          flexShrink: 0,
          height: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '11px',
          color: 'var(--color-text-secondary)',
          borderTop: '1px solid var(--color-border)',
          background: 'var(--color-surface)',
        }}>
          © 2026 某科技企业
        </footer>
      </div>
    </div>
  );
}
