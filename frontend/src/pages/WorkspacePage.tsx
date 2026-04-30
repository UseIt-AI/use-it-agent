import React, { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import { observer } from 'mobx-react-lite';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useProject } from '@/contexts/ProjectContext';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import {
  Folder,
  GitBranch,
  Minus,
  Monitor,
  Plus,
  X,
  HelpCircle,
  FileText,
  Square,
  Copy,
  LayoutDashboard,
  PanelRight,
  PanelRightOpen,
  ArrowRightToLine,
  Upload,
  Download,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Loader2,
} from 'lucide-react';
import { useOnboarding } from '@/features/onboarding/useOnboarding';
import { WelcomeModal } from '@/features/onboarding/WelcomeModal';
import { PanelHint } from '@/features/onboarding/PanelHint';
import FileExplorer from '@/features/workspace/file-explorer/FileExplorer';
import { SkillsExplorer, type SkillsExplorerRef } from '@/features/workspace/SkillsExplorer';
import { subscribeSkillsNavigation } from '@/features/workspace/skillsNavigationEvent';
import { useSkillsRootPath } from '@/features/workspace/useSkillsRootPath';
import { collectSkillsFilesWithMetadata } from '@/features/workspace/skills/skillsStorageService';
import { WorkflowEditor, WorkflowList, useCreateWorkflow } from '@/features/workflow';
import type { WorkflowNode, WorkflowListItem } from '@/features/workflow';
import ChatPanel, { type ChatPanelRef } from '@/features/workspace/ChatPanel';
import type { SyncProgressInfo } from '@/features/chat/components/SyncStatusCard';
import ControlPanel, { type ControlPanelRef } from '@/features/workspace/control-panel/ControlPanel';
import { FileViewer } from '@/features/workspace/file-explorer/components/FileViewer';
import { ActivityBar, type ActivityId } from '@/features/workspace/sidebar/ActivityBar';
import { SearchPanel, SearchResultsList } from '@/features/workspace/sidebar/SearchPanel';
import { ApiPanel } from '@/features/workspace/api-panel';
import { RemoteControlPanel } from '@/features/workspace/sidebar/RemoteControlPanel';
import type { ControlTab } from '@/features/workspace/control-panel/types';
import type { FileNode } from '@/features/workspace/file-explorer/types';
import { collectFilesFromTree } from '@/features/workspace/file-explorer/services/uploadService';
import { WorkspaceDropZone } from '@/features/workspace/file-explorer/components/WorkspaceDropZone';
import { REMOTE_CONTROL_ENABLED } from '@/config/runtimeEnv';
import { WindowControlButton } from '@/components/WindowControlButton';
import { ProjectSwitcherDropdown } from '@/features/workspace/sidebar/ProjectSwitcherDropdown';

interface WorkTab {
  id: string;
  title: string;
  type: 'workflow' | 'file';
  data?: {
    filePath?: string;
    fileName?: string;
    workflowId?: string;  // 工作流 ID（用于从 Supabase 加载）
  };
}

type PersistedWorkTab = Pick<WorkTab, 'id' | 'title' | 'type' | 'data'>;

interface WorkspacePersistedStateV1 {
  version: 1;
  updatedAt: number;
  workTabs: PersistedWorkTab[];
  activeTabId: string;
}

type SidebarEnvironmentItem = {
  id: string;
  type: 'local';
  name: string;
  available: boolean;
};

const WorkspacePage = observer(function WorkspacePage() {
  const location = useLocation();
  const { currentProject } = useProject();
  const { t } = useTranslation();
  // Panel/layout state from centralized store (enables AI app actions to control UI)
  const {
    activeActivity, setActiveActivity,
    leftPanelCollapsed, setLeftPanelCollapsed,
    isChatPanelCollapsed, setChatPanelCollapsed: setIsChatPanelCollapsed,
    controlPanelMode, setControlPanelMode,
    viewerFullscreen, setViewerFullscreen,
    isSidebarMode, setSidebarMode: setIsSidebarMode,
    isCompactWindow, setCompactWindow: setIsCompactWindow,
    setShowHistory,
    activeTargetId, setActiveTargetId, initActiveTargetId,
    isExploreFullscreen, setExploreFullscreen,
    setVibeWorkflowHintWorkflowId,
  } = useWorkspaceStore();

  const [isMaximized, setIsMaximized] = useState(false);
  const { startTour, showWelcome, skipWelcome } = useOnboarding(isSidebarMode || isCompactWindow);
  const { rootPath: skillsRootPath } = useSkillsRootPath();
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [sidebarSearchQuery, setSidebarSearchQuery] = useState('');
  const { create: createWorkflow, creating: creatingWorkflow } = useCreateWorkflow();
  const [workflowBatchActions, setWorkflowBatchActions] = useState<React.ReactNode | null>(null);

  // 本地项目：无 S3 预签名上传；发送前仅标记「已同步」并放行聊天
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const uploadBeforeSendResolveRef = useRef<((shouldContinue: boolean) => void) | null>(null);
  const isUploadBeforeSendRef = useRef(false);

  /** 若当前是「发送前上传」流程，则 resolve 并清空 ref，便于聊天发送继续 */
  const resolveAndClearUploadBeforeSend = useCallback((shouldContinue: boolean = true) => {
    if (isUploadBeforeSendRef.current && uploadBeforeSendResolveRef.current) {
      isUploadBeforeSendRef.current = false;
      uploadBeforeSendResolveRef.current(shouldContinue);
      uploadBeforeSendResolveRef.current = null;
    }
  }, []);

  const markFileExplorerSynced = useCallback(() => {
    try {
      const key = currentProject?.id
        ? `workspace_fileExplorer_lastSyncAt_${currentProject.id}`
        : 'workspace_fileExplorer_lastSyncAt_default';
      localStorage.setItem(key, String(Date.now()));
      const refreshFn = (window as any).__fileExplorerRefresh;
      if (refreshFn && typeof refreshFn === 'function') {
        setTimeout(() => refreshFn(), 0);
      }
    } catch {
      // ignore localStorage failures
    }
  }, [currentProject?.id]);

  const [syncMessage, setSyncMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const silentSyncInProgressRef = useRef(false);
  const silentSyncPendingRef = useRef(false);

  // Skills（本地目录）
  const [skillsFileTree, setSkillsFileTree] = useState<FileNode[]>([]);
  const [skillsUploadMessage, setSkillsUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [skillsSyncMessage, setSkillsSyncMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const skillsUploadBeforeSendResolveRef = useRef<((shouldContinue: boolean) => void) | null>(null);
  const isSkillsUploadBeforeSendRef = useRef(false);

  const resolveAndClearSkillsUploadBeforeSend = useCallback((shouldContinue: boolean = true) => {
    if (isSkillsUploadBeforeSendRef.current && skillsUploadBeforeSendResolveRef.current) {
      isSkillsUploadBeforeSendRef.current = false;
      skillsUploadBeforeSendResolveRef.current(shouldContinue);
      skillsUploadBeforeSendResolveRef.current = null;
    }
  }, []);

  // Skills Explorer ref（用于导航到特定 skill 文件夹）
  const skillsExplorerRef = useRef<SkillsExplorerRef>(null);

  // 监听 skills 导航事件（点击 skill chip 时切换到 Skills 页面并展开对应文件夹）
  useEffect(() => {
    const unsubscribe = subscribeSkillsNavigation((payload) => {
      // 1. 切换到 skills activity
      setActiveActivity('skills');
      // 2. 展开对应的 skill 文件夹（延迟执行，确保页面已切换）
      setTimeout(() => {
        skillsExplorerRef.current?.expandFolder(payload.skillName);
      }, 100);
    });
    return unsubscribe;
  }, []);

  // 底部资源面板状态
  const [resourceTab, setResourceTab] = useState<ControlTab>('workflow');
  const resourceTabRef = useRef<ControlTab>(resourceTab);
  resourceTabRef.current = resourceTab;

  // Control Panel resize state (mode comes from useWorkspaceStore above)
  const [controlPanelHeight, setControlPanelHeight] = useState(240);
  const controlPanelResizing = useRef(false);
  const controlPanelStartY = useRef(0);
  const controlPanelStartHeight = useRef(0);
  const CONTROL_PANEL_MIN_HEIGHT = 120;
  const CONTROL_PANEL_HEADER_HEIGHT = 30;

  // 顶部工作区 Tabs 状态
  const [workTabs, setWorkTabs] = useState<WorkTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string>('');
  // Workflow Editor 中选中的节点（用于 ControlPanel 显示 node settings）
  const [selectedWorkflowNode, setSelectedWorkflowNode] = useState<WorkflowNode | null>(null);
  // 来自当前激活的 WorkflowEditor 的 API（用于写回图）
  const workflowNodeApiRef = useRef<{ updateNodeData: (nodeId: string, patch: Record<string, any>) => void } | null>(null);

  // ControlPanel 中选中的 workflow ID（用于同步 workflow 列表选中状态）
  const [controlPanelSelectedWorkflowId, setControlPanelSelectedWorkflowId] = useState<string | null>(null);

  // 左右 panel 默认宽度相等
  const [leftWidth, setLeftWidth] = useState(300);
  const [rightWidth, setRightWidth] = useState(368);
  const [currentEnvName, setCurrentEnvName] = useState('Local Machine (This PC)');
  const [sidebarEnvItems, setSidebarEnvItems] = useState<SidebarEnvironmentItem[]>([
    { id: 'local', type: 'local', name: 'This PC', available: true },
  ]);
  const [selectedSidebarEnvId, setSelectedSidebarEnvId] = useState<string | null>(null);

  // 进入 workspace 页面时：移除首屏 HTML loading
  // 此时 auth/project/chunk 全部就绪，是最准确的"应用就绪"时机
  useEffect(() => {
    document.getElementById('app-loading')?.remove();
  }, []);

  // Hydrate activeTargetId from Electron config into Zustand store
  useEffect(() => {
    initActiveTargetId();
  }, [initActiveTargetId]);

  // Load current environment display name whenever activeTargetId changes
  useEffect(() => {
    const loadEnvName = async () => {
      if (!activeTargetId) return;
      try {
        let envs: any[] = [];
        if (window.electron?.getAppConfig) {
          envs = (await window.electron.getAppConfig('environments')) || [];
        }
        if (Array.isArray(envs)) {
          const target = envs.find((e: any) => e.id === activeTargetId);
          if (target) {
            let name = target.name || target.id;
            if (target.id === 'local' && name === 'local') name = 'Local Machine (This PC)';
            setCurrentEnvName(name);
          } else if (activeTargetId === 'local') {
            setCurrentEnvName('Local Machine (This PC)');
          }
        }
      } catch { }
    };
    loadEnvName();
  }, [activeTargetId]);

  const loadSidebarEnvironmentItems = useCallback(async () => {
    setSidebarEnvItems([{ id: 'local', type: 'local', name: 'This PC', available: true }]);
  }, []);

  useEffect(() => {
    void loadSidebarEnvironmentItems();
    const handleUpdated = () => {
      void loadSidebarEnvironmentItems();
    };
    window.addEventListener('environments-updated', handleUpdated as EventListener);
    return () => window.removeEventListener('environments-updated', handleUpdated as EventListener);
  }, [loadSidebarEnvironmentItems]);

  const handleOpenEnvironmentFromSidebar = useCallback((envId: string) => {
    setSelectedSidebarEnvId(envId);
    setResourceTab('workflow');
    controlPanelRef.current?.selectTarget(envId);
  }, []);

  // Chat Tabs 状态
  interface ChatTab {
    id: string;           // 唯一标识（新建时用临时 ID，保存后用 chatId）
    chatId: string | null; // Supabase chat ID（新建时为 null）
    title: string;
  }
  const [chatTabs, setChatTabs] = useState<ChatTab[]>([
    { id: 'new-chat-1', chatId: null, title: 'New Chat' }
  ]);
  const [activeChatTabId, setActiveChatTabId] = useState<string>('new-chat-1');

  // Chat Panel ref (用于调用 switchToChat 等方法)
  const chatPanelRef = useRef<ChatPanelRef>(null);
  const controlPanelRef = useRef<ControlPanelRef>(null);

  // 从 ExplorePage 跳转过来时，自动发送初始消息 / 预选 Agent
  useEffect(() => {
    const state = location.state as any;
    const initialMessage = state?.initialMessage;
    const initialAgentId = state?.initialAgentId;
    if (!initialMessage && !initialAgentId) return;
    const timer = setTimeout(() => {
      if (initialMessage) {
        chatPanelRef.current?.sendMessage?.(initialMessage, state?.initialImages, initialAgentId);
      } else if (initialAgentId) {
        chatPanelRef.current?.selectAgent?.(initialAgentId);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, []);
  // Chat Tabs 滚动容器 ref
  const chatTabsScrollRef = useRef<HTMLDivElement>(null);

  // 滚动 Chat Tabs 到最右边
  const scrollChatTabsToEnd = useCallback(() => {
    setTimeout(() => {
      if (chatTabsScrollRef.current) {
        chatTabsScrollRef.current.scrollLeft = chatTabsScrollRef.current.scrollWidth;
      }
    }, 50); // 等待 DOM 更新
  }, []);

  // 当 ChatPanel 的 chatId 变化时，更新当前 tab 的 chatId 和 title
  const updateCurrentTabChatId = useCallback((newChatId: string | null, newTitle?: string) => {
    setChatTabs(prev => prev.map(tab =>
      tab.id === activeChatTabId
        ? {
          ...tab,
          chatId: newChatId,
          title: newTitle || tab.title
        }
        : tab
    ));
  }, [activeChatTabId]);

  // 添加新的 Chat Tab
  const addNewChatTab = useCallback(() => {
    const newTabId = `new-chat-${Date.now()}`;
    const newTab: ChatTab = {
      id: newTabId,
      chatId: null,
      title: 'New Chat'
    };
    setChatTabs(prev => [...prev, newTab]);
    setActiveChatTabId(newTabId);
    // 通知 ChatPanel 开始新对话
    chatPanelRef.current?.startNewChat();
    setShowHistory(false);
    // 滚动到新 Tab
    scrollChatTabsToEnd();
  }, [scrollChatTabsToEnd]);

  // 从历史记录打开 Chat Tab
  const openChatFromHistory = useCallback((chatId: string, title: string) => {
    // 检查是否已经有这个 chat 的 tab
    const existingTab = chatTabs.find(tab => tab.chatId === chatId);
    if (existingTab) {
      // 已存在，直接切换
      setActiveChatTabId(existingTab.id);
      chatPanelRef.current?.switchToChat(chatId);
    } else {
      // 不存在，创建新 tab
      const newTabId = `chat-${chatId}`;
      const newTab: ChatTab = {
        id: newTabId,
        chatId: chatId,
        title: title || 'Chat'
      };
      setChatTabs(prev => [...prev, newTab]);
      setActiveChatTabId(newTabId);
      chatPanelRef.current?.switchToChat(chatId);
      // 滚动到新 Tab
      scrollChatTabsToEnd();
    }
    setShowHistory(false);
  }, [chatTabs, scrollChatTabsToEnd]);

  // 关闭 Chat Tab
  const closeChatTab = useCallback((tabId: string) => {
    setChatTabs(prev => {
      const newTabs = prev.filter(tab => tab.id !== tabId);
      // 如果关闭的是当前 tab，切换到最后一个
      if (tabId === activeChatTabId && newTabs.length > 0) {
        const lastTab = newTabs[newTabs.length - 1];
        setActiveChatTabId(lastTab.id);
        if (lastTab.chatId) {
          chatPanelRef.current?.switchToChat(lastTab.chatId);
        } else {
          chatPanelRef.current?.startNewChat();
        }
      }
      // 如果没有 tab 了，创建一个新的
      if (newTabs.length === 0) {
        const newTab: ChatTab = {
          id: `new-chat-${Date.now()}`,
          chatId: null,
          title: 'New Chat'
        };
        setActiveChatTabId(newTab.id);
        chatPanelRef.current?.startNewChat();
        return [newTab];
      }
      return newTabs;
    });
  }, [activeChatTabId]);

  // 切换 Chat Tab
  const switchChatTab = useCallback((tabId: string) => {
    const tab = chatTabs.find(t => t.id === tabId);
    if (tab) {
      setActiveChatTabId(tabId);
      if (tab.chatId) {
        chatPanelRef.current?.switchToChat(tab.chatId);
      } else {
        chatPanelRef.current?.startNewChat();
      }
    }
  }, [chatTabs]);

  const isDraggingLeft = useRef(false);
  const isDraggingRight = useRef(false);
  const isDraggingActivityBar = useRef(false);
  const [activityBarWidth, setActivityBarWidth] = useState(260);

  // Work Tabs 滚动容器 ref
  const workTabsScrollRef = useRef<HTMLDivElement>(null);

  // 滚动 Work Tabs 到最右边
  const scrollWorkTabsToEnd = useCallback(() => {
    setTimeout(() => {
      if (workTabsScrollRef.current) {
        workTabsScrollRef.current.scrollLeft = workTabsScrollRef.current.scrollWidth;
      }
    }, 50); // 等待 DOM 更新
  }, []);

  const didHydrateTabsRef = useRef(false);
  const persistTimerRef = useRef<number | null>(null);

  // Restore tabs for existing project; new project will have no saved state => no tabs.
  useEffect(() => {
    const pid = currentProject?.id;
    if (!pid) {
      setWorkTabs([]);
      setActiveTabId('');
      return;
    }

    didHydrateTabsRef.current = false;

    const restore = async () => {
      try {
        if (!window.electron?.getAppConfig) {
          didHydrateTabsRef.current = true;
          return;
        }
        const map = (await window.electron.getAppConfig('workspaceStateByProjectId')) as
          | Record<string, WorkspacePersistedStateV1 | undefined>
          | undefined;
        const saved = map?.[pid];

        const restoredTabs: WorkTab[] = (Array.isArray(saved?.workTabs) ? (saved!.workTabs as WorkTab[]) : []).filter(
          (t) => t.type !== 'vm'
        );
        const restoredActive = typeof saved?.activeTabId === 'string' ? saved!.activeTabId : '';

        setWorkTabs(restoredTabs);
        setActiveTabId((prev) => {
          // Prefer saved activeTabId if it exists in restored tabs, else last tab, else empty.
          if (restoredTabs.some((t) => t.id === restoredActive)) return restoredActive;
          return restoredTabs.length ? restoredTabs[restoredTabs.length - 1].id : '';
        });
      } catch (e) {
        console.warn('[Workspace] Failed to restore tabs:', e);
        setWorkTabs([]);
        setActiveTabId('');
      } finally {
        didHydrateTabsRef.current = true;
      }
    };

    restore();

    // cleanup pending persist timers on project switch
    return () => {
      if (persistTimerRef.current) {
        window.clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
      }
    };
  }, [currentProject?.id]);

  const persistWorkspaceTabs = useCallback(
    async (pid: string, tabs: PersistedWorkTab[], active: string) => {
      if (!window.electron?.getAppConfig || !window.electron?.setAppConfig) return;

      try {
        const existing =
          ((await window.electron.getAppConfig('workspaceStateByProjectId')) as
            | Record<string, WorkspacePersistedStateV1 | undefined>
            | undefined) || {};

        const next: Record<string, WorkspacePersistedStateV1 | undefined> = {
          ...existing,
          [pid]: {
            version: 1,
            updatedAt: Date.now(),
            workTabs: tabs,
            activeTabId: active,
          },
        };

        await window.electron.setAppConfig({ workspaceStateByProjectId: next });
      } catch (e) {
        console.warn('[Workspace] Failed to persist tabs:', e);
      }
    },
    []
  );

  // Persist tabs whenever they change (after hydration), per-project.
  useEffect(() => {
    const pid = currentProject?.id;
    if (!pid) return;
    if (!didHydrateTabsRef.current) return;

    if (persistTimerRef.current) {
      window.clearTimeout(persistTimerRef.current);
      persistTimerRef.current = null;
    }

    // debounce to avoid spamming disk on rapid interactions
    persistTimerRef.current = window.setTimeout(() => {
      const safeTabs: PersistedWorkTab[] = workTabs.map((t) => ({
        id: t.id,
        title: t.title,
        type: t.type,
        data: t.data,
      }));
      persistWorkspaceTabs(pid, safeTabs, activeTabId);
    }, 250);
  }, [workTabs, activeTabId, currentProject?.id, persistWorkspaceTabs]);

  const handleOpenWorkflow = (workflowId?: string, title?: string) => {
    if (isExploreFullscreen) setExploreFullscreen(false);
    setSelectedWorkflowNode(null);
    // If workflowId not provided, open an unsaved workflow editor (uses example graph as a starting point).
    const tabId = workflowId ? `workflow-${workflowId}` : `workflow-unsaved-${Date.now()}`;
    const tabTitle = title || 'Workflow';

    const existingTab = workTabs.find((t) => t.id === tabId);

    if (existingTab) {
      setActiveTabId(existingTab.id);
    } else {
      const newTab: WorkTab = {
        id: tabId,
        title: tabTitle,
        type: 'workflow',
        data: workflowId ? { workflowId } : undefined,
      };
      setWorkTabs([...workTabs, newTab]);
      setActiveTabId(newTab.id);
      // 滚动到新 Tab
      scrollWorkTabsToEnd();
    }
  };

  // Listen for AI app-action to open a workflow
  const handleOpenWorkflowRef = useRef(handleOpenWorkflow);
  handleOpenWorkflowRef.current = handleOpenWorkflow;
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.workflowId) {
        handleOpenWorkflowRef.current(detail.workflowId);
      }
    };
    window.addEventListener('app-action:open-workflow', handler);
    return () => window.removeEventListener('app-action:open-workflow', handler);
  }, []);

  // Vibe Workflow: open chat, select workflow agent, show example prompts in ChatPanel
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      const wfId = detail?.workflowId;
      if (wfId) {
        setVibeWorkflowHintWorkflowId(wfId);
        setIsChatPanelCollapsed(false);
        chatPanelRef.current?.selectAgent?.(`workflow:${wfId}`);
      }
    };
    window.addEventListener('vibe-workflow-init', handler);
    return () => window.removeEventListener('vibe-workflow-init', handler);
  }, [setIsChatPanelCollapsed, setVibeWorkflowHintWorkflowId]);

  // 打开文件 Tab
  const handleOpenFile = (filePath: string, fileName: string) => {
    if (isExploreFullscreen) setExploreFullscreen(false);
    setSelectedWorkflowNode(null);
    const fileTabId = `file-${filePath}`;
    const existingTab = workTabs.find((t) => t.id === fileTabId);

    if (existingTab) {
      setActiveTabId(existingTab.id);
    } else {
      const newTab: WorkTab = {
        id: fileTabId,
        title: fileName,
        type: 'file',
        data: { filePath, fileName },
      };
      setWorkTabs([...workTabs, newTab]);
      setActiveTabId(newTab.id);
      // 滚动到新 Tab
      scrollWorkTabsToEnd();
    }
  };

  // 本地项目：发送前仅校验存在文件并标记已同步（不再调用 batch-presign / S3）
  const handleUploadFiles = useCallback(async () => {
    if (!currentProject || !fileTree.length) {
      setUploadMessage({ type: 'error', text: '没有可上传的文件' });
      setTimeout(() => setUploadMessage(null), 3000);
      return;
    }

    setUploadMessage(null);

    try {
      const electron = window.electron as any;
      let basePath = '';
      if (electron?.fsGetProjectRoot) {
        try {
          basePath = await electron.fsGetProjectRoot(currentProject.id);
        } catch (err) {
          console.warn('Failed to get project root path:', err);
        }
      }

      const files = collectFilesFromTree(fileTree, basePath);
      if (files.length === 0) {
        throw new Error('文件树中没有文件');
      }

      markFileExplorerSynced();
      resolveAndClearUploadBeforeSend();
    } catch (error: any) {
      console.error('Upload step failed:', error);
      if (isUploadBeforeSendRef.current && error?.message === '文件树中没有文件') {
        resolveAndClearUploadBeforeSend();
        return;
      }
      const errorMessage = error.message || '处理失败，请重试';
      setUploadMessage({ type: 'error', text: errorMessage });
      setTimeout(() => setUploadMessage(null), 5000);
      resolveAndClearUploadBeforeSend();
    }
  }, [currentProject, fileTree, resolveAndClearUploadBeforeSend, markFileExplorerSynced]);

  const handleCancelUpload = useCallback(() => {
    resolveAndClearUploadBeforeSend(false);
  }, [resolveAndClearUploadBeforeSend]);

  /** 发送聊天前先触发左侧文件资源管理器的上传，上传完成（或取消/无文件）后再 resolve */
  const runUploadBeforeSend = useCallback((): Promise<boolean> => {
    if (!currentProject || !fileTree.length) {
      // 发送触发时无文件不弹错误提示，直接放行让消息发送
      return Promise.resolve(true);
    }
    return new Promise<boolean>((resolve) => {
      uploadBeforeSendResolveRef.current = resolve;
      isUploadBeforeSendRef.current = true;
      handleUploadFiles();
    });
  }, [currentProject, fileTree.length, handleUploadFiles]);

  /** 本地项目：不拉取云端，仅刷新并更新同步时间戳 */
  const handleSyncFiles = useCallback(
    async (silent = false) => {
      if (!currentProject) {
        if (!silent) {
          setSyncMessage({ type: 'error', text: '请先选择项目' });
          setTimeout(() => setSyncMessage(null), 3000);
        }
        return;
      }

      if (silent && silentSyncInProgressRef.current) {
        silentSyncPendingRef.current = true;
        console.log('[Sync] Silent sync already in progress, queued for retry');
        return;
      }
      if (silent) {
        silentSyncInProgressRef.current = true;
        silentSyncPendingRef.current = false;
      } else {
        setSyncMessage(null);
      }

      try {
        markFileExplorerSynced();
        const refreshFn = (window as any).__fileExplorerRefresh;
        if (refreshFn && typeof refreshFn === 'function') {
          setTimeout(() => refreshFn(), silent ? 500 : 0);
        }

        if (silent) {
          silentSyncInProgressRef.current = false;
          if (silentSyncPendingRef.current) {
            silentSyncPendingRef.current = false;
            setTimeout(() => handleSyncFiles(true), 1000);
          }
        } else {
          setSyncMessage({
            type: 'success',
            text: '项目文件位于本地目录，无需从云端拉取',
          });
          setTimeout(() => setSyncMessage(null), 5000);
        }
      } catch (error: any) {
        console.error('Sync failed:', error);
        if (silent) {
          silentSyncInProgressRef.current = false;
          const refreshFn = (window as any).__fileExplorerRefresh;
          if (refreshFn && typeof refreshFn === 'function') refreshFn();
          if (silentSyncPendingRef.current) {
            silentSyncPendingRef.current = false;
            setTimeout(() => handleSyncFiles(true), 1000);
          }
        } else {
          const errorMessage = error.message || '同步失败，请重试';
          setSyncMessage({ type: 'error', text: errorMessage });
          setTimeout(() => setSyncMessage(null), 5000);
        }
      }
    },
    [currentProject, markFileExplorerSynced]
  );

  // ==================== Skills Upload/Sync ====================

  const handleUploadSkills = useCallback(async () => {
    if (!skillsRootPath) {
      setSkillsUploadMessage({ type: 'error', text: 'Skills 文件夹不可用' });
      setTimeout(() => setSkillsUploadMessage(null), 3000);
      resolveAndClearSkillsUploadBeforeSend();
      return;
    }

    try {
      const { rawFiles } = await collectSkillsFilesWithMetadata(skillsRootPath);
      if (rawFiles.length === 0) {
        throw new Error('Skills 文件夹中没有文件');
      }

      setTimeout(() => {
        const refreshFn = (window as any).__skillsExplorerRefresh;
        if (refreshFn && typeof refreshFn === 'function') refreshFn();
      }, 0);

      resolveAndClearSkillsUploadBeforeSend();
    } catch (error: any) {
      console.error('[SkillsUpload] 失败:', error);
      if (isSkillsUploadBeforeSendRef.current && error?.message === 'Skills 文件夹中没有文件') {
        resolveAndClearSkillsUploadBeforeSend();
        return;
      }
      setSkillsUploadMessage({ type: 'error', text: error.message || '处理失败' });
      setTimeout(() => setSkillsUploadMessage(null), 5000);
      resolveAndClearSkillsUploadBeforeSend();
    }
  }, [skillsRootPath, resolveAndClearSkillsUploadBeforeSend]);

  const handleCancelSkillsUpload = useCallback(() => {
    resolveAndClearSkillsUploadBeforeSend(false);
  }, [resolveAndClearSkillsUploadBeforeSend]);

  /** 本地 Skills：不请求云端，仅提示并刷新列表 */
  const handleSyncSkills = useCallback(async () => {
    if (!skillsRootPath) {
      setSkillsSyncMessage({ type: 'error', text: 'Skills 文件夹不可用' });
      setTimeout(() => setSkillsSyncMessage(null), 3000);
      return;
    }

    setSkillsSyncMessage({
      type: 'success',
      text: 'Skills 位于本地文件夹，无需从云端拉取',
    });
    setTimeout(() => setSkillsSyncMessage(null), 5000);

    setTimeout(() => {
      const refreshFn = (window as any).__skillsExplorerRefresh;
      if (refreshFn && typeof refreshFn === 'function') refreshFn();
    }, 300);
  }, [skillsRootPath]);

  /** 发送前确认本地 Skills 目录有文件即可 */
  const runSkillsUploadBeforeSend = useCallback((): Promise<boolean> => {
    if (!skillsRootPath) {
      return Promise.resolve(true);
    }
    return new Promise<boolean>((resolve) => {
      skillsUploadBeforeSendResolveRef.current = resolve;
      isSkillsUploadBeforeSendRef.current = true;
      handleUploadSkills();
    });
  }, [skillsRootPath, handleUploadSkills]);

  // 本地模式：发送前上传/同步为瞬时完成，不在 Chat 中展示进度条
  const chatSyncProgress = useMemo((): SyncProgressInfo | null => null, []);

  const handleChatCancelSync = useCallback(() => {
    handleCancelUpload();
    handleCancelSkillsUpload();
  }, [handleCancelUpload, handleCancelSkillsUpload]);

  /**
   * 关闭一个 Work Tab（可靠版）
   * - 如果关闭的是当前 active tab：自动切到“关闭后剩余 tabs 的最后一个”
   * - 如果都关完了：activeTabId 置空
   */
  const closeWorkTab = useCallback((tabId: string) => {
    setWorkTabs((prev) => {
      const next = prev.filter((t) => t.id !== tabId);
      setActiveTabId((prevActive) => {
        if (prevActive !== tabId) return prevActive;
        return next.length ? next[next.length - 1].id : '';
      });
      return next;
    });
  }, []);

  /**
   * 批量关闭 Work Tabs（用于删除 workflow / environment 后同步关 tab）
   */
  const closeWorkTabsWhere = useCallback((predicate: (t: WorkTab) => boolean) => {
    setWorkTabs((prev) => {
      const idsToRemove = new Set(prev.filter(predicate).map((t) => t.id));
      if (idsToRemove.size === 0) return prev;

      const next = prev.filter((t) => !idsToRemove.has(t.id));
      setActiveTabId((prevActive) => (idsToRemove.has(prevActive) ? (next.length ? next[next.length - 1].id : '') : prevActive));
      return next;
    });
  }, []);

  // 删除 workflow 后：关闭对应 workflow tab
  const handleDeleteWorkflow = useCallback(
    (workflowId: string) => {
      closeWorkTabsWhere((t) => t.type === 'workflow' && t.data?.workflowId === workflowId);
    },
    [closeWorkTabsWhere]
  );

  const handleCollapse = () => {
    // 切换到侧边栏模式
    setIsSidebarMode(true);
    // 窗口收缩到屏幕右侧
    (window.electron as any)?.shrinkWindow?.();
  };

  const handleExpand = () => {
    // 展开到完整工作区模式
    setIsSidebarMode(false);
    // 窗口恢复到默认大小
    (window.electron as any)?.restoreWindowSize?.();
  };

  const handleToggleMaximize = () => {
    (window.electron as any)?.toggleMaximize?.();
    setIsMaximized(prev => !prev);
  };

  const handleActiveActivity = (activityId: ActivityId) => {
    if (activityId === 'explore') {
      addNewChatTab();
      setIsChatPanelCollapsed(false);
      setExploreFullscreen(true);
      setActiveActivity(null);
      return;
    }
    setActiveActivity(activityId)
  }

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDraggingActivityBar.current) {
        const newWidth = Math.max(180, Math.min(400, e.clientX));
        setActivityBarWidth(newWidth);
        document.body.style.cursor = 'col-resize';
        e.preventDefault();
      } else if (isDraggingLeft.current) {
        const abWidth = leftPanelCollapsed ? 52 : activityBarWidth;
        const newWidth = Math.max(150, Math.min(500, e.clientX - abWidth));
        setLeftWidth(newWidth);
        document.body.style.cursor = 'col-resize';
        e.preventDefault();
      } else if (isDraggingRight.current) {
        const newWidth = Math.max(300, Math.min(800, window.innerWidth - e.clientX));
        setRightWidth(newWidth);
        document.body.style.cursor = 'col-resize';
        e.preventDefault();
      } else if (controlPanelResizing.current) {
        // Control panel vertical resize - drag up to increase height
        const deltaY = controlPanelStartY.current - e.clientY;
        const newHeight = Math.max(CONTROL_PANEL_MIN_HEIGHT, Math.min(600, controlPanelStartHeight.current + deltaY));
        setControlPanelHeight(newHeight);
        document.body.style.cursor = 'row-resize';
        e.preventDefault();
      }
    };

    const handleMouseUp = () => {
      if (isDraggingActivityBar.current || isDraggingLeft.current || isDraggingRight.current || controlPanelResizing.current) {
        isDraggingActivityBar.current = false;
        isDraggingLeft.current = false;
        isDraggingRight.current = false;
        controlPanelResizing.current = false;
        document.body.style.cursor = 'default';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Sidebar/compact window mode: Electron shrinkWindow typically makes the window very narrow.
  // In that case, we render a chat-only layout and remove inner split borders/resizers.
  useEffect(() => {
    const compute = () => {
      // Threshold chosen to match typical "right sidebar" width while keeping normal layouts unaffected.
      setIsCompactWindow(window.innerWidth <= 520);
    };
    compute();
    window.addEventListener('resize', compute);
    return () => window.removeEventListener('resize', compute);
  }, []);

  // 切换工作区 tab 时：同步 chat 的默认 workflow，并清除非 workflow tab 的选中节点
  useEffect(() => {
    const active = workTabs.find(t => t.id === activeTabId);
    if (active?.type === 'workflow' && active.data?.workflowId) {
      const wfId = active.data.workflowId;
      setControlPanelSelectedWorkflowId(wfId);
      chatPanelRef.current?.selectAgent?.(`workflow:${wfId}`);
    } else if (active?.type !== 'workflow') {
      setSelectedWorkflowNode(null);
    }
  }, [activeTabId, workTabs]);

  // Keep activeTabId valid: if current active tab disappears, fallback to last tab or empty.
  useEffect(() => {
    if (!activeTabId) return;
    if (workTabs.some((t) => t.id === activeTabId)) return;
    setActiveTabId(workTabs.length ? workTabs[workTabs.length - 1].id : '');
  }, [activeTabId, workTabs]);

  // Auto-expand chat panel when all workspace tabs are closed
  useEffect(() => {
    if (workTabs.length === 0 && isChatPanelCollapsed) {
      setIsChatPanelCollapsed(false);
    }
  }, [workTabs.length, isChatPanelCollapsed, setIsChatPanelCollapsed]);

  const handleUpdateWorkflowNode = useCallback((nodeId: string, patch: Record<string, any>) => {
    workflowNodeApiRef.current?.updateNodeData(nodeId, patch);
    // 同步当前选中 node 的本地快照（让左侧表单立即反映最新值）
    setSelectedWorkflowNode(prev =>
      prev && prev.id === nodeId ? ({ ...prev, data: { ...(prev.data as any), ...patch } } as any) : prev
    );
  }, []);

  // 稳定的 onNodeSelect 回调：使用 ref 读取 resourceTab 避免闭包导致回调引用频繁变化，
  // 从而防止 WorkflowEditor/ReactFlow 不必要的重渲染和 onSelectionChange 连锁震荡
  const handleWorkflowNodeSelect = useCallback((node: any | null) => {
    setSelectedWorkflowNode(prev => {
      const prevId = prev?.id ?? null;
      const nextId = node?.id ?? null;
      if (prevId === nextId && prevId !== null) return prev;
      return node;
    });
    if (node) {
      setResourceTab('workflow');
    }
  }, []);

  const handleNodeApiReady = useCallback((api: { updateNodeData: (nodeId: string, patch: Record<string, any>) => void }) => {
    workflowNodeApiRef.current = api;
  }, []);

  return (
    <>
      <div className="flex flex-col h-screen bg-canvas text-[#111] overflow-hidden font-sans selection:bg-orange-500/20 relative">
        {/* ===== 全局统一顶栏 (Global Header) ===== */}
        <header className="draggable flex items-center justify-between px-3 h-[32px] bg-[#F2F1EE] border-b border-divider flex-shrink-0 z-50">
          {/* Left: Brand/Logo + Switch Project Button - Allow drag；侧边栏模式仅保留 Logo，不显示 Home/Switch Project */}
          <div className="flex items-center gap-1.5 select-none min-w-0">
            <img src="./useit-logo-no-text.svg" alt="Logo" className="w-6 h-6 opacity-80 no-drag mr-1.5" />
            {!isSidebarMode && (
              <>
                <button
                  onClick={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
                  className="no-drag w-6 h-6 flex items-center justify-center rounded-sm text-black/35 hover:text-black/65 hover:bg-black/5 transition-colors"
                  title={leftPanelCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                >
                  {leftPanelCollapsed ? <PanelLeftOpen className="w-3.5 h-3.5" /> : <PanelLeftClose className="w-3.5 h-3.5" />}
                </button>
              </>
            )}
          </div>

          {/* Center: Project Name - Allow drag */}
          {!isCompactWindow && (
            <div className="flex items-center justify-center gap-2 text-[11px] font-medium text-black/60 select-none flex-1 min-w-0">
              <Folder className="w-3 h-3 text-black/40" />
              <span className="truncate">{currentProject?.name || t('workspace.header.untitledProject')}</span>
            </div>
          )}

          {/* Right: Window Controls - No drag for buttons */}
          <div className="flex items-center justify-end gap-1 no-drag flex-shrink-0">
            {/* 侧边栏模式：显示展开按钮带文字（优化蓝色） */}
            {isSidebarMode ? (
              <button
                onClick={handleExpand}
                className="no-drag flex items-center gap-1.5 px-1.5 py-0.5 bg-blue-100/50 hover:bg-blue-100 text-blue-700 hover:text-blue-900 transition-all duration-200 text-xs font-medium tracking-wide rounded-sm"
                title={t('workspace.header.expandTooltip')}
              >
                <LayoutDashboard className="w-3.5 h-3.5 stroke-[2]" />
                <span>{t('workspace.header.expandToWorkspace')}</span>
              </button>
            ) : (
              <WindowControlButton
                onClick={handleCollapse}
                icon={<PanelRight className="w-3.5 h-3.5" />}
                title={t('workspace.header.collapseToSidebar')}
                hoverColor="hover:bg-orange-50 hover:text-orange-600"
              />
            )}

            <WindowControlButton
              onClick={startTour}
              icon={<HelpCircle className="w-3.5 h-3.5" />}
              title={t('workspace.header.guideTour')}
            />

            <div />
            <WindowControlButton onClick={() => (window.electron as any)?.minimize?.()} icon={<Minus className="w-3.5 h-3.5" />} title={t('workspace.header.minimize')} />
            <WindowControlButton
              onClick={handleToggleMaximize}
              icon={isMaximized ? <Copy className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
              title={isMaximized ? t('workspace.header.restore') : t('workspace.header.maximize')}
            />
            <WindowControlButton
              onClick={() => (window.electron as any)?.close?.()}
              icon={<X className="w-3.5 h-3.5" />}
              hoverColor="hover:bg-red-600 hover:text-white"
              title={t('workspace.header.close')}
            />
          </div>
        </header>

        {/* ===== 主要内容区域 (Main Content) ===== */}
        <div className="flex flex-1 min-h-0 relative flex-row overflow-hidden">
          {/* ===== 左侧：Activity Bar + 侧边栏 ===== */}
          {!viewerFullscreen && !isCompactWindow && !isSidebarMode && (
            <div data-tour="left-panel" className="flex flex-shrink-0 h-full">
              {/* Activity Bar */}
              <ActivityBar
                activeActivity={activeActivity}
                onActivityChange={handleActiveActivity}
                collapsed={leftPanelCollapsed}
                onToggleCollapse={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
                width={activityBarWidth}
                fileExplorerSlot={currentProject ? (
                  <>
                    <FileExplorer
                      projectId={currentProject?.id}
                      onFileOpen={handleOpenFile}
                      onFileTreeChange={setFileTree}
                      onAddToChat={(filePath, fileName, type) => {
                        chatPanelRef.current?.addFile?.(filePath, fileName, type);
                      }}
                    />
                    <WorkspaceDropZone
                      workspacePath={currentProject?.path ? `${currentProject.path.replace(/[/\\]+$/, '')}/workspace` : ''}
                      onFilesAdded={() => (window as any).__fileExplorerRefresh?.()}
                      disabled={!currentProject?.path}
                    />
                  </>
                ) : undefined}
                projectSwitcher={<ProjectSwitcherDropdown />}
                onSearchQueryChange={setSidebarSearchQuery}
                searchResultsSlot={
                  <SearchResultsList
                    fileTree={fileTree}
                    query={sidebarSearchQuery}
                    onFileOpen={handleOpenFile}
                  />
                }
                workflowTitleOverride={workflowBatchActions}
                workflowActions={
                  <button
                    onClick={async () => {
                      const now = new Date();
                      const timestamp = now.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).replace(/\//g, '-');
                      try {
                        const wf = await createWorkflow({ name: `New Workflow ${timestamp}`, description: '' });
                        setControlPanelSelectedWorkflowId(wf.id);
                        handleOpenWorkflow(wf.id, wf.name);
                      } catch { }
                    }}
                    disabled={creatingWorkflow}
                    className="p-1 text-black/30 hover:text-black/60 hover:bg-black/5 rounded transition-colors disabled:opacity-50"
                    title="New Workflow"
                  >
                    {creatingWorkflow ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                  </button>
                }
              />

              {/* 侧边栏内容区域 */}
              {activeActivity && activeActivity !== 'explore' && activeActivity !== 'workflow' && (
                <div
                  className={`flex-shrink-0 flex flex-col min-h-0 bg-canvas transition-all duration-200 border-r border-divider`}
                  style={{ width: leftWidth }}
                >

                  {activeActivity === 'environment' && (
                    <div className="flex flex-col h-full">
                      <header className="flex items-center justify-between px-3 h-[32px] bg-[#F2F1EE] border-b border-divider flex-shrink-0">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-black/40 select-none">
                          {t('workspace.environment.title')}
                        </span>
                        <span className="text-[9px] font-mono text-black/30 bg-black/5 px-1 rounded-sm">
                          {sidebarEnvItems.filter((item) => item.available).length}
                        </span>
                      </header>
                      <div className="flex-1 min-h-0 flex flex-col bg-canvas-sub/20">
                        <div className="flex-1 min-h-0 overflow-y-auto">
                          {sidebarEnvItems.map((item) => {
                            const isSelected = selectedSidebarEnvId === item.id;
                            return (
                              <div key={item.id} className="border-b border-divider/50">
                                <div
                                  className={`w-full h-[32px] px-2 flex items-center gap-1 transition-colors ${
                                    isSelected ? 'bg-white text-black' : 'text-black/60 hover:bg-black/5 hover:text-black/90'
                                  }`}
                                >
                                  <button
                                    type="button"
                                    disabled={!item.available}
                                    onClick={() => handleOpenEnvironmentFromSidebar(item.id)}
                                    className="min-w-0 flex-1 h-full px-1 flex items-center gap-2 text-left"
                                  >
                                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-emerald-500" />
                                    <Monitor className="w-3.5 h-3.5 flex-shrink-0 text-black/45" />
                                    <span className="text-[11px] font-medium truncate flex-1">{item.name}</span>
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )}

                  {activeActivity === 'search' && (
                    <>
                      {/* Search Header */}
                      <header className="flex items-center px-3 h-[32px] bg-[#F2F1EE] border-b border-divider flex-shrink-0">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-black/40 select-none">
                          {t('workspace.search.title')}
                        </span>
                      </header>
                      <div className="flex-1 min-h-0">
                        <SearchPanel
                          fileTree={fileTree}
                          onFileOpen={handleOpenFile}
                        />
                      </div>
                    </>
                  )}

                  {activeActivity === 'skills' && (
                    <>
                      <header className="flex items-center justify-between px-3 h-[32px] bg-[#F2F1EE] border-b border-divider flex-shrink-0">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-black/40 select-none">
                          Skills
                        </span>
                        <div className="flex items-center gap-2 flex-nowrap">
                          {(skillsUploadMessage || skillsSyncMessage) && (
                            <div
                              className={`flex items-center gap-1 px-2 py-0.5 text-[10px] rounded whitespace-nowrap min-w-0 ${(skillsUploadMessage || skillsSyncMessage)?.type === 'success'
                                ? 'text-green-700 bg-green-100'
                                : 'text-red-700 bg-red-100'
                                }`}
                              title={(skillsUploadMessage || skillsSyncMessage)?.text}
                            >
                              {(skillsUploadMessage || skillsSyncMessage)?.type === 'success' ? (
                                <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                              ) : (
                                <AlertCircle className="w-3 h-3 flex-shrink-0" />
                              )}
                              <span className="truncate max-w-[120px]">
                                {(skillsUploadMessage || skillsSyncMessage)?.text}
                              </span>
                            </div>
                          )}
                          <button
                            type="button"
                            onClick={handleSyncSkills}
                            className="flex items-center justify-center p-1.5 text-black/60 hover:text-black/80 hover:bg-black/5 rounded transition-colors flex-shrink-0"
                            title="刷新 Skills 列表（本地目录，无云端同步）"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={handleUploadSkills}
                            className="flex items-center justify-center p-1.5 text-black/60 hover:text-black/80 hover:bg-black/5 rounded transition-colors flex-shrink-0"
                            title="校验本地 Skills 目录（无云端上传）"
                          >
                            <Upload className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </header>
                      <div className="flex-1 min-h-0 flex flex-col">
                        <div className="flex-1 min-h-0">
                          <SkillsExplorer ref={skillsExplorerRef} rootPath={skillsRootPath} onFileOpen={handleOpenFile} onFileTreeChange={setSkillsFileTree} />
                        </div>
                        <div className="mx-2 mt-2 mb-3 min-w-0 py-2 px-2 text-[11px] text-black/50 text-center select-none">
                          {t('workspace.fileExplorer.skillsDragHint')}
                        </div>
                      </div>
                    </>
                  )}


                  {activeActivity === 'api' && <ApiPanel collapsed={leftPanelCollapsed} />}

                  {activeActivity === 'remote' && REMOTE_CONTROL_ENABLED && <RemoteControlPanel />}

                  <PanelHint
                    panelId={activeActivity}
                    message={t(`workspace.${activeActivity === 'explorer' ? 'fileExplorer' : activeActivity}.panelHint`)}
                  />
                </div>
              )}
            </div>
          )}

          {/* ===== 中间：工作区 (Workspace) ===== */}
          {!isCompactWindow && !isSidebarMode && workTabs.length > 0 && !isExploreFullscreen && (
            <div className="flex-1 flex flex-col min-w-0 bg-canvas overflow-hidden">
              {/* 第二层：Work Tabs (现在是中间列的顶层) */}
              {!viewerFullscreen && workTabs.length > 0 && (
                <header data-tour="work-tabs" className="flex items-end px-0 h-[32px] bg-[#F2F1EE] border-b border-divider flex-shrink-0 relative z-20">
                  <div
                    ref={workTabsScrollRef}
                    className="flex h-full items-end flex-1 min-w-0 scrollbar-thin-horizontal"
                    onWheel={(e) => {
                      // 将垂直滚轮转换为横向滚动
                      if (e.deltaY !== 0) {
                        e.currentTarget.scrollLeft += e.deltaY;
                        e.preventDefault();
                      }
                    }}
                  >
                    {workTabs.map((tab) => {
                      const isActive = tab.id === activeTabId;
                      return (
                        <div
                          key={tab.id}
                          onClick={() => setActiveTabId(tab.id)}
                          className={`
                          group flex items-center gap-2 px-3 h-full min-w-[120px] max-w-[200px] text-xs font-medium select-none cursor-pointer border-r border-divider relative flex-shrink-0
                          ${isActive ? 'bg-[#F8F9FA] text-black/90' : 'bg-transparent text-black/50 hover:bg-black/5 hover:text-black/80'}
                        `}
                          style={isActive ? { marginBottom: '-1px', height: '33px', borderBottom: '1px solid #F8F9FA', zIndex: 10 } : {}}
                        >
                          {isActive && <div className="absolute top-0 left-0 right-0 h-[2px] bg-orange-500" />}
                          {tab.type === 'file' ? (
                            <FileText className="w-3.5 h-3.5 flex-shrink-0" />
                          ) : (
                            <GitBranch className="w-3.5 h-3.5 flex-shrink-0" />
                          )}
                          <span className="truncate flex-1">{tab.title}</span>

                          {/* Close Button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              closeWorkTab(tab.id);
                            }}
                            className={`
                            p-0.5 rounded-sm hover:bg-black/10 hover:text-red-500 transition-colors
                            ${isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}
                          `}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  {isChatPanelCollapsed && (
                    <div className="flex items-center h-full flex-shrink-0 pr-1">
                      <WindowControlButton
                        icon={<PanelRightOpen className="w-3.5 h-3.5" />}
                        title={t('workspace.chat.expandPanel')}
                        onClick={() => setIsChatPanelCollapsed(false)}
                        hoverColor={undefined}
                      />
                    </div>
                  )}
                </header>
              )}

              {/* 主视图区域 */}
              <div data-tour="main-viewer" className="flex-1 min-h-0 relative bg-[#F8F9FA] z-10">
                {workTabs.length > 0 ? (
                  workTabs.map((tab) => {
                    const isActive = tab.id === activeTabId;
                    // 使用 visibility 而非 display:none，避免多个 React Flow 实例互相干扰
                    const wrapperStyle: React.CSSProperties = {
                      position: 'absolute',
                      inset: 0,
                      width: '100%',
                      height: '100%',
                      visibility: isActive ? 'visible' : 'hidden',
                      pointerEvents: isActive ? 'auto' : 'none',
                    };

                    if (tab.type === 'file') {
                      return (
                        <div key={tab.id} style={wrapperStyle}>
                          <FileViewer
                            filePath={tab.data?.filePath ?? ''}
                            fileName={tab.data?.fileName || tab.title}
                            onClose={() => closeWorkTab(tab.id)}
                            onFileOpen={handleOpenFile}
                          />
                        </div>
                      );
                    }

                    // Workflow tabs: 只渲染当前活动的，避免多个 React Flow 实例互相干扰
                    if (!isActive) {
                      return null;
                    }

                    return (
                      <div key={tab.id} style={wrapperStyle}>
                        <WorkflowEditor
                          key={tab.data?.workflowId || tab.id}
                          workflowId={tab.data?.workflowId}
                          onNodeApiReady={handleNodeApiReady}
                          onNodeSelect={handleWorkflowNodeSelect}
                        />
                      </div>
                    );
                  })
                ) : null}
              </div>
            </div>
          )}

          {/* ===== 右侧：助手区 (Assistant) ===== */}
          <div
            data-tour="chat-panel"
            className={`flex flex-col bg-canvas z-10 h-full transition-all duration-200 border-l border-divider ${viewerFullscreen || (!isSidebarMode && isChatPanelCollapsed) ? 'pointer-events-none border-l-0' : ''
              }`}
            style={{
              width: viewerFullscreen ? 0 : (!isSidebarMode && isChatPanelCollapsed) ? 0 : (isCompactWindow || isSidebarMode || workTabs.length === 0 || isExploreFullscreen) ? '100%' : rightWidth,
              overflow: 'hidden'
            }}
          >
            {/* 第二层：聊天工具栏 (Chat Toolbar / Tab Bar) - 现在是右侧列的顶层，与工作区Tabs对齐 */}
            <div className={`flex items-end justify-between h-[32px] border-b border-divider bg-[#F2F1EE] flex-shrink-0 pl-0 pr-2 ${!isCompactWindow ? 'border-l border-divider' : ''}`}>
              {/* 左侧：Chat Tabs - 可横向滚动，隐藏滚动条，支持滚轮横向滚动 */}
              <div
                ref={chatTabsScrollRef}
                className="flex items-end h-full gap-0 flex-1 min-w-0 scrollbar-thin-horizontal"
                onWheel={(e) => {
                  // 将垂直滚轮转换为横向滚动
                  if (e.deltaY !== 0) {
                    e.currentTarget.scrollLeft += e.deltaY;
                    e.preventDefault();
                  }
                }}
              >
                {chatTabs.map((tab) => {
                  const isActive = tab.id === activeChatTabId;
                  return (
                    <div
                      key={tab.id}
                      className={`group flex items-center gap-1.5 px-3 h-full text-xs font-medium select-none cursor-pointer relative transition-colors ${isActive
                        ? 'bg-canvas text-black/90 border-r border-divider'
                        : 'text-black/50 hover:text-black/70 hover:bg-black/5'
                        } ${isActive ? 'top-[1px]' : ''}`}
                      onClick={() => switchChatTab(tab.id)}
                    >
                      {/* 顶部橙色高亮条（仅活动 tab） */}
                      {isActive && (
                        <div className="absolute top-0 left-0 right-0 h-[2px] bg-orange-500" />
                      )}
                      <span className="truncate max-w-[120px]">{tab.title}</span>
                      {/* 关闭按钮 */}
                      {chatTabs.length > 1 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            closeChatTab(tab.id);
                          }}
                          className={`p-0.5 rounded hover:bg-black/10 ${isActive ? 'opacity-60 hover:opacity-100' : 'opacity-0 group-hover:opacity-60 hover:!opacity-100'
                            }`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 右侧：聊天功能按钮 */}
              <div className="flex items-center gap-1 h-full flex-shrink-0">
                <WindowControlButton
                  icon={<Plus className="w-3.5 h-3.5" />}
                  title={t('workspace.header.newChat')}
                  onClick={addNewChatTab}
                />
                {!isSidebarMode && workTabs.length > 0 && (
                  <WindowControlButton
                    icon={isChatPanelCollapsed ? <PanelRightOpen className="w-3.5 h-3.5" /> : <ArrowRightToLine className="w-3.5 h-3.5" />}
                    title={isChatPanelCollapsed ? t('workspace.chat.expandPanel') : t('workspace.chat.collapsePanel')}
                    onClick={() => {
                      if (isExploreFullscreen) {
                        setExploreFullscreen(false);
                        return;
                      }
                      if (!isChatPanelCollapsed && isCompactWindow) {
                        setIsCompactWindow(false);
                      }
                      setIsChatPanelCollapsed(!isChatPanelCollapsed);
                    }}
                    hoverColor={undefined}
                  />
                )}
              </div>
            </div>

            <div className="flex-1 min-h-0 relative overflow-hidden">
              <ChatPanel
                ref={chatPanelRef}
                onChatIdChange={updateCurrentTabChatId}
                fileTree={fileTree}
                onBeforeSend={async () => {
                  const explorerOk = await runUploadBeforeSend();
                  if (!explorerOk) return false;
                  const skillsOk = await runSkillsUploadBeforeSend();
                  if (!skillsOk) return false;
                  return true;
                }}
                onNodeEnd={() => {
                  handleSyncFiles(true);
                }}
                syncProgress={chatSyncProgress}
                onCancelSync={handleChatCancelSync}
                onForkWorkflow={(workflowId) => handleOpenWorkflow(workflowId)}
                onExploreSelectAgent={(agentId) => chatPanelRef.current?.selectAgent?.(agentId)}
                onCollapse={handleCollapse}
                onMessageSent={() => {
                  if (isSidebarMode || isCompactWindow) return;
                  setIsSidebarMode(true);
                  (window.electron as any)?.shrinkWindow?.();
                }}
                projectId={currentProject?.id}
                hasWorkspaceTabs={workTabs.length > 0 && !isExploreFullscreen}
              />
            </div>
          </div>

          {/* Activity Bar 宽度拖拽 */}
          {!isCompactWindow && !viewerFullscreen && !isSidebarMode && !leftPanelCollapsed && (
            <div
              className="absolute top-0 bottom-0 w-[6px] cursor-col-resize z-50 flex justify-center group"
              style={{ left: activityBarWidth - 3 }}
              onMouseDown={(e) => {
                isDraggingActivityBar.current = true;
                e.preventDefault();
              }}
            >
              <div className="w-[2px] h-full bg-orange-300 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          )}
          {!isCompactWindow && !viewerFullscreen && !isSidebarMode && activeActivity && activeActivity !== 'explore' && (
            <div
              className="absolute top-0 bottom-0 w-[10px] cursor-col-resize z-50 flex justify-center group"
              style={{ left: (leftPanelCollapsed ? 52 : activityBarWidth) + leftWidth - 5 }}
              onMouseDown={(e) => {
                isDraggingLeft.current = true;
                e.preventDefault();
              }}
            >
              <div className="w-[3px] h-full bg-orange-300 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          )}

          {!isCompactWindow && !viewerFullscreen && !isSidebarMode && !isChatPanelCollapsed && workTabs.length > 0 && !isExploreFullscreen && (
            <div
              className="absolute top-0 bottom-0 w-[10px] cursor-col-resize z-50 flex justify-center group"
              style={{ right: rightWidth - 5 }}
              onMouseDown={(e) => {
                isDraggingRight.current = true;
                e.preventDefault();
              }}
            >
              <div className="w-[3px] h-full bg-orange-300 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          )}
        </div>
      </div>

      {/* Onboarding Welcome Modal */}
      <WelcomeModal
        open={showWelcome}
        onStartTour={startTour}
        onSkip={skipWelcome}
      />
    </>
  );
});

export default WorkspacePage;
