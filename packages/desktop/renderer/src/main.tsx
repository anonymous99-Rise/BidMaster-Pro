import React from 'react';
import ReactDOM from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import TitleBar from './components/layout/TitleBar';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <TitleBar />
      <div style={{ flex: 1, minHeight: 0 }}>
        <QueryClientProvider client={queryClient}>
          {/* Electron 生产模式走 file:// 协议，必须用 HashRouter，BrowserRouter 路由匹配会失效导致白屏 */}
          <HashRouter>
            <App />
          </HashRouter>
        </QueryClientProvider>
      </div>
    </div>
  </React.StrictMode>,
);
