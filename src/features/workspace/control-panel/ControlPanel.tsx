import React, { useState, useMemo, useEffect, useCallback, useRef, forwardRef, useImperativeHandle } from 'react';
import { Monitor, GitBranch, Plus, Maximize2, Minimize2, ChevronUp, ChevronDown, X, File } from 'lucide-react';
import { WorkflowOverview, NODE_CONFIGS, useWorkflow } from '@/features/workflow';
import type { WorkflowNode } from '@/features/workflow';
import { AGENTS } from '@/features/chat/config';
import { parseQuickStartMessage } from '@/features/workflow/utils/quickStartParser';
import type { ControlTab, AgentTarget } from './types';
import { AgentTargetContent } from './components/AgentTargetContent';
import { useVmSpecs } from './hooks/useVmSpecs';
import { WorkflowNodeDetails } from './components/WorkflowNodeDetails';
import { NodeSkillsInline } from './components/NodeSkillsInline';
import { NodeModelInline } from './components/NodeModelInline';
import { ORCHESTRATOR_AGENT_DEFAULT_MODEL, ORCHESTRATOR_AGENT_MODELS } from './components/node-details/modelConfig';
import { NodeToolsInline } from './components/NodeToolsInline';
import { FIELD_LABEL_CLASS, FIELD_LABEL_WRAP_CLASS, FIELD_TEXTAREA_CLASS } from './components/node-details/formStyles';
import { InlineMenuSelect } from './components/node-details/InlineMenuSelect';
import { ACTION_TYPES } from './components/node-details/ComputerUseNodeDetails';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { VM_ENABLED } from '@/config/runtimeEnv';

export interface ControlPanelRef {
  selectTarget: (id: string) => void;
  createVm: () => void;
}

export type ControlPanelMode = 'normal' | 'maximized' | 'collapsed';

interface ControlPanelProps {
  activeTab: ControlTab;
  onTabChange: (tab: ControlTab) => void;
  onOpenVm?: (vmId: string, title: string, vmName?: string) => void;
  onOpenWorkflow?: (workflowId?: string, title?: string) => void;
  selectedWorkflowNode?: WorkflowNode | null;
  onUpdateWorkflowNode?: (nodeId: string, patch: Record<string, any>) => void;
  onDeleteWorkflow?: (workflowId: string) => void;
  onDeleteEnvironment?: (envId: string) => void;
  // Panel mode controls
  panelMode?: ControlPanelMode;
  onPanelModeChange?: (mode: ControlPanelMode) => void;
  // Resize controls
  onResizeStart?: (e: React.MouseEvent) => void;
  // Workflow selection (from outside, e.g. sidebar click)
  activeWorkflowId?: string | null;
  // Workflow selection change callback
  onWorkflowSelect?: (workflowId: string | null) => void;
}

type EnvironmentConfig = {
  id: string;
  type: 'local' | 'vm';
  name: string;     // display name
  vmName?: string;  // hyper-v name
  deletable?: boolean;
};

const ControlPanel = forwardRef<ControlPanelRef, ControlPanelProps>(({
  activeTab,
  onTabChange,
  onOpenVm,
  onOpenWorkflow,
  selectedWorkflowNode,
  onUpdateWorkflowNode,
  onDeleteWorkflow,
  onDeleteEnvironment,
  panelMode = 'normal',
  onPanelModeChange,
  onResizeStart,
  activeWorkflowId,
  onWorkflowSelect,
}, ref) => {
  // env 列表（从 config 读取）
  const [envs, setEnvs] = useState<EnvironmentConfig[]>([]);
  // env runtime 状态（不写入 config）
  const [vmRuntime, setVmRuntime] = useState<Record<string, { available: boolean; status: 'running' | 'off' | 'unknown'; actualVmName?: string | null }>>({});

  // 选中的目标（用于查看详情）
  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(null);
  
  // 激活的目标（用于AI执行）- from shared Zustand store
  const activeTargetId = useWorkspaceStore((s) => s.activeTargetId);
  const setActiveTargetId = useWorkspaceStore((s) => s.setActiveTargetId);

  // workflow selection: single source of truth from parent
  const selectedWorkflowId = activeWorkflowId ?? null;
  const { workflow: selectedWorkflow, update: updateSelectedWorkflow } = useWorkflow(selectedWorkflowId);
  const canEditWorkflowMeta = !!selectedWorkflow && !selectedWorkflow.is_public;
  const [isEditingWorkflowMeta, setIsEditingWorkflowMeta] = useState(false);
  const [isEditingWorkflowName, setIsEditingWorkflowName] = useState(false);
  const [draftWorkflowName, setDraftWorkflowName] = useState('');
  const [draftWorkflowDescription, setDraftWorkflowDescription] = useState('');
  const workflowDescRef = useRef<HTMLTextAreaElement | null>(null);
  const workflowNameInputRef = useRef<HTMLInputElement | null>(null);

  // Quick Start Messages
  const [draftQuickStartMessages, setDraftQuickStartMessages] = useState<string[]>([]);
  const [editingQuickStartIndex, setEditingQuickStartIndex] = useState<number | null>(null);
  const quickStartInputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // keep draft in sync (avoid overriding while user is typing)
  useEffect(() => {
    if (!selectedWorkflowId || !selectedWorkflow) {
      if (!isEditingWorkflowMeta) {
        setDraftWorkflowName('');
        setDraftWorkflowDescription('');
        setDraftQuickStartMessages([]);
      }
      return;
    }
    if (isEditingWorkflowMeta) return;
    setDraftWorkflowName(selectedWorkflow.name || '');
    setDraftWorkflowDescription(selectedWorkflow.description || '');
    setDraftQuickStartMessages(selectedWorkflow.quick_start_messages || []);
  }, [selectedWorkflowId, selectedWorkflow, isEditingWorkflowMeta]);

  // autosize workflow description
  useEffect(() => {
    const el = workflowDescRef.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = `${el.scrollHeight}px`;
  }, [draftWorkflowDescription]);

  // focus workflow name input when entering edit mode
  useEffect(() => {
    if (!isEditingWorkflowName) return;
    const t = window.setTimeout(() => workflowNameInputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [isEditingWorkflowName]);

  const commitWorkflowMeta = useCallback(async () => {
    if (!selectedWorkflow || !canEditWorkflowMeta) return;
    const nextName = draftWorkflowName.trim();
    const nextDesc = draftWorkflowDescription.trim();
    if (!nextName) {
      setDraftWorkflowName(selectedWorkflow.name || '');
      setDraftWorkflowDescription(selectedWorkflow.description || '');
      return;
    }
    const prevDesc = selectedWorkflow.description || '';
    if (nextName === selectedWorkflow.name && nextDesc === prevDesc) return;
    try {
      await updateSelectedWorkflow({ name: nextName, description: nextDesc });
    } catch (err) {
      console.error('Failed to update workflow meta:', err);
      setDraftWorkflowName(selectedWorkflow.name || '');
      setDraftWorkflowDescription(selectedWorkflow.description || '');
    }
  }, [
    selectedWorkflow,
    canEditWorkflowMeta,
    draftWorkflowName,
    draftWorkflowDescription,
    updateSelectedWorkflow,
  ]);

  // Quick Start Message handlers
  const handleAddQuickStartMessage = useCallback(() => {
    if (!canEditWorkflowMeta) return;
    if (draftQuickStartMessages.length >= 5) return;
    const newMessages = [...draftQuickStartMessages, ''];
    setDraftQuickStartMessages(newMessages);
    setEditingQuickStartIndex(newMessages.length - 1);
    // Focus the new input after render
    setTimeout(() => {
      quickStartInputRefs.current[newMessages.length - 1]?.focus();
    }, 0);
  }, [canEditWorkflowMeta, draftQuickStartMessages]);

  const handleQuickStartMessageChange = useCallback((index: number, value: string) => {
    const newMessages = [...draftQuickStartMessages];
    newMessages[index] = value;
    setDraftQuickStartMessages(newMessages);
  }, [draftQuickStartMessages]);

  const handleQuickStartMessageBlur = useCallback(async (index: number) => {
    setEditingQuickStartIndex(null);
    setIsEditingWorkflowMeta(false);
    if (!selectedWorkflow || !canEditWorkflowMeta) return;
    
    // Filter out empty messages
    const filteredMessages = draftQuickStartMessages.filter(msg => msg.trim() !== '');
    setDraftQuickStartMessages(filteredMessages);
    
    // Check if changed
    const prevMessages = selectedWorkflow.quick_start_messages || [];
    if (JSON.stringify(filteredMessages) === JSON.stringify(prevMessages)) return;
    
    try {
      await updateSelectedWorkflow({ quick_start_messages: filteredMessages });
    } catch (err) {
      console.error('Failed to update quick start messages:', err);
      setDraftQuickStartMessages(selectedWorkflow.quick_start_messages || []);
    }
  }, [selectedWorkflow, canEditWorkflowMeta, draftQuickStartMessages, updateSelectedWorkflow]);

  const handleRemoveQuickStartMessage = useCallback(async (index: number) => {
    if (!canEditWorkflowMeta) return;
    const newMessages = draftQuickStartMessages.filter((_, i) => i !== index);
    setDraftQuickStartMessages(newMessages);
    
    if (!selectedWorkflow) return;
    try {
      await updateSelectedWorkflow({ quick_start_messages: newMessages });
    } catch (err) {
      console.error('Failed to remove quick start message:', err);
      setDraftQuickStartMessages(selectedWorkflow.quick_start_messages || []);
    }
  }, [canEditWorkflowMeta, draftQuickStartMessages, selectedWorkflow, updateSelectedWorkflow]);

  // 加载 environments 配置（并保证包含 This PC）
  useEffect(() => {
    let cancelled = false;
    const loadEnvs = async () => {
      try {
        // 重要：区分 “配置里没有 environments（首次运行/未初始化）” vs “用户明确配置过（可能已删除所有 VM）”
        // 否则会出现用户删除后，下次启动又被自动补回的情况
        let loaded: EnvironmentConfig[] = [];
        let hasEnvironmentsKey = false;
        if (window.electron?.getAppConfig) {
          const fullConfig = await window.electron.getAppConfig();
          hasEnvironmentsKey =
            !!fullConfig && Object.prototype.hasOwnProperty.call(fullConfig, 'environments');
          loaded = (fullConfig?.environments as EnvironmentConfig[]) || [];
        }

        // ensure local exists
        const hasLocal = loaded.some(e => e.id === 'local' || e.type === 'local');
        if (!hasLocal) {
          loaded = [
            {
              id: 'local',
              type: 'local',
              name: 'This PC',
              deletable: false,
            },
            ...loaded,
          ];
        } else {
          // normalize local
          loaded = loaded.map(e =>
            e.type === 'local' || e.id === 'local'
              ? { ...e, id: 'local', type: 'local', name: 'This PC', deletable: false }
              : e
          );
        }

        // migration: 仅在首次运行（配置里还没有 environments key）时才自动补默认 VM
        // 如果用户已经有 environments（哪怕只有 This PC），则尊重用户，不自动补回 VM
        const hasVm = loaded.some(e => e.type === 'vm');
        if (VM_ENABLED && !hasEnvironmentsKey && !hasVm && window.electron?.checkVmExists) {
          try {
            const r = await window.electron.checkVmExists('UseIt-Dev-VM');
            if (r?.exists && r.vmName) {
              loaded = [
                ...loaded,
                { id: 'vm-default', type: 'vm', name: r.vmName, vmName: r.vmName, deletable: true },
              ];
            }
          } catch {
            // ignore
          }
        }

        // 写回修复后的配置（仅在可用时）
        if (window.electron?.setAppConfig) {
          window.electron.setAppConfig({ environments: loaded }).catch(() => {});
        }

        if (!cancelled) setEnvs(loaded);
      } catch (e) {
        if (!cancelled) {
          setEnvs([{ id: 'local', type: 'local', name: 'This PC', deletable: false }]);
        }
      }
    };
    loadEnvs();
    return () => {
      cancelled = true;
    };
  }, []);

  // 监听 environments 更新事件（例如 ScreenViewer 在 ISO 选择后同步名称）
  useEffect(() => {
    const reload = async () => {
      try {
        if (!window.electron?.getAppConfig) return;
        let loaded: EnvironmentConfig[] = (await window.electron.getAppConfig('environments')) || [];

        // ensure local exists
        const hasLocal = loaded.some(e => e.id === 'local' || e.type === 'local');
        if (!hasLocal) {
          loaded = [
            { id: 'local', type: 'local', name: 'This PC', deletable: false },
            ...loaded,
          ];
        } else {
          loaded = loaded.map(e =>
            e.type === 'local' || e.id === 'local'
              ? { ...e, id: 'local', type: 'local', name: 'This PC', deletable: false }
              : e
          );
        }

        setEnvs(loaded);
      } catch {
        // ignore
      }
    };

    const handler = () => {
      reload();
    };
    window.addEventListener('environments-updated', handler as EventListener);
    return () => {
      window.removeEventListener('environments-updated', handler as EventListener);
    };
  }, []);

  // 根据 envs 刷新 VM runtime（exists + status）
  const refreshVmRuntime = useCallback(async () => {
    if (!window.electron?.checkVmExists || !window.electron?.getVmStatus) return;
    const vmEnvs = envs.filter(e => e.type === 'vm');
    if (vmEnvs.length === 0) return;

    const next: Record<string, { available: boolean; status: 'running' | 'off' | 'unknown'; actualVmName?: string | null }> = {};
    for (const e of vmEnvs) {
      try {
        const pattern = e.vmName || e.name;
        const r = await window.electron.checkVmExists(pattern);
        if (!r?.exists || !r.vmName) {
          next[e.id] = { available: false, status: 'unknown', actualVmName: null };
          continue;
        }
        let status: 'running' | 'off' | 'unknown' = 'unknown';
        try {
          const s = await window.electron.getVmStatus(r.vmName);
          status = s === 'Running' ? 'running' : s === 'Off' ? 'off' : 'unknown';
        } catch {
          // ignore
        }
        next[e.id] = { available: true, status, actualVmName: r.vmName };
      } catch {
        next[e.id] = { available: false, status: 'unknown', actualVmName: null };
      }
    }
    setVmRuntime(next);
  }, [envs]);

  useEffect(() => {
    refreshVmRuntime();
  }, [refreshVmRuntime]);

  // 当 VM 连接/关机等事件发生时，刷新右侧 Available 的状态（避免左侧 Running 但右侧 Unknown）
  useEffect(() => {
    const handleVmConnected = () => refreshVmRuntime();
    const handleShutdownRequest = () => {
      setTimeout(refreshVmRuntime, 1000);
      setTimeout(refreshVmRuntime, 3000);
    };

    window.addEventListener('vm-connected', handleVmConnected as EventListener);
    window.addEventListener('request-vm-shutdown', handleShutdownRequest as EventListener);
    return () => {
      window.removeEventListener('vm-connected', handleVmConnected as EventListener);
      window.removeEventListener('request-vm-shutdown', handleShutdownRequest as EventListener);
    };
  }, [refreshVmRuntime]);

  // 轻量定时刷新（避免状态长期卡住）
  useEffect(() => {
    if (envs.filter(e => e.type === 'vm').length === 0) return;
    const t = setInterval(refreshVmRuntime, 15000);
    return () => clearInterval(t);
  }, [envs, refreshVmRuntime]);

  // 构建 targets（UI 使用）
  const targets: AgentTarget[] = useMemo(() => {
    return envs.map(e => {
      if (e.type === 'local') {
        return {
          id: 'local',
          type: 'local',
          name: 'This PC',
          deletable: false,
          available: true,
          status: 'running',
        };
      }
      const rt = vmRuntime[e.id];
      return {
        id: e.id,
        type: 'vm',
        name: e.name,
        vmName: e.vmName,
        deletable: e.deletable ?? true,
        available: rt?.available ?? false,
        status: rt?.status ?? 'unknown',
      };
    });
  }, [envs, vmRuntime]);

  const selectedVmName =
    targets.find(t => t.id === selectedTargetId)?.type === 'vm'
      ? (targets.find(t => t.id === selectedTargetId)?.vmName || targets.find(t => t.id === selectedTargetId)?.name)
      : undefined;

  const { specs: vmSpecs, refresh: refreshVmSpecs } = useVmSpecs(selectedVmName || 'UseIt-Dev-VM');

  // 获取当前选中的目标对象
  const selectedTarget = useMemo(() => {
    if (!selectedTargetId) return null;
    return targets.find(t => t.id === selectedTargetId) || null;
  }, [selectedTargetId, targets]);

  // 处理目标选择
  const handleTargetSelect = (target: AgentTarget | null) => {
    setSelectedTargetId(target?.id || null);
    // 注意：这里只处理查看详情，不自动设为 Active
    // 如果选择了 VM：总是尝试打开对应的 ScreenViewer tab（连接/安装都在那边完成）
    if (target?.type === 'vm') {
      onOpenVm?.(target.id, target.name, target.vmName || target.name);
    }
  };

  // 处理目标激活
  const handleTargetActivate = (id: string) => {
    setActiveTargetId(id);
  };


  const handleTabClick = (tab: ControlTab) => {
    onTabChange(tab);
  };

  const persistEnvs = (next: EnvironmentConfig[]) => {
    setEnvs(next);
    if (window.electron?.setAppConfig) {
      window.electron.setAppConfig({ environments: next }).catch(() => {});
    }
  };

  const handleDeleteEnvironment = (targetId: string) => {
    if (targetId === 'local') return;
    const target = targets.find(t => t.id === targetId);
    if (!target || target.type !== 'vm') return;

    // NOTE: 删除确认弹窗已改为在 Available 列表中内嵌展示（类似 ShutdownModal）
    // 这里收到的是用户已确认后的回调，因此不再使用系统 confirm
    // const ok = confirm(`Delete environment "${target.name}"?`);
    // if (!ok) return;

    const next = envs.filter(e => e.id !== targetId);
    persistEnvs(next);

    // 通知外部：用于关闭对应的 workspace tab
    onDeleteEnvironment?.(targetId);

    // 如果当前正在查看该条目，删除后回到 overview
    if (selectedTargetId === targetId) {
      setSelectedTargetId(null);
    }

    // 如果 active 指向被删除的环境，回退到 This PC
    if (activeTargetId === targetId) {
      setActiveTargetId('local');
    }
  };

  const handleCreateVm = () => {
    // 生成一个“未被占用”的 vmName（支持用户把 Available 名称同步成 vmName 的情况）
    // 规则：UseIt-Dev-VM-1/2/3...
    const vmEnvs = envs.filter(e => e.type === 'vm');
    const usedVmNames = new Set(
      vmEnvs
        .map(e => (e.vmName || '').trim())
        .filter(Boolean)
    );

    let idx = 1;
    let vmName = `UseIt-Dev-VM-${idx}`;
    while (usedVmNames.has(vmName)) {
      idx += 1;
      vmName = `UseIt-Dev-VM-${idx}`;
    }

    const displayName = `New Virtual Desktop ${idx}`;
    const id = `vm-${Date.now()}`;

    const next: EnvironmentConfig[] = [
      ...envs,
      { id, type: 'vm', name: displayName, vmName, deletable: true },
    ];
    persistEnvs(next);

    // 选中该条目（左侧显示详情），并打开 ScreenViewer 安装页
    setSelectedTargetId(id);
    onOpenVm?.(id, displayName, vmName);
  };

  useImperativeHandle(ref, () => ({
    selectTarget: (id: string) => {
      onTabChange('vm');
      const target = targets.find(t => t.id === id);
      if (target) {
        handleTargetSelect(target);
      }
    },
    createVm: () => {
      onTabChange('vm');
      handleCreateVm();
    }
  }), [onTabChange, targets, handleCreateVm]); // handleTargetSelect is stable enough or can be added to deps if extracted

  return (
    <div className="flex flex-col h-full bg-canvas">
      {/* Resize handle at top (only in normal mode) */}
      {panelMode === 'normal' && onResizeStart && (
        <div
          className="absolute top-0 left-0 right-0 h-[10px] cursor-row-resize z-20 flex items-center justify-center group -translate-y-1/2"
          onMouseDown={onResizeStart}
        >
          <div className="w-full h-[3px] bg-orange-300 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      )}
      {/* Header tabs */}
      <div className="flex items-center justify-between h-[30px] bg-canvas px-2 flex-shrink-0 border-t border-divider">
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleTabClick('workflow')}
            className={`flex items-center gap-2 px-3 h-[26px] rounded-sm text-[12px] font-medium select-none transition-colors ${
              activeTab === 'workflow'
                ? 'bg-black/5 text-black/90'
                : 'text-black/50 hover:bg-black/5 hover:text-black/80'
            }`}
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span>Workflow</span>
          </button>

          {VM_ENABLED && (
            <button
              onClick={() => handleTabClick('vm')}
              className={`flex items-center gap-2 px-3 h-[26px] rounded-sm text-[12px] font-medium select-none transition-colors ${
                activeTab === 'vm'
                  ? 'bg-black/5 text-black/90'
                  : 'text-black/50 hover:bg-black/5 hover:text-black/80'
              }`}
            >
              <Monitor className="w-3.5 h-3.5" />
              <span>Agent Environment</span>
            </button>
          )}
        </div>

        {/* Panel mode controls */}
        <div className="flex items-center gap-1">
          {/* Maximize/Restore button */}
          <button
            onClick={() => onPanelModeChange?.(panelMode === 'maximized' ? 'normal' : 'maximized')}
            className="flex items-center justify-center w-6 h-6 rounded-sm text-black/40 hover:bg-black/5 hover:text-black/70 transition-colors"
            title={panelMode === 'maximized' ? 'Restore panel' : 'Maximize panel'}
          >
            {panelMode === 'maximized' ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>

          {/* Collapse/Expand button */}
          <button
            onClick={() => onPanelModeChange?.(panelMode === 'collapsed' ? 'normal' : 'collapsed')}
            className="flex items-center justify-center w-6 h-6 rounded-sm text-black/40 hover:bg-black/5 hover:text-black/70 transition-colors"
            title={panelMode === 'collapsed' ? 'Expand panel' : 'Collapse panel'}
          >
            {panelMode === 'collapsed' ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'vm' ? (
          <div className="h-full flex">
            <div className="flex-1 flex flex-col overflow-hidden bg-canvas">
              <AgentTargetContent
                selectedTarget={selectedTarget}
                activeTargetId={activeTargetId}
                targets={targets}
                vmSpecs={vmSpecs}
                onRefreshVm={refreshVmSpecs}
                onSelectTarget={(id) => {
                  // 点击 Overview 卡片，查看详情
                  handleTargetSelect(targets.find(t => t.id === id) || null);
                }}
                onActivateTarget={handleTargetActivate}
                onCreateVm={handleCreateVm}
              />
            </div>
          </div>
        ) : (
          <div className="h-full flex">
            {/* Left: Workflow overview */}
            <div className="flex-1 flex flex-col overflow-hidden bg-canvas">
              {/* Workflow settings area - always shrink to content, scrollable when overflow */}
              {(!!selectedWorkflowNode || !!selectedWorkflowId) && (
                <div className="flex-shrink-0 max-h-full overflow-y-auto scrollbar-thin-overlay px-3 pt-1.5 pb-2">
                  <div className="min-w-0">
                    {selectedWorkflowNode ? (
                      <div className="flex items-center gap-2 overflow-hidden">
                        <div className="min-w-0 flex items-center gap-2 overflow-hidden flex-1">
                          <h3 className="text-[12px] font-semibold text-black/80 truncate flex-shrink min-w-[60px]">
                            {(selectedWorkflowNode.data as any).title || selectedWorkflowNode.data.type}
                          </h3>
                          {selectedWorkflowNode.data.type === 'computer-use' && (
                            <InlineMenuSelect
                              value={(selectedWorkflowNode.data as any).action_type || 'gui'}
                              options={ACTION_TYPES}
                              onChange={(value) => onUpdateWorkflowNode?.(selectedWorkflowNode.id, { action_type: value })}
                              align="left"
                              showIcon
                            />
                          )}
                          {NODE_CONFIGS[selectedWorkflowNode.data.type]?.definition ? (
                            <span className="text-[11px] text-black/45 truncate hidden lg:inline">
                              {NODE_CONFIGS[selectedWorkflowNode.data.type].definition}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center justify-end flex-shrink-0 gap-3">
                          {(selectedWorkflowNode.data.type === 'computer-use' ||
                            selectedWorkflowNode.data.type === 'tool-use' ||
                            selectedWorkflowNode.data.type === 'agent') && (
                            <NodeModelInline
                              node={selectedWorkflowNode}
                              onUpdate={onUpdateWorkflowNode}
                              {...(selectedWorkflowNode.data.type === 'agent'
                                ? { options: ORCHESTRATOR_AGENT_MODELS, defaultModel: ORCHESTRATOR_AGENT_DEFAULT_MODEL }
                                : {})}
                            />
                          )}
                          {selectedWorkflowNode.data.type === 'tool-use' && (
                            <NodeToolsInline node={selectedWorkflowNode} onUpdate={onUpdateWorkflowNode} />
                          )}
                          <NodeSkillsInline node={selectedWorkflowNode} onUpdate={onUpdateWorkflowNode} />
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-[12px] font-semibold text-black/80">Workflow</span>
                              {isEditingWorkflowName && canEditWorkflowMeta ? (
                                <input
                                  ref={workflowNameInputRef}
                                  value={draftWorkflowName}
                                  onChange={(e) => setDraftWorkflowName(e.target.value)}
                                  onFocus={() => setIsEditingWorkflowMeta(true)}
                                  onBlur={async () => {
                                    setIsEditingWorkflowName(false);
                                    setIsEditingWorkflowMeta(false);
                                    await commitWorkflowMeta();
                                  }}
                                  onKeyDown={async (e) => {
                                    if (e.key === 'Enter') {
                                      (e.currentTarget as HTMLInputElement).blur();
                                    }
                                    if (e.key === 'Escape') {
                                      setDraftWorkflowName(selectedWorkflow?.name || '');
                                      setDraftWorkflowDescription(selectedWorkflow?.description || '');
                                      setIsEditingWorkflowName(false);
                                      setIsEditingWorkflowMeta(false);
                                      (e.currentTarget as HTMLInputElement).blur();
                                    }
                                  }}
                                  placeholder="Select a workflow on the right…"
                                  size={Math.max(6, Math.min(28, ((draftWorkflowName || '').trim().length || 12) + 1))}
                                  className="w-auto max-w-[260px] h-[24px] px-2 text-[11px] bg-black/5 hover:bg-black/10 border border-transparent rounded-sm focus:outline-none focus:border-black/20 focus:bg-white placeholder:text-black/20 transition-colors"
                                />
                              ) : (
                                <button
                                  type="button"
                                  disabled={!canEditWorkflowMeta}
                                  onClick={() => {
                                    if (!canEditWorkflowMeta) return;
                                    setIsEditingWorkflowMeta(true);
                                    setIsEditingWorkflowName(true);
                                  }}
                                  className={`inline-flex items-center max-w-[260px] h-[24px] px-2 text-[11px] rounded-sm bg-black/5 text-black/80 transition-colors ${
                                    canEditWorkflowMeta ? 'hover:bg-black/10 cursor-text' : 'opacity-70 cursor-default'
                                  }`}
                                  title={draftWorkflowName || 'Select a workflow on the right…'}
                                >
                                  <span className="truncate">{draftWorkflowName || 'Select a workflow…'}</span>
                                </button>
                              )}
                            </div>
                          </div>
                        </div>

                        <div>
                          <div className={FIELD_LABEL_WRAP_CLASS}>
                            <span className={FIELD_LABEL_CLASS}>Description</span>
                          </div>
                          <textarea
                            ref={workflowDescRef}
                            value={draftWorkflowDescription}
                            onChange={(e) => setDraftWorkflowDescription(e.target.value)}
                            onFocus={() => setIsEditingWorkflowMeta(true)}
                            onBlur={async () => {
                              setIsEditingWorkflowMeta(false);
                              await commitWorkflowMeta();
                            }}
                            placeholder="Add a description…"
                            disabled={!canEditWorkflowMeta}
                            rows={1}
                            className={`${FIELD_TEXTAREA_CLASS} ${
                              canEditWorkflowMeta ? '' : 'opacity-80 cursor-default hover:bg-black/5'
                            }`}
                          />
                        </div>

                        {/* Quick Start Messages */}
                        <div>
                          <div className={FIELD_LABEL_WRAP_CLASS}>
                            <span className={FIELD_LABEL_CLASS}>Quick Start Messages</span>
                          </div>

                          <div className="flex flex-col gap-2">
                            {/* 已添加的消息列表 */}
                            {draftQuickStartMessages.map((msg, index) => (
                              <div key={index} className="relative group">
                                <input
                                  ref={(el) => { quickStartInputRefs.current[index] = el; }}
                                  type="text"
                                  value={msg}
                                  onChange={(e) => handleQuickStartMessageChange(index, e.target.value)}
                                  onFocus={() => {
                                    setIsEditingWorkflowMeta(true);
                                    setEditingQuickStartIndex(index);
                                  }}
                                  onBlur={() => handleQuickStartMessageBlur(index)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      e.currentTarget.blur();
                                    }
                                  }}
                                  placeholder="Enter a message..."
                                  disabled={!canEditWorkflowMeta}
                                  className={`w-full h-[32px] px-2 pr-7 text-[11px] bg-black/5 hover:bg-black/10 border border-black/10 rounded-sm focus:outline-none focus:border-black/30 focus:bg-white placeholder:text-black/20 transition-colors ${
                                    canEditWorkflowMeta ? '' : 'opacity-80 cursor-default hover:bg-black/5'
                                  }`}
                                />
                                {canEditWorkflowMeta && (
                                  <button
                                    type="button"
                                    onMouseDown={(e) => {
                                      e.preventDefault();
                                      handleRemoveQuickStartMessage(index);
                                    }}
                                    className="absolute right-1.5 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center text-black/30 hover:text-red-500 rounded-sm transition-colors opacity-0 group-hover:opacity-100"
                                    title="Remove message"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                )}
                                {msg.includes('@') && (
                                  <div className="flex flex-wrap items-center gap-0.5 mt-0.5 px-0.5">
                                    {parseQuickStartMessage(msg).map((seg, si) =>
                                      seg.type === 'text' ? (
                                        <span key={si} className="text-[10px] text-black/30">{seg.value}</span>
                                      ) : (
                                        <span key={si} className="inline-flex items-center gap-0.5 px-1 py-px bg-orange-50/80 border border-orange-200/60 rounded text-[10px] text-orange-700 font-medium">
                                          <File className="w-2.5 h-2.5" />
                                          {seg.name}
                                        </span>
                                      )
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}

                            {/* 添加按钮 */}
                            {canEditWorkflowMeta && draftQuickStartMessages.length < 5 && (
                              <button
                                type="button"
                                onClick={handleAddQuickStartMessage}
                                className="flex items-center justify-center gap-1.5 w-full h-[32px] bg-black/[0.03] hover:bg-black/[0.06] rounded-sm text-[11px] text-black/40 hover:text-black/60 transition-colors"
                              >
                                <Plus className="w-3.5 h-3.5" />
                                <span>Add quick start message</span>
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Dataset (coming soon) */}
                        <div>
                          <div className={FIELD_LABEL_WRAP_CLASS}>
                            <span className={FIELD_LABEL_CLASS}>Dataset</span>
                            <span className="text-[10px] text-black/30 ml-1">Coming soon</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Content - only render when there's actual content to show */}
              {selectedWorkflowNode ? (
                <div className="flex-1 overflow-hidden">
                  <WorkflowNodeDetails node={selectedWorkflowNode} onUpdate={onUpdateWorkflowNode} panelMode={panelMode} />
                </div>
              ) : !selectedWorkflowId ? (
                <div className="flex-1 overflow-hidden flex items-center justify-center">
                  <WorkflowOverview
                    onCreate={(workflow) => {
                      onWorkflowSelect?.(workflow.id);
                      onOpenWorkflow?.(workflow.id, workflow.name);
                    }}
                  />
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

export default ControlPanel;


