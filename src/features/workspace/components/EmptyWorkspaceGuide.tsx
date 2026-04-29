import React, { useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { 
  Monitor, 
  ArrowRight, 
  ArrowLeft,
  Globe, 
  Mail, 
  Terminal, 
  Plus,
  Box,
  Download,
  Sparkles,
  MousePointer2,
  Play,
  Loader2,
  GitBranch,
  Wand2,
  BadgeCheck,
  FileText,
  Table,
  MessageCircle,
  Zap,
  Smartphone,
  ExternalLink,
  Clock,
  Package,
  Wrench,
  X,
  CheckCircle,
  FolderDown,
  Tag,
  MessageSquare,
  GitFork,
  BarChart3,
} from 'lucide-react';
import { usePublicWorkflows, useCreateWorkflow } from '@/features/workflow';
import type { PublicWorkflowListItem, WorkflowListItem, BundledAsset } from '@/features/workflow';
import { workflowApi } from '@/features/workflow/api';
import { LOCAL_OFFLINE_USER_ID } from '@/services/localOfflineStore';
import { InfoDialog } from '@/components/InfoDialog';
import { CATEGORIES } from '@/features/workflow/components/WorkflowEditor/components/publishConstants';
import { parseQuickStartMessage } from '@/features/workflow/utils/quickStartParser';
import { getFileIcon } from '@/features/workspace/file-explorer/utils/fileIcon';
import { REMOTE_CONTROL_ENABLED } from '@/config/runtimeEnv';
import { useProject } from '@/contexts/ProjectContext';

interface EmptyWorkspaceGuideProps {
  onSetEnvironment: () => void;
  onSelectLocal?: () => void;
  onCreateVm?: () => void;
  onCreateWorkflow: (templateName?: string) => void;
  onForkWorkflow?: (workflowId: string) => void;
  onSelectAgent?: (agentId: string) => void;
  onCollapse?: () => void;
  projectId?: string;
  currentEnvName?: string;
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

// Icon name (from DB) -> lucide component mapping
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  MousePointer2,
  Globe,
  Mail,
  Terminal,
  Table,
  FileText,
  MessageCircle,
  Sparkles,
  Zap,
  Smartphone,
  GitBranch,
  Wand2,
  BadgeCheck,
  Box,
  Download,
  Monitor,
  Play,
  ExternalLink,
};

export function resolveIcon(iconName: string | null | undefined): React.ComponentType<{ className?: string }> {
  if (iconName && ICON_MAP[iconName]) return ICON_MAP[iconName];
  return Sparkles;
}

export function AgentCard({ 
  workflow, 
  onClick,
  loading = false
}: { 
  workflow: PublicWorkflowListItem;
  onClick: () => void;
  loading?: boolean;
}) {
  const Icon = resolveIcon(workflow.icon);
  const displayName = workflow.name;
  const assetCount = (workflow.bundled_skills?.length ?? 0) + (workflow.example_files?.length ?? 0);

  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="group relative flex flex-col items-start p-5 bg-white border border-black/[0.08] hover:border-black/20 transition-all text-left overflow-hidden hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {/* Decorative corner line */}
      <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
        <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-black/10 to-transparent" />
        <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-black/10 to-transparent" />
      </div>
      
      {/* Icon */}
      <div className="w-10 h-10 bg-black/5 text-black/70 flex items-center justify-center transition-colors group-hover:bg-black group-hover:text-white">
        {loading ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : (
          <Icon className="w-5 h-5" />
        )}
      </div>
      
      {/* Content */}
      <div className="mt-4 space-y-1.5 flex-1 pr-6">
        <h3 className="font-bold text-[15px] text-black/90 group-hover:text-black leading-tight">
          {displayName}
        </h3>
        <p className="text-xs text-black/50 leading-relaxed line-clamp-2">
          {workflow.description || 'Official agent template'}
        </p>
      </div>
      
      {/* Footer info */}
      <div className="mt-4 flex items-center gap-3">
        <span className="flex items-center gap-1 text-[10px] text-black/40 font-medium">
          <Play className="w-3 h-3" />
          View Details
        </span>
        {assetCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-black/30 font-medium">
            <Package className="w-3 h-3" />
            {assetCount} files
          </span>
        )}
      </div>
      
      {/* Hover indicator bar */}
      <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
    </button>
  );
}

export function CustomizeCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-orange-50/60 via-amber-50/30 to-stone-50 border border-orange-200/40 hover:border-orange-300/60 transition-all text-left overflow-hidden hover:shadow-[0_8px_30px_-8px_rgba(194,114,63,0.2)]"
    >
      {/* Subtle radial glow */}
      <div 
        className="absolute -top-20 -right-20 w-40 h-40 opacity-30 group-hover:opacity-50 transition-opacity pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(234,162,107,0.4) 0%, transparent 70%)'
        }}
      />
      
      {/* Grid pattern overlay - softer orange */}
      <div 
        className="absolute inset-0 opacity-[0.12] group-hover:opacity-[0.18] transition-opacity pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(to right, rgb(194 114 63 / 0.35) 1px, transparent 1px), linear-gradient(to bottom, rgb(194 114 63 / 0.35) 1px, transparent 1px)',
          backgroundSize: '20px 20px'
        }}
      />
      
      {/* Decorative corner accent */}
      <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
        <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-orange-300/50 to-transparent" />
        <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-orange-300/50 to-transparent" />
      </div>
      
      {/* Icon */}
      <div className="w-10 h-10 bg-gradient-to-br from-orange-400/90 to-amber-600/90 text-white flex items-center justify-center transition-all group-hover:from-orange-500 group-hover:to-amber-700 group-hover:shadow-md relative z-10">
        <Wand2 className="w-5 h-5" />
      </div>
      
      {/* Content */}
      <div className="mt-4 space-y-1.5 flex-1 relative z-10">
        <h3 className="font-bold text-[15px] text-stone-800 group-hover:text-stone-900 leading-tight">
          Customize Your Own
        </h3>
        <p className="text-xs text-stone-500 leading-relaxed">
          Create a custom workflow tailored to your specific needs
        </p>
      </div>
      
      {/* Footer - matching AgentCard button style */}
      <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-orange-600/60 font-semibold uppercase tracking-wider group-hover:text-orange-700/80 transition-colors relative z-10">
        <Plus className="w-3 h-3" />
        <span>Create New</span>
      </div>
      
      {/* Hover indicator bar */}
      <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-orange-400/80 to-amber-500/80 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
    </button>
  );
}

// Step 指示器
function StepIndicator({ step, currentStep, title }: { step: number; currentStep: number; title: string }) {
  const isActive = step === currentStep;
  const isCompleted = step < currentStep;
  
  return (
    <div className="flex items-center gap-3">
      <div className={`
        w-8 h-8 flex items-center justify-center text-xs font-bold transition-all relative
        ${isActive ? 'bg-black text-white' : isCompleted ? 'bg-black text-white' : 'bg-black/[0.06] text-black/40'}
      `}>
        {isCompleted ? (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="square" strokeLinejoin="miter" d="M5 13l4 4L19 7" />
          </svg>
        ) : (
          step
        )}
      </div>
      <span className={`text-sm font-semibold transition-colors ${isActive ? 'text-black' : 'text-black/40'}`}>
        {title}
      </span>
    </div>
  );
}

export function AgentDetailDialog({
  open,
  onClose,
  workflow,
  onFork,
  onNavigate,
  onSelectAgent,
  onCollapse,
  onLoadQuickStart,
  projectId,
  onEnsureProject,
}: {
  open: boolean;
  onClose: () => void;
  workflow: PublicWorkflowListItem;
  onFork: (workflowId: string) => Promise<string>;
  onNavigate: (workflowId: string, quickStartMessage?: string) => void;
  onSelectAgent?: (agentId: string) => void;
  onCollapse?: () => void;
  onLoadQuickStart?: (workflowId: string) => void;
  projectId?: string;
  onEnsureProject?: () => Promise<string | null>;
}) {
  const [actionType, setActionType] = useState<'fork' | 'run' | null>(null);
  const [downloadPhase, setDownloadPhase] = useState<'skill' | 'example' | null>(null);
  const [downloadFile, setDownloadFile] = useState('');
  const [downloadIndex, setDownloadIndex] = useState(0);
  const [downloadTotal, setDownloadTotal] = useState(0);
  const [error, setError] = useState('');
  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const [duplicateWorkflow, setDuplicateWorkflow] = useState<WorkflowListItem | null>(null);
  const [pendingAction, setPendingAction] = useState<'fork' | 'run' | null>(null);
  const [downloadDone, setDownloadDone] = useState<{ skillsRoot?: string; projectRoot?: string } | null>(null);
  const [pendingClose, setPendingClose] = useState<{ id: string; action: 'fork' | 'run' } | null>(null);

  const electron = (window as any).electron;
  const skills = workflow.bundled_skills ?? [];
  const examples = workflow.example_files ?? [];
  const quickStartMessages = workflow.quick_start_messages ?? [];
  const hasAssets = skills.length > 0 || examples.length > 0;
  const categoryLabel = CATEGORIES.find(c => c.value === workflow.category)?.label;
  const Icon = resolveIcon(workflow.icon);
  const busy = actionType !== null;

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const checkDuplicate = useCallback(async (): Promise<WorkflowListItem | null> => {
    try {
      const myWorkflows = await workflowApi.list();
      return myWorkflows.find(w => w.name === workflow.name) ?? null;
    } catch {
      return null;
    }
  }, [workflow.name]);

  const downloadAssets = useCallback(async (
    assets: BundledAsset[],
    type: 'skill' | 'example',
    explicitProjectId?: string,
  ): Promise<string> => {
    if (!electron || assets.length === 0) return '';

    setDownloadPhase(type);
    setDownloadTotal(assets.length);

    let targetRoot: string;
    if (type === 'skill') {
      targetRoot = await electron.fsGetSkillsRoot(LOCAL_OFFLINE_USER_ID);
    } else {
      targetRoot = await electron.fsGetProjectRoot(explicitProjectId ?? projectId);
    }

    const normalize = (p: string) => p.replace(/\\/g, '/').replace(/\/$/, '');
    const root = normalize(targetRoot);
    const newCompleted = new Set(completed);
    const assetBase = (import.meta.env.VITE_COMMUNITY_ASSETS_PUBLIC_BASE as string | undefined)?.replace(/\/$/, '');

    for (let i = 0; i < assets.length; i++) {
      const asset = assets[i];
      setDownloadIndex(i + 1);
      setDownloadFile(asset.relative_path);

      if (!assetBase) {
        console.warn(
          '[EmptyWorkspaceGuide] 跳过模板资源下载：未配置 VITE_COMMUNITY_ASSETS_PUBLIC_BASE（离线发行版无默认云端）',
        );
        continue;
      }

      const downloadUrl = `${assetBase}/${asset.s3_key.split('/').map(encodeURIComponent).join('/')}`;

      const targetPath = `${root}/${asset.relative_path}`;

      const result = await electron.downloadPresignedGet({
        requestId: `dl-${Date.now()}-${i}`,
        filePath: targetPath,
        downloadUrl,
      });

      if (!result.success) {
        throw new Error(`Failed to download ${asset.filename}: ${result.error}`);
      }
      newCompleted.add(asset.s3_key);
      setCompleted(new Set(newCompleted));
    }

    return root;
  }, [electron, projectId, completed]);

  const doDownloadAssets = useCallback(async (explicitProjectId?: string) => {
    if (!hasAssets) return null;
    const paths: { skillsRoot?: string; projectRoot?: string } = {};
    if (skills.length > 0) paths.skillsRoot = await downloadAssets(skills, 'skill', explicitProjectId);
    if (examples.length > 0) paths.projectRoot = await downloadAssets(examples, 'example', explicitProjectId);
    return paths;
  }, [hasAssets, skills, examples, downloadAssets]);

  // 确认执行：底部 "Run"/"Done" 按钮专用，会触发导航
  const handleClose = useCallback(() => {
    if (pendingClose) {
      const quickStartMessage = pendingClose.action === 'run'
        ? (workflow.quick_start_messages?.[0] ?? undefined)
        : undefined;
      onNavigate(pendingClose.id, quickStartMessage);
      if (pendingClose.action === 'run') {
        onSelectAgent?.(`workflow:${pendingClose.id}`);
        onLoadQuickStart?.(pendingClose.id);
        onCollapse?.();
      }
      setPendingClose(null);
    }
    setDownloadDone(null);
    setCompleted(new Set());
    onClose();
  }, [pendingClose, workflow.quick_start_messages, onNavigate, onSelectAgent, onCollapse, onLoadQuickStart, onClose]);

  // 纯关闭：X 按钮 / 背景遮罩专用，不触发导航
  const handleDismiss = useCallback(() => {
    setPendingClose(null);
    setDownloadDone(null);
    setCompleted(new Set());
    setDuplicateWorkflow(null);
    setPendingAction(null);
    onClose();
  }, [onClose]);

  const executeFork = useCallback(async (action: 'fork' | 'run') => {
    setActionType(action);
    setDuplicateWorkflow(null);
    setPendingAction(null);
    setDownloadDone(null);
    setPendingClose(null);

    try {
      const forkedId = await onFork(workflow.id);

      let resolvedProjectId = projectId;
      if (!resolvedProjectId && onEnsureProject) {
        const ensured = await onEnsureProject();
        resolvedProjectId = ensured ?? undefined;
      }

      const paths = await doDownloadAssets(resolvedProjectId);
      if (paths) setDownloadDone(paths);

      setPendingClose({ id: forkedId, action });
    } catch (err: any) {
      setError(err.message || 'Failed to fork workflow');
    } finally {
      setActionType(null);
      setDownloadPhase(null);
      setDownloadFile('');
    }
  }, [workflow.id, onFork, doDownloadAssets, projectId, onEnsureProject]);

  const useExisting = useCallback(async (existingId: string) => {
    setDuplicateWorkflow(null);
    const action = pendingAction;
    setPendingAction(null);
    setActionType(action);
    setDownloadDone(null);
    setPendingClose(null);

    try {
      let resolvedProjectId = projectId;
      if (!resolvedProjectId && onEnsureProject) {
        const ensured = await onEnsureProject();
        resolvedProjectId = ensured ?? undefined;
      }

      const paths = await doDownloadAssets(resolvedProjectId);
      if (paths) setDownloadDone(paths);

      setPendingClose({ id: existingId, action: action || 'fork' });
    } catch (err: any) {
      setError(err.message || 'Download failed');
    } finally {
      setActionType(null);
      setDownloadPhase(null);
      setDownloadFile('');
    }
  }, [pendingAction, doDownloadAssets, projectId, onEnsureProject]);

  const handleAction = useCallback(async (action: 'fork' | 'run') => {
    if (busy) return;
    setError('');

    const existing = await checkDuplicate();
    if (existing) {
      setDuplicateWorkflow(existing);
      setPendingAction(action);
      return;
    }

    await executeFork(action);
  }, [busy, checkDuplicate, executeFork]);

  if (!open) return null;

  const isRunning = actionType === 'run';
  const isForking = actionType === 'fork';

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40" onClick={handleDismiss} />
      <div className="relative bg-white shadow-xl border border-gray-200 rounded-xl w-full max-w-lg mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-black/5 text-black/70 flex items-center justify-center flex-shrink-0">
              <Icon className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 truncate">{workflow.name}</h2>
          </div>
          <button onClick={handleDismiss} className="text-gray-400 hover:text-gray-600 flex-shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* About — description + quick start */}
          <section className="space-y-3">
            {workflow.description && (
              <p className="text-sm text-gray-600 leading-relaxed">{workflow.description}</p>
            )}
            {quickStartMessages.length > 0 && (
              <div className="space-y-1.5">
                {quickStartMessages.map((msg, index) => {
                  const hasFileRefs = msg.includes('@');
                  return (
                    <div key={index} className="px-3 py-2 bg-gray-50 rounded-md">
                      <div className="text-xs text-gray-600 leading-relaxed flex flex-wrap items-center gap-0.5">
                        {hasFileRefs ? (
                          parseQuickStartMessage(msg).map((seg, si) =>
                            seg.type === 'text' ? (
                              <span key={si}>{seg.value}</span>
                            ) : (
                              <span key={si} className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-orange-50 border border-orange-200/60 rounded text-[11px] text-orange-800 font-medium">
                                {getFileIcon(seg.name, false, 13)}
                                {seg.name}
                              </span>
                            )
                          )
                        ) : (
                          <span>{msg}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {workflow.tags && workflow.tags.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap">
                {workflow.tags.map(tag => (
                  <span key={tag} className="text-[11px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* Example Files */}
          {(examples.length > 0 || skills.length > 0) && (
            <section className="space-y-2">
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
                <FolderDown className="w-3.5 h-3.5" />
                Files included
              </h4>
              <div className="border border-gray-200 rounded-md divide-y divide-gray-100">
                {[...skills, ...examples].map(asset => {
                  const isDone = completed.has(asset.s3_key);
                  const isActive = downloadFile === asset.relative_path && !isDone;
                  return (
                    <div key={asset.s3_key} className={`flex items-center justify-between px-3 py-2 transition-colors ${isActive ? 'bg-blue-50' : ''}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        {isDone ? (
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                        ) : isActive ? (
                          <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin flex-shrink-0" />
                        ) : (
                          <span className="flex-shrink-0">{getFileIcon(asset.filename, false, 14)}</span>
                        )}
                        <span className={`text-xs truncate ${isDone ? 'text-emerald-700' : isActive ? 'text-blue-700 font-medium' : 'text-gray-700'}`}>{asset.relative_path}</span>
                      </div>
                      {asset.size_bytes > 0 && <span className="text-[10px] text-gray-400 flex-shrink-0 ml-2">{formatSize(asset.size_bytes)}</span>}
                    </div>
                  );
                })}
              </div>
              <p className="text-[11px] text-gray-400 flex items-center gap-1">
                {downloadDone ? (
                  <><CheckCircle className="w-3 h-3 text-emerald-500" /> Downloaded successfully.{pendingClose?.action === 'run' && ' Click "Close & Run" to start.'}</>
                ) : downloadPhase ? (
                  <><Loader2 className="w-3 h-3 text-blue-500 animate-spin" /> Downloading {downloadIndex}/{downloadTotal}…</>
                ) : (
                  <>These files will be downloaded when you run the agent.</>
                )}
              </p>
            </section>
          )}

          {/* Duplicate notice */}
          {duplicateWorkflow && (
            <div className="text-xs text-gray-600 bg-gray-50 rounded-md px-3 py-2.5">
              You already have <span className="font-semibold">"{duplicateWorkflow.name}"</span>. You can use the existing one or fork a new copy.
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-xs text-red-600 bg-red-50 rounded-md px-3 py-2">{error}</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100">
          {pendingClose ? (
            <>
              <button
                onClick={() => { setPendingClose(null); setDownloadDone(null); setCompleted(new Set()); onClose(); }}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
              >
                Close
              </button>
              <button
                onClick={() => { setDuplicateWorkflow(null); setPendingAction(null); handleClose(); }}
                className="flex items-center gap-1.5 px-5 py-2 text-sm font-medium text-white bg-gray-900 hover:bg-gray-800 transition-colors"
              >
                {pendingClose.action === 'run' && <Play className="w-4 h-4" />}
                {pendingClose.action === 'run' ? 'Run' : 'Done'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleDismiss}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
              >
                Close
              </button>
          {!downloadDone && (
            duplicateWorkflow ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => pendingAction && executeFork(pendingAction)}
                  disabled={busy}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {pendingAction === 'run' ? <Play className="w-4 h-4" /> : <GitFork className="w-4 h-4" />}
                  {pendingAction === 'run' ? 'Run New Copy' : 'Fork Anyway'}
                </button>
                <button
                  onClick={() => useExisting(duplicateWorkflow.id)}
                  className="flex items-center gap-1.5 px-5 py-2 text-sm font-medium text-white bg-gray-900 hover:bg-gray-800 transition-colors"
                >
                  {pendingAction === 'run' ? <Play className="w-4 h-4" /> : <GitFork className="w-4 h-4" />}
                  Use Existing
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleAction('fork')}
                  disabled={busy}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isForking ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitFork className="w-4 h-4" />}
                  Fork
                </button>
                <button
                  onClick={() => handleAction('run')}
                  disabled={busy}
                  className="flex items-center gap-1.5 px-5 py-2 text-sm font-medium text-white bg-gray-900 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  Run Agent
                </button>
              </div>
            )
          )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function EmptyWorkspaceGuide({ 
  onSetEnvironment, 
  onSelectLocal,
  onCreateVm,
  onCreateWorkflow,
  onForkWorkflow,
  onSelectAgent,
  onCollapse,
  projectId,
  currentEnvName = 'Local Machine (This PC)'
}: EmptyWorkspaceGuideProps) {
  const [page, setPage] = useState<'agents' | 'customize'>('agents');
  const [customizeStep, setCustomizeStep] = useState(1);
  const [forkingId, setForkingId] = useState<string | null>(null);
  const [showLocalRunDialog, setShowLocalRunDialog] = useState(false);
  const [isCreatingWorkflow, setIsCreatingWorkflow] = useState(false);
  const [detailWorkflow, setDetailWorkflow] = useState<PublicWorkflowListItem | null>(null);

  const { currentProject, recentProjects, openProject, createProject } = useProject();

  const handleEnsureProject = useCallback(async (): Promise<string | null> => {
    if (currentProject) return currentProject.id;
    const localProject = recentProjects
      .filter(p => p.exists !== false && !p.isCloudOnly)
      .sort((a, b) => (b.created_at ?? b.lastModified) - (a.created_at ?? a.lastModified))[0];
    if (localProject) {
      const opened = await openProject(localProject.id);
      return opened?.id ?? null;
    }
    const existingNames = new Set(recentProjects.map(p => p.name));
    let n = 1;
    while (existingNames.has(`New Project ${n}`)) n++;
    const created = await createProject(`New Project ${n}`);
    return created?.id ?? null;
  }, [currentProject, recentProjects, openProject, createProject]);

  // 获取公开的官方 workflows
  const { workflows: publicWorkflows, loading: loadingWorkflows, fork, forking } = usePublicWorkflows();
  
  // 创建新 workflow
  const { create: createWorkflow, creating: creatingWorkflow } = useCreateWorkflow();

  // Remote 控制的 URL
  const REMOTE_CONTROL_URL = 'https://app.useit.studio/remote';

  // 创建新 workflow 并打开
  const handleCreateNewWorkflow = async () => {
    if (isCreatingWorkflow) return;
    setIsCreatingWorkflow(true);
    try {
      // 生成带时间戳的默认名称
      const now = new Date();
      const timestamp = now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).replace(/\//g, '-');
      const defaultName = `New Workflow ${timestamp}`;
      
      // 创建 workflow
      const newWorkflow = await createWorkflow({ name: defaultName });
      
      // 打开新创建的 workflow（使用 onForkWorkflow，它会打开指定 workflowId 的 tab）
      if (onForkWorkflow) {
        onForkWorkflow(newWorkflow.id);
      } else {
        // Fallback
        onCreateWorkflow(newWorkflow.name);
      }
      
      // 更新步骤
      setCustomizeStep(2);
    } catch (error) {
      console.error('Failed to create workflow:', error);
    } finally {
      setIsCreatingWorkflow(false);
    }
  };
  
  // API now returns only featured+published workflows, no client-side filtering needed
  const officialWorkflows = publicWorkflows;

  // handlers
  const handleSelectLocal = () => {
    if (onSelectLocal) onSelectLocal();
    else onSetEnvironment();
    if (page === 'customize') {
      setCustomizeStep(2);
    }
  };

  const handleCreateVm = () => {
    if (onCreateVm) onCreateVm();
    else onSetEnvironment();
    if (page === 'customize') {
      setCustomizeStep(2);
    }
  };

  const handleForkOnly = async (workflowId: string): Promise<string> => {
    setForkingId(workflowId);
    try {
      const forkedWorkflow = await fork(workflowId);
      return forkedWorkflow.id;
    } catch (error) {
      console.error('Failed to fork workflow:', error);
      throw error;
    } finally {
      setForkingId(null);
    }
  };

  const handleNavigateToWorkflow = (workflowId: string) => {
    if (onForkWorkflow) {
      onForkWorkflow(workflowId);
    } else {
      onCreateWorkflow(workflowId);
    }
  };

  const handleBackToAgents = () => {
    setPage('agents');
    setCustomizeStep(1);
  };

  // Page 1: Agent Gallery
  if (page === 'agents') {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-[#FAFAFA] overflow-y-auto font-sans selection:bg-black/5">
        {/* Subtle background pattern */}
        <div 
          className="absolute inset-0 opacity-[0.4] pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
            backgroundSize: '24px 24px'
          }}
        />
        
        <div className="w-full max-w-[960px] px-8 py-12 flex flex-col gap-8 animate-in fade-in zoom-in-95 duration-500 relative z-10">
          
          {/* Header */}
          <div className="space-y-2">
            <h1 className="text-2xl font-black text-black tracking-tight">Quick Start</h1>
            <p className="text-sm text-black/50 font-medium max-w-md">
              Choose an agent to get started instantly, or create your own custom workflow from scratch.
            </p>
          </div>

          {/* Divider */}
          <div className="h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" />

          {/* Loading State */}
          {loadingWorkflows ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
            </div>
          ) : (
            /* All Agents Grid - Official + Customize in one grid */
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {officialWorkflows.slice(0, 6).map((workflow) => (
                <AgentCard
                  key={workflow.id}
                  workflow={workflow}
                  onClick={() => setDetailWorkflow(workflow)}
                  loading={forkingId === workflow.id}
                />
              ))}
              <CustomizeCard onClick={() => setPage('customize')} />
            </div>
          )}
          
          {/* Footer hint */}
          <div className="flex items-center justify-center gap-2 text-[11px] text-black/30 font-medium">
            <span>Click any agent to fork and customize</span>
            <span className="w-1 h-1 rounded-full bg-black/20" />
            <span>Your workflows are saved automatically</span>
          </div>
        </div>

        {detailWorkflow && (
          <AgentDetailDialog
            open={!!detailWorkflow}
            onClose={() => setDetailWorkflow(null)}
            workflow={detailWorkflow}
            onFork={handleForkOnly}
            onNavigate={handleNavigateToWorkflow}
            onSelectAgent={onSelectAgent}
            onCollapse={onCollapse}
            projectId={projectId}
            onEnsureProject={handleEnsureProject}
          />
        )}
      </div>
    );
  }

  // Page 2: Customize Steps
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#FAFAFA] overflow-y-auto font-sans selection:bg-black/5">
      {/* Subtle background pattern */}
      <div 
        className="absolute inset-0 opacity-[0.4] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
          backgroundSize: '24px 24px'
        }}
      />
      
      <div className="w-full max-w-[960px] px-8 py-12 flex flex-col gap-8 animate-in fade-in zoom-in-95 duration-500 relative z-10">
        
        {/* Header */}
        <div className="space-y-2">
          <button
            onClick={handleBackToAgents}
            className="flex items-center gap-1.5 text-xs text-black/40 hover:text-black transition-colors group mb-4"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5" />
            <span className="font-medium">Back</span>
          </button>
          <h1 className="text-2xl font-black text-black tracking-tight">Customize Your Agent</h1>
          <p className="text-sm text-black/50 font-medium max-w-md">
            Build and run your custom workflow in three simple steps.
          </p>
        </div>

        {/* Divider */}
        <div className="h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" />

        {/* Steps with external labels */}
        <div className="grid grid-cols-3 gap-5">
          
          {/* Step 1: Create - Lightest */}
          <div className="p-4 rounded-sm bg-stone-200/60 space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 flex items-center justify-center text-[10px] font-bold bg-stone-300 text-stone-700">1</span>
              <span className="text-sm font-bold text-stone-700">Create</span>
            </div>
            <button 
              onClick={handleCreateNewWorkflow}
              disabled={isCreatingWorkflow}
              className="group w-full relative flex flex-col p-5 bg-white border border-stone-200 hover:border-stone-300 hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] transition-all text-left overflow-hidden disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
                <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-stone-300 to-transparent" />
                <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-stone-300 to-transparent" />
              </div>
              <div className="w-10 h-10 bg-stone-100 text-stone-600 flex items-center justify-center mb-3 group-hover:bg-stone-700 group-hover:text-white transition-colors">
                {isCreatingWorkflow ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Plus className="w-5 h-5" />
                )}
              </div>
              <div className="text-[15px] font-bold text-stone-800 mb-1">New</div>
              <div className="text-xs text-stone-500 leading-relaxed">Tune your own AI skills from scratch</div>
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-stone-500 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
            </button>
            <div className="flex items-center justify-center">
              <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wider">or</span>
            </div>
            <div 
              className="group w-full relative flex flex-col p-5 bg-white/60 border border-stone-200 text-left overflow-hidden cursor-not-allowed opacity-70"
            >
              {/* Coming Soon Badge */}
              <div className="absolute top-3 right-3 px-2 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase tracking-wider rounded-sm flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" />
                Coming Soon
              </div>
              <div className="w-10 h-10 bg-stone-100 text-stone-400 flex items-center justify-center mb-3">
                <Download className="w-5 h-5" />
              </div>
              <div className="text-[15px] font-bold text-stone-500 mb-1">Import</div>
              <div className="text-xs text-stone-400 leading-relaxed">Modify an existing workflow</div>
            </div>
          </div>

          {/* Step 2: Deploy - Medium */}
          <div className="p-4 rounded-sm bg-stone-300/60 space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 flex items-center justify-center text-[10px] font-bold bg-stone-400 text-white">2</span>
              <span className="text-sm font-bold text-stone-700">Deploy</span>
            </div>
            <button 
              onClick={() => { handleSelectLocal(); setCustomizeStep(3); }}
              className="group w-full relative flex flex-col p-5 bg-white border border-stone-200 hover:border-stone-300 hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] transition-all text-left overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
                <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-stone-300 to-transparent" />
                <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-stone-300 to-transparent" />
              </div>
              <div className="w-10 h-10 bg-stone-100 text-stone-600 flex items-center justify-center mb-3 group-hover:bg-stone-700 group-hover:text-white transition-colors">
                <Monitor className="w-5 h-5" />
              </div>
              <div className="text-[15px] font-bold text-stone-800 mb-1">This PC</div>
              <div className="text-xs text-stone-500 leading-relaxed">Fast & free, shares your desktop</div>
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-stone-500 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
            </button>
            <div className="flex items-center justify-center">
              <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wider">or</span>
            </div>
            <button 
              onClick={() => { handleCreateVm(); setCustomizeStep(3); }}
              className="group w-full relative flex flex-col p-5 bg-white border border-stone-200 hover:border-stone-300 hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] transition-all text-left overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
                <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-stone-300 to-transparent" />
                <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-stone-300 to-transparent" />
              </div>
              <div className="w-10 h-10 bg-stone-100 text-stone-600 flex items-center justify-center mb-3 group-hover:bg-stone-700 group-hover:text-white transition-colors">
                <Box className="w-5 h-5" />
              </div>
              <div className="text-[15px] font-bold text-stone-800 mb-1">VM</div>
              <div className="text-xs text-stone-500 leading-relaxed">Isolated & safe, requires credits</div>
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-stone-500 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
            </button>
          </div>

          {/* Step 3: Run - Darkest */}
          <div className="p-4 rounded-sm bg-stone-400/60 space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 flex items-center justify-center text-[10px] font-bold bg-stone-500 text-white">3</span>
              <span className="text-sm font-bold text-stone-700">Run</span>
            </div>
            <button 
              onClick={() => setShowLocalRunDialog(true)}
              className="group w-full relative flex flex-col p-5 bg-white border border-stone-200 hover:border-stone-300 hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] transition-all text-left overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
                <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-stone-300 to-transparent" />
                <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-stone-300 to-transparent" />
              </div>
              <div className="w-10 h-10 bg-stone-100 text-stone-600 flex items-center justify-center mb-3 group-hover:bg-stone-700 group-hover:text-white transition-colors">
                <Play className="w-5 h-5" />
              </div>
              <div className="text-[15px] font-bold text-stone-800 mb-1">Run Local</div>
              <div className="text-xs text-stone-500 leading-relaxed">Collaborate with AI on your machine</div>
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-stone-500 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
            </button>
            {REMOTE_CONTROL_ENABLED && (
              <>
                <div className="flex items-center justify-center">
                  <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wider">or</span>
                </div>
                <button 
                  onClick={() => window.open(REMOTE_CONTROL_URL, '_blank')}
                  className="group w-full relative flex flex-col p-5 bg-white border border-stone-200 hover:border-stone-300 hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] transition-all text-left overflow-hidden"
                >
                  <div className="absolute top-0 right-0 w-12 h-12 overflow-hidden">
                    <div className="absolute top-0 right-0 w-[1px] h-8 bg-gradient-to-b from-stone-300 to-transparent" />
                    <div className="absolute top-0 right-0 h-[1px] w-8 bg-gradient-to-l from-stone-300 to-transparent" />
                  </div>
                  {/* External link indicator */}
                  <div className="absolute top-3 right-3 text-stone-400 group-hover:text-stone-600 transition-colors">
                    <ExternalLink className="w-3.5 h-3.5" />
                  </div>
                  <div className="w-10 h-10 bg-stone-100 text-stone-600 flex items-center justify-center mb-3 group-hover:bg-stone-700 group-hover:text-white transition-colors">
                    <Smartphone className="w-5 h-5" />
                  </div>
                  <div className="text-[15px] font-bold text-stone-800 mb-1">Remote</div>
                  <div className="text-xs text-stone-500 leading-relaxed">Control from phone or another device</div>
                  <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-stone-500 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
                </button>
              </>
            )}
          </div>

        </div>

        {/* Run Local Info Dialog */}
        <InfoDialog
          open={showLocalRunDialog}
          onClose={() => setShowLocalRunDialog(false)}
          title="You're Using Desktop App"
          icon="success"
          confirmLabel="Got it"
        >
          <div className="space-y-3">
            <p className="text-sm text-gray-600 leading-relaxed">
              You are currently running the <span className="font-semibold text-gray-900">UseIt Studio Desktop App</span>. 
              This means your workflows will execute directly on this computer.
            </p>
            <div className="flex items-start gap-2.5 p-3 bg-blue-50/80 rounded-md border border-blue-100">
              <Monitor className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-blue-700 leading-relaxed">
                <span className="font-semibold">Local execution</span> provides the fastest performance and 
                allows the AI to interact directly with your desktop environment.
              </div>
            </div>
          </div>
        </InfoDialog>

      </div>
    </div>
  );
}
