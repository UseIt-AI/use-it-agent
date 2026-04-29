import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { 
  Monitor, Box, Cpu, MemoryStick, HardDrive, 
  RefreshCw, Terminal, Zap, Eye, Shield, Activity, Lock,
  ArrowRight, AlertTriangle, ChevronDown, Settings, Server,
  Save, X, FileInput, Activity as ActivityIcon, Camera, ChevronRight
} from 'lucide-react';
import type { AgentTarget } from '../types';
import type { VmSpecsState } from '../hooks/useVmSpecs';
import { setVmSpecs, listVmSnapshots, createVmSnapshot, restoreVmSnapshot } from '../../screen-viewer/services/vmElectronApi';

type VmSnapshotNode = {
  id: string;
  name: string;
  parentId: string | null;
  createdAt: string;
  checkpointType: string;
  children: VmSnapshotNode[];
};

interface AgentTargetContentProps {
  selectedTarget: AgentTarget | null;
  activeTargetId?: string | null;  // 新增 activeTargetId
  vmSpecs?: VmSpecsState;
  onRefreshVm?: () => void;
  onSelectTarget?: (targetId: string) => void;
  onActivateTarget?: (targetId: string) => void;
  onCreateVm?: () => void;
  targets?: AgentTarget[]; // 新增 targets 列表用于查找 active target info
}

export function AgentTargetContent({
  selectedTarget,
  activeTargetId,
  vmSpecs,
  onRefreshVm,
  onSelectTarget,
  onActivateTarget,
  onCreateVm,
  targets,
}: AgentTargetContentProps) {
  if (!selectedTarget) {
    return <IntroductionContent onSelectTarget={onSelectTarget} onCreateVm={onCreateVm} activeTargetId={activeTargetId} targets={targets} />;
  }


  if (selectedTarget.type === 'local') {
    return (
      <LocalMachineContent 
        target={selectedTarget}
        isActive={selectedTarget.id === activeTargetId}
        onActivate={() => onActivateTarget?.(selectedTarget.id)}
      />
    );
  }

  return (
    <VirtualMachineContent 
      target={selectedTarget} 
      isActive={selectedTarget.id === activeTargetId}
      onActivate={() => onActivateTarget?.(selectedTarget.id)}
      vmSpecs={vmSpecs} 
      onRefresh={onRefreshVm} 
      onOpenVmTab={() => onSelectTarget?.(selectedTarget.id)}
    />
  );
}

// 统一的左右分栏容器
function SplitLayout({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas">
      <div className="flex h-full">
        {/* 左侧：核心信息 (40%) */}
        <div className="w-[40%] min-w-[240px] flex flex-col justify-center p-6 pr-8">
          {left}
        </div>
        
        {/* 右侧：详细参数 (60%) */}
        <div className="flex-1 flex flex-col justify-center p-6 pl-0">
          {right}
        </div>
      </div>
    </div>
  );
}

function Tooltip({ children, content }: { children: React.ReactNode; content: string }) {
  const [coords, setCoords] = useState<{ x: number, y: number } | null>(null);

  const handleMouseEnter = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setCoords({
      x: rect.left + rect.width / 2,
      y: rect.top
    });
  };

  const handleMouseLeave = () => {
    setCoords(null);
  };

  return (
    <>
      <div className="relative flex items-center" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
        {children}
      </div>
      {coords && createPortal(
        <div 
          className="fixed p-2 bg-white border border-black/10 shadow-xl text-xs text-black/70 rounded-sm z-[9999] text-center w-48 pointer-events-none animate-in fade-in duration-200"
          style={{
            left: coords.x,
            top: coords.y - 8,
            transform: 'translate(-50%, -100%)'
          }}
        >
          {content}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-[1px] border-4 border-transparent border-t-white" />
        </div>,
        document.body
      )}
    </>
  );
}


// ==========================================
// Overview 页面 (极致紧凑版)
// ==========================================
function IntroductionContent({ 
  onSelectTarget, 
  onCreateVm,
  activeTargetId, 
  targets 
}: { 
  onSelectTarget?: (id: string) => void;
  onCreateVm?: () => void;
  activeTargetId?: string | null;
  targets?: AgentTarget[];
}) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  
  // 获取当前激活的 Target 名称
  const activeTargetName = targets?.find(t => t.id === activeTargetId)?.name;

  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas flex flex-col py-2 pr-2 pl-4">
      {/* 顶部标题栏：极度压缩 */}
      <div className="flex items-center justify-between mb-1.5 flex-shrink-0 h-5">
        <h2 className="text-xs font-bold text-black/60 flex items-center gap-2">
          Create Environment
          <span className="w-px h-3 bg-black/10"></span>
          <span className="text-[12px] text-black/60 font-normal">
             Choose where the AI agent will execute its tasks. We currently provide two options:
          </span>
        </h2>

        {/* 显示当前 Active Target - 移至最右侧，并支持下拉 */}
        {activeTargetName && (
           <div className="relative z-20">
             <button 
               onClick={() => setIsDropdownOpen(!isDropdownOpen)}
               className="flex items-center gap-2 hover:bg-black/5 px-2 py-0.5 rounded-sm transition-colors cursor-pointer"
             >
               <div className="flex items-center gap-1.5">
                 <span className="text-[9px] font-bold text-black/40 uppercase tracking-wider">Active:</span>
                 
                 <div className="relative flex items-center justify-center">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-20 animate-ping"></span>
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                 </div>
                 
                 <span className="text-[10px] font-bold text-black/80 tracking-tight">
                   {activeTargetName}
                 </span>
                 
                 <ChevronDown className="w-3 h-3 text-black/40 ml-0.5" />
               </div>
             </button>

             {isDropdownOpen && (
               <>
                 <div className="fixed inset-0 z-10" onClick={() => setIsDropdownOpen(false)} />
                 <div className="absolute right-0 top-full mt-1 w-[180px] bg-white border border-divider shadow-xl rounded-sm z-20 overflow-hidden flex flex-col animate-in fade-in slide-in-from-top-1 duration-200">
                    <div className="px-3 py-1.5 border-b border-divider/50 flex items-center justify-center bg-black/[0.02]">
                       <span className="text-[9px] font-bold text-black/40 uppercase tracking-wider">Switch Environment</span>
                    </div>
                    <div className="py-1 flex flex-col">
                      {targets?.map(target => {
                         const isActive = target.id === activeTargetId;
                         return (
                           <button
                             key={target.id}
                             disabled={!target.available}
                             onClick={(e) => {
                               e.stopPropagation(); // 防止冒泡触发卡片点击
                               onSelectTarget?.(target.id);
                               setIsDropdownOpen(false);
                             }}
                             className={`
                               flex items-center gap-2 px-3 py-1.5 text-left text-[11px] transition-colors w-full
                               ${isActive ? 'bg-orange-50 text-orange-700' : 'text-black/70 hover:bg-black/5'}
                               ${!target.available ? 'opacity-50 cursor-not-allowed' : ''}
                             `}
                           >
                             <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                target.status === 'running' ? 'bg-emerald-500' : 
                                target.available ? 'bg-blue-500' : 'bg-neutral-300'
                             }`} />
                             <span className="font-medium truncate flex-1">{target.name}</span>
                             {isActive && <div className="w-1 h-1 rounded-full bg-orange-500" />}
                           </button>
                         );
                      })}
                    </div>
                 </div>
               </>
             )}
           </div>
        )}
      </div>

      {/* 内容区域 - Centered Sentence Style */}
      <div className="flex-1 overflow-hidden flex items-center justify-center">
        <div className="flex items-center flex-wrap justify-center text-sm font-medium text-black/90 leading-loose">
            <span>Setup agent environment on</span>
            <Tooltip content="Run the agent directly on your current computer. This offers the best performance but requires caution.">
              <button 
                onClick={() => onSelectTarget?.('local')}
                className="inline-flex items-center gap-1.5 px-3 mx-2 bg-black text-white border border-black shadow-sm text-xs font-bold uppercase tracking-wide transition-all align-middle h-8 hover:bg-black/90"
              >
                <Monitor className="w-3 h-3" />
                This PC
              </button>
            </Tooltip>
            <span>or</span>
            <Tooltip content="Create an isolated virtual desktop for safer runs.">
              <button 
                onClick={() => onCreateVm?.()}
                className="inline-flex items-center gap-1.5 px-3 mx-2 bg-white border border-black/10 text-black/70 hover:border-black/30 hover:text-black transition-all text-xs font-bold uppercase tracking-wide align-middle h-8 hover:shadow-sm"
              >
                <Box className="w-3 h-3" />
                Create VM
                <span className="ml-1.5 px-1.5 py-0.5 text-[10px] border border-black/20 text-black/60 font-medium normal-case tracking-normal">Advanced</span>
              </button>
            </Tooltip>
            <span>.</span>
        </div>
      </div>
    </div>
  );
}

// 本机内容
function LocalMachineContent({
  target,
  isActive,
  onActivate
}: {
  target: AgentTarget;
  isActive: boolean;
  onActivate: () => void;
}) {
  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas flex flex-col py-2 pr-2 pl-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 flex-shrink-0 h-6">
        <div className="flex items-center gap-2">
          <Monitor className="w-4 h-4 text-black/60" />
          <h2 className="text-sm font-bold text-black/80">This PC</h2>
          <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-sm tracking-wide ml-2">
            Ready
          </span>
        </div>
        
        {/* Activate Button */}
        <button
          onClick={onActivate}
          disabled={isActive}
          className={`
            flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-colors
            ${isActive 
              ? 'bg-emerald-500/10 text-emerald-600 cursor-default' 
              : 'bg-black/5 text-black/60 hover:bg-black/10 hover:text-black/80'}
          `}
        >
          {isActive ? (
            <>
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="font-bold">Active</span>
            </>
          ) : (
            <span>Activate</span>
          )}
        </button>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-2">
        {/* Description */}
        <p className="text-[11px] text-black/60 leading-relaxed px-1">
          The agent will operate directly on your current operating system with user-level permissions. 
          This offers the best performance but requires caution.
        </p>

        {/* Warning Block */}
        <div className="w-fit p-3 bg-amber-50/50 border border-amber-100 rounded-sm flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <div className="flex flex-col gap-0.5">
            <h4 className="text-[10px] font-bold text-amber-800 uppercase tracking-wide">
              Live Environment Warning
            </h4>
            <p className="text-[10px] text-amber-900/70 leading-relaxed">
              Agent has full control over your mouse and keyboard. Do not interfere while it is running. Actions performed here are irreversible.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// VM 内容
function VirtualMachineContent({ 
  target,
  isActive,
  onActivate,
  vmSpecs, 
  onRefresh,
  onOpenVmTab,
}: { 
  target: AgentTarget;
  isActive: boolean;
  onActivate: () => void;
  vmSpecs?: VmSpecsState; 
  onRefresh?: () => void;
  onOpenVmTab?: () => void;
}) {
  const { t } = useTranslation();
  const isLoading = vmSpecs?.status === 'loading';
  const isRunning = vmSpecs?.state === 'running';
  // vmSpecs.state 在 hook 中为 'running' | 'off' | 'unknown'（小写）
  // 这里统一做标准化，避免大小写导致错误显示为 Stopped
  const vmState = (vmSpecs?.state ?? 'unknown').toLowerCase();
  const isUnknown = vmState === 'unknown';
  const isSettingsBlocked = isUnknown || isLoading;
  const [activeTab, setActiveTab] = useState<'monitor' | 'settings' | 'snapshots'>('monitor');
  const [snapshotMode, setSnapshotMode] = useState<'save' | 'no_save'>('save');
  const [snapshotDraftName, setSnapshotDraftName] = useState('');
  const [snapshots, setSnapshots] = useState<VmSnapshotNode[]>([]);
  const [snapshotExpandedIds, setSnapshotExpandedIds] = useState<Record<string, boolean>>({});
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotCreating, setSnapshotCreating] = useState(false);
  const [snapshotRestoringId, setSnapshotRestoringId] = useState<string | null>(null);
  const [snapshotCurrentId, setSnapshotCurrentId] = useState<string | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  
  const handleStopVm = () => {
    // 1. 触发全局事件，通知 ScreenViewer 打开关机弹窗
    const vmName = vmSpecs?.name || target.name;
    
    // 使用 setTimeout 确保 Tab 切换后再触发事件
    setTimeout(() => {
        window.dispatchEvent(new CustomEvent('request-vm-shutdown', { detail: { vmName } }));
    }, 100);

    // 2. 切换到 VM 详情页 (ScreenViewer Tab)
    onOpenVmTab?.();
  };

  const buildSnapshotTree = (items: Array<{ id: string; name: string; parentId: string | null; createdAt: string; checkpointType: string }>): VmSnapshotNode[] => {
    const nodeMap = new Map<string, VmSnapshotNode>();
    items.forEach((item) => {
      nodeMap.set(item.id, { ...item, children: [] });
    });

    const roots: VmSnapshotNode[] = [];
    items.forEach((item) => {
      const current = nodeMap.get(item.id);
      if (!current) return;
      if (item.parentId && nodeMap.has(item.parentId)) {
        nodeMap.get(item.parentId)?.children.push(current);
      } else {
        roots.push(current);
      }
    });

    const sortNodes = (nodes: VmSnapshotNode[]) => {
      nodes.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
      nodes.forEach((node) => sortNodes(node.children));
    };
    sortNodes(roots);
    return roots;
  };

  const vmNameForSnapshot = (vmSpecs?.name || target.vmName || target.name).trim();
  const toSnapshotErrorMessage = (error: any, fallbackKey: string) => {
    const message = String(error?.message || '');
    if (/listVmSnapshots not available|createVmSnapshot not available|restoreVmSnapshot not available/i.test(message)) {
      return t('workspace.snapshots.errors.apiNotAvailable');
    }
    return message || t(fallbackKey);
  };

  const loadSnapshots = async () => {
    if (!vmNameForSnapshot) return;
    setSnapshotLoading(true);
    setSnapshotError(null);
    try {
      const records = await listVmSnapshots(vmNameForSnapshot);
      const normalized = (records || []).map((record) => ({
        id: String(record.Id),
        name: String(record.Name || ''),
        parentId: record.ParentCheckpointId ? String(record.ParentCheckpointId) : null,
        createdAt: String(record.CreationTime || ''),
        checkpointType: String(record.CheckpointType || ''),
      }));
      setSnapshots(buildSnapshotTree(normalized));
    } catch (error: any) {
      setSnapshotError(toSnapshotErrorMessage(error, 'workspace.snapshots.errors.loadFailed'));
      setSnapshots([]);
    } finally {
      setSnapshotLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'snapshots') {
      void loadSnapshots();
    }
  }, [activeTab, vmNameForSnapshot]);

  const handleCreateSnapshot = async () => {
    if (!vmNameForSnapshot) return;
    setSnapshotCreating(true);
    setSnapshotError(null);
    try {
      const now = new Date();
      const autoName = `Snapshot-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
      await createVmSnapshot({
        vmName: vmNameForSnapshot,
        snapshotName: snapshotDraftName.trim() || autoName,
        saveState: snapshotMode === 'save',
      });
      setSnapshotDraftName('');
      await loadSnapshots();
    } catch (error: any) {
      setSnapshotError(toSnapshotErrorMessage(error, 'workspace.snapshots.errors.createFailed'));
    } finally {
      setSnapshotCreating(false);
    }
  };

  const toggleExpanded = (id: string) => {
    setSnapshotExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const collectSnapshotBranchIds = (nodes: VmSnapshotNode[], targetId: string | null): Set<string> => {
    if (!targetId) return new Set<string>();
    const path: string[] = [];
    const dfs = (items: VmSnapshotNode[]): boolean => {
      for (const item of items) {
        path.push(item.id);
        if (item.id === targetId) return true;
        if (dfs(item.children)) return true;
        path.pop();
      }
      return false;
    };
    if (!dfs(nodes)) return new Set<string>();
    return new Set<string>(path);
  };

  const handleRestoreSnapshot = async (snapshotId: string, snapshotName: string) => {
    if (!vmNameForSnapshot) return;
    const confirmed = window.confirm(
      t('workspace.snapshots.actions.restoreConfirm', {
        name: snapshotName || snapshotId,
      })
    );
    if (!confirmed) return;

    setSnapshotRestoringId(snapshotId);
    setSnapshotError(null);
    try {
      await restoreVmSnapshot({
        vmName: vmNameForSnapshot,
        snapshotId,
      });
      setSnapshotCurrentId(snapshotId);
      window.dispatchEvent(
        new CustomEvent('vm-snapshot-restored', {
          detail: { vmName: vmNameForSnapshot, snapshotId },
        })
      );
      await loadSnapshots();
    } catch (error: any) {
      setSnapshotError(toSnapshotErrorMessage(error, 'workspace.snapshots.errors.restoreFailed'));
    } finally {
      setSnapshotRestoringId(null);
    }
  };

  const activeBranchIds = collectSnapshotBranchIds(snapshots, snapshotCurrentId);

  useEffect(() => {
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<{ vmName?: string; snapshotId?: string }>;
      const restoredVmName = String(customEvent.detail?.vmName || '').trim();
      const restoredSnapshotId = String(customEvent.detail?.snapshotId || '').trim();
      if (!restoredVmName || !restoredSnapshotId) return;
      if (restoredVmName === vmNameForSnapshot) {
        setSnapshotCurrentId(restoredSnapshotId);
      }
    };
    window.addEventListener('vm-snapshot-restored', handler as EventListener);
    return () => {
      window.removeEventListener('vm-snapshot-restored', handler as EventListener);
    };
  }, [vmNameForSnapshot]);

  useEffect(() => {
    if (!snapshotCurrentId) return;
    const branchIds = collectSnapshotBranchIds(snapshots, snapshotCurrentId);
    if (!branchIds.size) {
      setSnapshotCurrentId(null);
    }
  }, [snapshotCurrentId, snapshots]);

  const renderSnapshotNodes = (nodes: VmSnapshotNode[], depth = 0): React.ReactNode =>
    nodes.map((node) => {
      const hasChildren = node.children.length > 0;
      const expanded = snapshotExpandedIds[node.id] ?? true;
      const isCurrent = snapshotCurrentId === node.id;
      const inActiveBranch = activeBranchIds.has(node.id);
      return (
        <div key={node.id}>
          <div
            className={`w-full h-[30px] px-2 flex items-center gap-1 ${isCurrent ? 'bg-blue-100/70' : inActiveBranch ? 'bg-blue-50/45' : ''}`}
            style={{ paddingLeft: `${8 + depth * 16}px` }}
          >
            <button
              type="button"
              onClick={() => hasChildren && toggleExpanded(node.id)}
              className="min-w-0 flex-1 h-full flex items-center gap-1.5 text-left text-[11px] text-black/70 hover:bg-black/5 transition-colors rounded-sm px-1"
              title={node.name}
            >
              {hasChildren ? (
                expanded ? <ChevronDown className="w-3 h-3 text-black/40" /> : <ChevronRight className="w-3 h-3 text-black/40" />
              ) : (
                <span className="w-3 h-3 inline-block" />
              )}
              <span className="truncate flex-1">{node.name}</span>
              <span className="text-[9px] text-black/30">
                {node.checkpointType.toLowerCase() === 'standard'
                  ? t('workspace.snapshots.node.state')
                  : t('workspace.snapshots.node.noState')}
              </span>
              {isCurrent ? (
                <span className="text-[9px] px-1 py-0.5 rounded-sm bg-blue-600/10 text-blue-700">
                  {t('workspace.snapshots.node.current')}
                </span>
              ) : null}
            </button>
            <button
              type="button"
              onClick={() => void handleRestoreSnapshot(node.id, node.name)}
              disabled={snapshotRestoringId === node.id}
              className="h-[22px] px-2 text-[10px] rounded-sm border border-black/10 text-black/60 hover:text-black/80 hover:bg-black/5 disabled:opacity-50"
              title={t('workspace.snapshots.actions.restore')}
            >
              {snapshotRestoringId === node.id
                ? t('workspace.snapshots.actions.restoring')
                : t('workspace.snapshots.actions.restore')}
            </button>
          </div>
          {hasChildren && expanded ? <div>{renderSnapshotNodes(node.children, depth + 1)}</div> : null}
        </div>
      );
    });

  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas flex flex-col py-2 pr-2 pl-4 relative">
      {/* Top Bar: Identity | Tabs | Activate */}
      <div className="flex items-center justify-between mb-3 flex-shrink-0 h-7">
        {/* Left: Identity */}
        <div className="flex items-center gap-2 mr-4">
          <Box className="w-4 h-4 text-black/60" />
          <h2 className="text-sm font-bold text-black/80 whitespace-nowrap">{target.name}</h2>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-sm tracking-wide ${isRunning ? 'text-emerald-600 bg-emerald-50' : 'text-neutral-500 bg-neutral-100'}`}>
            {isRunning ? 'Running' : vmState === 'unknown' ? 'Unknown' : 'Stopped'}
          </span>
        </div>

        {/* Center: Tabs */}
        <div className="flex items-center gap-1 bg-black/5 p-0.5 rounded-md mx-auto">
          <button
            onClick={() => setActiveTab('monitor')}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] font-bold transition-all
              ${activeTab === 'monitor' ? 'bg-white text-black shadow-sm' : 'text-black/50 hover:text-black/70 hover:bg-black/5'}
            `}
          >
            <ActivityIcon className="w-3 h-3" />
            <span>{t('workspace.snapshots.tabs.monitor')}</span>
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            disabled={isSettingsBlocked}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] font-bold transition-all
              ${activeTab === 'settings' ? 'bg-white text-black shadow-sm' : 'text-black/50 hover:text-black/70 hover:bg-black/5'}
              ${isSettingsBlocked ? 'opacity-40 cursor-not-allowed hover:bg-transparent hover:text-black/50' : ''}
            `}
            title={isUnknown ? 'Waiting for VM status…' : isLoading ? 'Loading…' : undefined}
          >
            <Settings className="w-3 h-3" />
            <span>{t('workspace.snapshots.tabs.settings')}</span>
          </button>
          <button
            onClick={() => setActiveTab('snapshots')}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] font-bold transition-all
              ${activeTab === 'snapshots' ? 'bg-white text-black shadow-sm' : 'text-black/50 hover:text-black/70 hover:bg-black/5'}
            `}
          >
            <Camera className="w-3 h-3" />
            <span>{t('workspace.snapshots.tabs.snapshots')}</span>
          </button>
        </div>

        {/* Right: Activate Button */}
        <div className="flex items-center gap-2 ml-4">
          {/* Activate Button */}
          <button
            onClick={onActivate}
            disabled={isActive || !target.available}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-colors
              ${isActive 
                ? 'bg-emerald-500/10 text-emerald-600 cursor-default' 
                : 'bg-black/5 text-black/60 hover:bg-black/10 hover:text-black/80'}
              ${!target.available ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            {isActive ? (
              <>
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span className="font-bold">Active</span>
              </>
            ) : (
              <span>Activate</span>
            )}
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-2">
        {/* Content Area */}
        <div className="flex-1 bg-neutral-50/50 border border-neutral-100 rounded-sm p-3 overflow-hidden relative">
           
           {/* Monitor Tab Content */}
           <div className={`
             absolute inset-0 p-3 flex flex-col transition-all duration-300
             ${activeTab === 'monitor' ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-4 pointer-events-none'}
           `}>
             <div className="flex items-start justify-between mb-4">
               <div className="flex flex-col gap-1">
                 {!isRunning && (vmSpecs?.status === 'ready' || vmSpecs?.status === 'loading') && (
                   <div className="flex items-center gap-1.5 text-orange-600/90 mb-1">
                     <AlertTriangle className="w-3 h-3" />
                     <span className="text-[10px] font-medium">Start VM to enable agent control</span>
                   </div>
                 )}
                 <p className="text-[11px] text-black/60 leading-relaxed pr-8">
                   Isolated virtual environment. Safe for testing and automation tasks. Changes can be reverted using snapshots.
                 </p>
               </div>
               
               {onRefresh && (
                 <button
                   onClick={onRefresh}
                   disabled={isLoading}
                   className="p-1.5 hover:bg-black/5 rounded text-black/40 hover:text-black/80 transition-colors"
                   title="Refresh Status"
                 >
                   <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                 </button>
               )}
             </div>

             <div className="mt-2">
                <ResourceInfoView vmSpecs={vmSpecs} isLoading={isLoading} />
             </div>
           </div>

           {/* Settings Tab Content */}
           <div className={`
             absolute inset-0 p-3 flex flex-col justify-center transition-all duration-300
             ${activeTab === 'settings' ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4 pointer-events-none'}
           `}>
            {isSettingsBlocked ? (
              <div className="h-full flex items-center justify-center">
                <div className="flex items-center gap-2 text-[11px] text-black/40">
                  <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                  <span>{isUnknown ? 'Waiting for VM status…' : 'Loading VM info…'}</span>
                </div>
              </div>
            ) : (
              vmSpecs && (
                <CompactSettingsView 
                  vmName={vmSpecs.name}
                  initialSpecs={{
                    cpuCores: vmSpecs.cpuCores,
                    memoryGB: vmSpecs.memoryGB,
                    isDynamicMemory: vmSpecs.isDynamicMemory
                  }}
                  isRunning={isRunning}
                  onSuccess={onRefresh}
                  onStopVm={handleStopVm}
                />
              )
            )}
           </div>

           {/* Snapshots Tab Content */}
           <div className={`
             absolute inset-0 p-3 flex flex-col transition-all duration-300
             ${activeTab === 'snapshots' ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4 pointer-events-none'}
           `}>
             <div className="flex items-center justify-between mb-2">
               <span className="text-[10px] font-bold uppercase tracking-wider text-black/45">{t('workspace.snapshots.title')}</span>
               <button
                 type="button"
                 className="p-1 rounded text-black/45 hover:bg-black/5 hover:text-black/75 transition-colors"
                 title={t('workspace.snapshots.actions.refresh')}
                 onClick={() => void loadSnapshots()}
                 disabled={snapshotLoading}
               >
                 <RefreshCw className={`w-3.5 h-3.5 ${snapshotLoading ? 'animate-spin' : ''}`} />
               </button>
             </div>

             <div className="flex items-center gap-2 mb-2">
               <input
                 value={snapshotDraftName}
                 onChange={(e) => setSnapshotDraftName(e.target.value)}
                 placeholder={t('workspace.snapshots.placeholder')}
                 className="flex-1 h-[30px] px-2 text-[11px] rounded-sm border border-black/10 bg-white outline-none focus:border-black/25"
               />
               <select
                 value={snapshotMode}
                 onChange={(e) => setSnapshotMode(e.target.value as 'save' | 'no_save')}
                 className="h-[30px] px-2 text-[11px] rounded-sm border border-black/10 bg-white text-black/70"
               >
                 <option value="save">{t('workspace.snapshots.mode.saveState')}</option>
                 <option value="no_save">{t('workspace.snapshots.mode.noSaveState')}</option>
               </select>
               <button
                 type="button"
                 onClick={() => void handleCreateSnapshot()}
                 disabled={snapshotCreating}
                 className="h-[30px] px-3 inline-flex items-center gap-1.5 text-[11px] rounded-sm bg-black text-white hover:bg-black/85 disabled:opacity-50"
               >
                 <Camera className="w-3.5 h-3.5" />
                 <span>{t('workspace.snapshots.actions.create')}</span>
               </button>
             </div>

             {snapshotError ? (
               <div className="mb-2 text-[11px] text-red-600 truncate" title={snapshotError}>
                 {snapshotError}
               </div>
             ) : null}

             <div className="flex-1 min-h-0 overflow-y-auto border border-black/5 bg-white/70 rounded-sm">
               {snapshots.length > 0 ? (
                 <div className="py-1">
                   {renderSnapshotNodes(snapshots)}
                 </div>
               ) : (
                 <div className="h-full flex items-center justify-center text-xs text-black/35">
                   {snapshotLoading ? t('workspace.snapshots.loading') : t('workspace.snapshots.empty')}
                 </div>
               )}
             </div>
           </div>
           
           {/* Shutdown Modal - Removed locally, now handled by ScreenViewer via event bus */}
           
        </div>
      </div>
    </div>
  );
}

// 拆分出来的资源显示组件
function ResourceInfoView({ vmSpecs, isLoading }: { vmSpecs?: VmSpecsState; isLoading: boolean }) {
  return (
    <div className={`grid grid-cols-3 gap-4 transition-opacity duration-200 ${isLoading ? 'opacity-60' : 'opacity-100'}`}>
      {/* CPU */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between h-[18px]">
          <div className="flex items-center gap-1.5 text-black/50">
            <Cpu className="w-3.5 h-3.5" />
            <span className="text-[10px] font-bold uppercase tracking-wider">vCPU</span>
          </div>
          <div className="text-[11px] font-mono font-bold text-black/80 leading-none flex items-center gap-1.5">
            <span className={`${vmSpecs?.cpuUsage ? 'text-black/80' : 'text-black/40'}`}>
              {vmSpecs?.cpuUsage || 0}%
            </span>
            <div className="w-px h-2.5 bg-black/10"></div>
            <span className="text-black/60">
              {vmSpecs?.cpuCores || '-'} <span className="text-[9px] text-black/40 font-normal ml-0.5">Cores</span>
            </span>
          </div>
        </div>
        <div className="w-full bg-black/5 h-1.5 rounded-full overflow-hidden">
           <div 
            className="bg-blue-500/60 h-full rounded-full transition-all duration-500" 
            style={{ width: `${Math.min(vmSpecs?.cpuUsage || 0, 100)}%` }}
          />
        </div>
      </div>

      {/* Memory */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between h-[18px]">
          <div className="flex items-center gap-1.5 text-black/50">
            <MemoryStick className="w-3.5 h-3.5" />
            <span className="text-[10px] font-bold uppercase tracking-wider">Memory</span>
          </div>
          <div className="text-[11px] font-mono font-bold text-black/80 leading-none flex items-center gap-1.5">
            <span className="text-black/80">
              {vmSpecs?.memoryDemandGB || 0} GB
            </span>
            <div className="w-px h-2.5 bg-black/10"></div>
            <span className="text-black/60">
              {vmSpecs?.memoryGB || '-'} <span className="text-[9px] text-black/40 font-normal ml-0.5">GB</span>
            </span>
          </div>
        </div>
        <div className="w-full bg-black/5 h-1.5 rounded-full overflow-hidden">
          <div 
            className="bg-purple-500/60 h-full rounded-full transition-all duration-500" 
            style={{ 
              width: `${vmSpecs?.memoryGB ? Math.min(((vmSpecs.memoryDemandGB || 0) / vmSpecs.memoryGB) * 100, 100) : 0}%`,
              opacity: 1
            }}
          />
        </div>
      </div>

      {/* Storage */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-end justify-between h-[18px]">
          <div className="flex items-center gap-1.5 text-black/50">
            <HardDrive className="w-3.5 h-3.5" />
            <span className="text-[10px] font-bold uppercase tracking-wider">Storage</span>
          </div>
          <div className="text-[11px] font-mono font-bold text-black/80 leading-none">
            <span className="text-black/60">{vmSpecs?.storageUsedGB || 0}</span>
            <span className="text-[9px] text-black/30 font-normal mx-1">/</span>
            {vmSpecs?.storageGB || '-'} 
            <span className="text-[9px] text-black/40 font-normal ml-1">GB</span>
          </div>
        </div>
        <div className="w-full bg-black/5 h-1.5 rounded-full overflow-hidden">
          <div 
            className="bg-emerald-500/60 h-full rounded-full transition-all duration-500" 
            style={{ width: `${vmSpecs?.storageGB ? Math.min(((vmSpecs.storageUsedGB || 0) / vmSpecs.storageGB) * 100, 100) : 0}%` }}
          />
        </div>
      </div>
    </div>
  );
}

// 紧凑型设置视图
function CompactSettingsView({ 
  vmName,
  initialSpecs, 
  isRunning, 
  onSuccess,
  onStopVm
}: { 
  vmName: string;
  initialSpecs: { cpuCores: number; memoryGB: number; isDynamicMemory: boolean };
  isRunning: boolean;
  onSuccess?: () => void;
  onStopVm?: () => void;
}) {
  const [specs, setSpecs] = useState(initialSpecs);
  const [isSaving, setIsSaving] = useState(false);
  // 检查是否有变更
  const hasChanges = 
    specs.cpuCores !== initialSpecs.cpuCores || 
    specs.memoryGB !== initialSpecs.memoryGB ||
    specs.isDynamicMemory !== initialSpecs.isDynamicMemory;

  const handleSave = async () => {
    if (!hasChanges || isRunning) return;
    
    setIsSaving(true);
    try {
      await setVmSpecs({ vmName, ...specs });
      onSuccess?.();
    } catch (err) {
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={`flex flex-col gap-2 ${isRunning ? 'opacity-50 pointer-events-none' : ''}`}>
       {/* 紧凑的一行布局：CPU | Memory | Dynamic Checkbox | Save Button */}
       <div className="flex items-center gap-6 h-full">
         
         {/* CPU */}
         <div className="flex flex-col gap-1.5 flex-1">
            <div className="flex items-center justify-between">
               <span className="text-[10px] font-bold text-black/60 uppercase tracking-wide">vCPU</span>
               <span className="text-[11px] font-mono font-bold text-black/80">{specs.cpuCores} <span className="text-[9px] text-black/40 font-normal">Cores</span></span>
            </div>
            <input 
              type="range" min="1" max="8" step="1"
              value={specs.cpuCores}
              onChange={(e) => setSpecs({ ...specs, cpuCores: parseInt(e.target.value) })}
              className="w-full h-1.5 bg-black/10 rounded-full appearance-none cursor-pointer accent-black"
            />
         </div>

         {/* Memory */}
         <div className="flex flex-col gap-1.5 flex-1">
            <div className="flex items-center justify-between">
               <span className="text-[10px] font-bold text-black/60 uppercase tracking-wide">Memory</span>
               <span className="text-[11px] font-mono font-bold text-black/80">{specs.memoryGB} <span className="text-[9px] text-black/40 font-normal">GB</span></span>
            </div>
            <input 
              type="range" min="2" max="16" step="1"
              value={specs.memoryGB}
              onChange={(e) => setSpecs({ ...specs, memoryGB: parseInt(e.target.value) })}
              className="w-full h-1.5 bg-black/10 rounded-full appearance-none cursor-pointer accent-black"
            />
         </div>

         {/* Dynamic Toggle & Save Action */}
         <div className="flex items-end gap-4 h-full pb-0.5">
            <div className="flex items-center gap-2 mb-1">
              <input 
                type="checkbox"
                id="compact-dynamic-mem"
                checked={specs.isDynamicMemory}
                onChange={(e) => setSpecs({ ...specs, isDynamicMemory: e.target.checked })}
                className="rounded-sm border-black/20 text-black focus:ring-black/20 w-3.5 h-3.5"
              />
              <label htmlFor="compact-dynamic-mem" className="text-[10px] text-black/70 font-medium cursor-pointer whitespace-nowrap">
                Dynamic Memory
              </label>
            </div>

            <button
              onClick={handleSave}
              disabled={!hasChanges || isSaving || isRunning}
              className={`
                flex items-center gap-1.5 px-3 py-1 rounded text-[10px] font-bold transition-all
                ${hasChanges && !isRunning
                  ? 'bg-black text-white hover:bg-black/80 shadow-sm translate-y-0 opacity-100' 
                  : 'bg-transparent text-transparent translate-y-2 opacity-0 pointer-events-none'}
              `}
            >
              {isSaving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              <span>Save</span>
            </button>
         </div>

       </div>
       
       {isRunning && (
         <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/50 backdrop-blur-[1px] rounded-sm pointer-events-auto">
            <button 
              onClick={(e) => {
                e.stopPropagation();
                onStopVm?.();
              }}
              className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 text-amber-700 rounded-full border border-amber-100/50 shadow-sm hover:bg-amber-100 cursor-pointer transition-colors group"
            >
               <Lock className="w-3 h-3 group-hover:text-amber-800" />
               <span className="text-[10px] font-medium group-hover:text-amber-900">Stop VM to configure</span>
            </button>
         </div>
       )}
    </div>
  );
}

