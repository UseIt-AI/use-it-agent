
import React, { Suspense } from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';

// 复用原 Next 项目的全局样式（Tailwind + 变量 + 拖拽区域等）
import './styles/globals.css';

// 初始化 i18n
import './i18n/config';

// Force light mode and English on startup (other options coming soon)
document.documentElement.classList.remove('dark');
localStorage.setItem('app-appearance', 'light');
localStorage.setItem('app-language', 'en');


// 开发环境工具（不阻塞主流程）
if (import.meta.env.DEV) {
  import('./utils/testLocalEngine');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Suspense fallback={null}>
      <App />
    </Suspense>
  </React.StrictMode>
);
