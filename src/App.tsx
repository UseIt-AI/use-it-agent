/**
 * Desktop App - Electron 桌面端应用入口
 * 
 * 这是桌面端的根组件，包含完整的工作区功能：
 * - 本地 Agent 执行
 * - Local Engine 调用
 * - 屏幕查看器
 * - 文件浏览器
 * - 远程任务轮询（接收手机端任务）
 */

import React, { lazy, Suspense, useEffect, useState, useRef } from 'react';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { observer } from 'mobx-react-lite'

// 共享模块
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ProjectProvider, useProject } from './contexts/ProjectContext';
import { StoreProvider } from './contexts/RootStoreContext';
import AppLoadingScreen from './components/AppLoadingScreen';

// 页面懒加载：只在路由匹配时才下载对应 chunk
// WorkspacePage 含 Monaco Editor / ReactFlow，懒加载可大幅减小首包体积
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'));

// Desktop 专用服务
import { useRemotePolling } from './stores/useRemotePolling';

const ProjectRoute = observer(function ProjectRoute({ children }: { children: React.ReactNode }) {
  const { isLoading } = useProject();
  if (isLoading) return <AppLoadingScreen />;
  return <>{children}</>;
});

const ProjectRedirect = observer(function ProjectRedirect() {
  const { currentProject, recentProjects, isLoading, openProject } = useProject();
  const [isAutoOpening, setIsAutoOpening] = useState(false);
  const autoOpenAttempted = useRef(false);

  useEffect(() => {
    if (isLoading || isAutoOpening || currentProject || autoOpenAttempted.current) return;
    autoOpenAttempted.current = true;

    const autoOpen = async () => {
      setIsAutoOpening(true);
      try {
        const localProject = recentProjects.find(p => p.exists !== false);
        if (localProject) {
          console.log('[ProjectRedirect] Auto-opening most recent project:', localProject.name);
          const resolvedProject = await openProject(localProject.id);
          if (!resolvedProject) {
            console.warn('[ProjectRedirect] Open failed, redirecting to explore');
          }
        }
      } catch (e) {
        console.error('[ProjectRedirect] Auto-open failed:', e);
      }
      setIsAutoOpening(false);
    };

    autoOpen();
  }, [isLoading, currentProject, recentProjects, openProject, isAutoOpening]);

  if (isLoading || isAutoOpening) {
    return <AppLoadingScreen />;
  }

  return <Navigate to="/workspace" replace />;
});

// 启动远程任务轮询的 Hook
function useRemoteTaskPolling() {
  const { session } = useAuth();
  const userId = session?.user?.id;
  const { startPolling, stopPolling, enabled } = useRemotePolling();

  useEffect(() => {
    // 当用户登录后，根据 enabled 状态决定是否启动远程任务轮询
    if (userId) {
      console.log('[Desktop] 初始化远程任务轮询...', { userId, enabled });
      startPolling(userId);

      return () => {
        console.log('[Desktop] 停止远程任务轮询');
        stopPolling();
      };
    }
  }, [userId, startPolling, stopPolling]);

  return null;
}

// 远程任务轮询组件（放在 ProtectedRoute 内部）
function RemoteTaskPollerProvider({ children }: { children: React.ReactNode }) {
  useRemoteTaskPolling();
  return <>{children}</>;
}


export function App() {
  return (
    <StoreProvider>
      <AuthProvider>
        <ProjectProvider>
          <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Suspense fallback={<AppLoadingScreen />}>
              <Routes>
                <Route
                  path="/"
                  element={
                      <RemoteTaskPollerProvider>
                        <ProjectRedirect />
                      </RemoteTaskPollerProvider>
                  }
                />

                <Route
                  path="/workspace"
                  element={
                      <RemoteTaskPollerProvider>
                        <ProjectRoute>
                          <WorkspacePage />
                        </ProjectRoute>
                      </RemoteTaskPollerProvider>
                  }
                />

                {/* Backward compatibility: old project-scoped URLs → /workspace */}
                <Route path="/project/*" element={<Navigate to="/workspace" replace />} />
                <Route path="/chat" element={<Navigate to="/" replace />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </HashRouter>
        </ProjectProvider>
      </AuthProvider>
    </StoreProvider>
  );
}

export default App;
