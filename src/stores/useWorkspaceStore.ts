/**
 * Workspace UI State Store
 * 
 * Centralized Zustand store for workspace layout/panel state.
 * Extracted from WorkspacePage useState calls so that AI app actions
 * (and any other non-component code) can read/mutate workspace UI state.
 */

import { create } from 'zustand';
import type { ActivityId } from '@/features/workspace/sidebar/ActivityBar';

export type ControlPanelMode = 'normal' | 'maximized' | 'collapsed';

export interface WorkspaceState {
  // Left sidebar
  activeActivity: ActivityId | null;
  leftPanelCollapsed: boolean;

  // Right chat panel
  isChatPanelCollapsed: boolean;
  showHistory: boolean;

  // Bottom control panel
  controlPanelMode: ControlPanelMode;

  // Layout modes
  viewerFullscreen: boolean;
  isSidebarMode: boolean;
  isCompactWindow: boolean;

  // Active environment target (shared between ControlPanel UI and /app commands)
  activeTargetId: string | null;

  // Explore fullscreen: chat takes full width, workspace tabs hidden but data preserved
  isExploreFullscreen: boolean;

  /** When set, ChatPanel shows Vibe Workflow example prompts for this workflow id until first user message */
  vibeWorkflowHintWorkflowId: string | null;

  // Actions
  resetForProjectSwitch: () => void;
  setActiveActivity: (activity: ActivityId | null) => void;
  setLeftPanelCollapsed: (collapsed: boolean) => void;
  setChatPanelCollapsed: (collapsed: boolean) => void;
  setControlPanelMode: (mode: ControlPanelMode) => void;
  setViewerFullscreen: (fullscreen: boolean) => void;
  setSidebarMode: (enabled: boolean) => void;
  setCompactWindow: (compact: boolean) => void;
  setShowHistory: (show: boolean) => void;
  setActiveTargetId: (id: string | null) => void;
  setExploreFullscreen: (fullscreen: boolean) => void;
  setVibeWorkflowHintWorkflowId: (workflowId: string | null) => void;
  initActiveTargetId: () => Promise<void>;
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  activeActivity: null,
  leftPanelCollapsed: false,
  isChatPanelCollapsed: false,
  showHistory: false,
  controlPanelMode: 'normal',
  viewerFullscreen: false,
  isSidebarMode: false,
  isCompactWindow: false,
  activeTargetId: null,
  isExploreFullscreen: false,
  vibeWorkflowHintWorkflowId: null,

  // 切换项目时重置临时显示状态（全屏、控制面板模式、历史面板等）。
  // 刻意保留用户布局偏好：activeActivity、leftPanelCollapsed、
  // isChatPanelCollapsed、activeTargetId、isSidebarMode、isCompactWindow。
  resetForProjectSwitch: () => set({
    viewerFullscreen: false,
    isExploreFullscreen: false,
    vibeWorkflowHintWorkflowId: null,
    controlPanelMode: 'normal',
    showHistory: false,
  }),
  setActiveActivity: (activity) => set({ activeActivity: activity }),
  setLeftPanelCollapsed: (collapsed) => set({ leftPanelCollapsed: collapsed }),
  setChatPanelCollapsed: (collapsed) => set({ isChatPanelCollapsed: collapsed }),
  setControlPanelMode: (mode) => set({ controlPanelMode: mode }),
  setViewerFullscreen: (fullscreen) => set({ viewerFullscreen: fullscreen }),
  setSidebarMode: (enabled) => set({ isSidebarMode: enabled }),
  setCompactWindow: (compact) => set({ isCompactWindow: compact }),
  setShowHistory: (show) => set({ showHistory: show }),
  setExploreFullscreen: (fullscreen) => set({ isExploreFullscreen: fullscreen }),
  setVibeWorkflowHintWorkflowId: (workflowId) => set({ vibeWorkflowHintWorkflowId: workflowId }),
  setActiveTargetId: (id) => {
    set({ activeTargetId: id });
    window.electron?.setAppConfig?.({ activeTargetId: id }).catch(() => {});
  },
  initActiveTargetId: async () => {
    try {
      if (window.electron?.getAppConfig) {
        const savedId = await window.electron.getAppConfig('activeTargetId');
        set({ activeTargetId: savedId || 'local' });
      } else {
        set({ activeTargetId: 'local' });
      }
    } catch {
      set({ activeTargetId: 'local' });
    }
  },
}));
