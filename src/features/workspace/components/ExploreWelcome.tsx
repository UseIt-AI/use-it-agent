import React, { useCallback, useRef, useState, useEffect, useMemo } from 'react';
import { observer } from 'mobx-react-lite';
import clsx from 'clsx';
import { ChevronDown, Loader2, ArrowUp, Paperclip, File, Folder, X } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useTranslation } from 'react-i18next';
import type { AttachedImage } from '@/features/chat/handlers/types';
import type { AttachedFile } from '@/features/chat/components/ChatInput';
import type { FileNode } from '@/features/workspace/file-explorer/types';
import { AgentDropdown } from '@/features/chat/components/AgentDropdown';
import { useChatAgents } from '@/features/chat/hooks/useChatAgents';
import type { AgentId } from '@/features/chat/hooks/useChat';
import { usePublicWorkflows, useCreateWorkflow } from '@/features/workflow';
import type { PublicWorkflowListItem } from '@/features/workflow';
import { AgentCard, CustomizeCard, AgentDetailDialog } from '@/features/workspace/components/EmptyWorkspaceGuide';
import { extractFilePaths, parseQuickStartMessage } from '@/features/workflow/utils/quickStartParser';
import { flattenAllFiles } from '@/features/chat/utils/fileTreeUtils';
import type { FlatFileItem } from '@/features/chat/utils/fileTreeUtils';
import { RichTextInput } from './RichTextInput';
import { useProject } from '@/contexts/ProjectContext';

function fileToAttachedImage(file: File): Promise<AttachedImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({
      id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: file.name,
      base64: reader.result as string,
      mimeType: file.type || 'image/png',
      size: file.size,
    });
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico']);

function ImageThumbnail({ img, onRemove, onReplace, imageFiles }: {
  img: AttachedImage;
  onRemove: (id: string) => void;
  onReplace: (oldId: string, newFile: FlatFileItem) => void;
  imageFiles: FlatFileItem[];
}) {
  const [showReplace, setShowReplace] = React.useState(false);
  const [ddPos, setDdPos] = React.useState({ top: 0, left: 0 });
  const thumbRef = React.useRef<HTMLDivElement>(null);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  const ext = img.name.lastIndexOf('.') >= 0 ? img.name.slice(img.name.lastIndexOf('.')).toLowerCase() : '';
  const alternatives = React.useMemo(
    () => imageFiles.filter(f => {
      const fExt = f.name.lastIndexOf('.') >= 0 ? f.name.slice(f.name.lastIndexOf('.')).toLowerCase() : '';
      return fExt === ext && f.name !== img.name;
    }),
    [imageFiles, ext, img.name]
  );

  const hoverTimeout = React.useRef<ReturnType<typeof setTimeout>>();

  const openDropdown = () => {
    if (thumbRef.current) {
      const rect = thumbRef.current.getBoundingClientRect();
      setDdPos({ top: rect.bottom + 4, left: rect.left });
    }
    setShowReplace(true);
  };

  const handleBtnEnter = () => {
    clearTimeout(hoverTimeout.current);
    openDropdown();
  };

  const handleLeave = () => {
    hoverTimeout.current = setTimeout(() => setShowReplace(false), 150);
  };

  const handleDropdownEnter = () => {
    clearTimeout(hoverTimeout.current);
  };

  React.useEffect(() => {
    if (!showReplace || !dropdownRef.current) return;
    const el = dropdownRef.current;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let { top, left } = ddPos;
    if (rect.right > vw - 8) left = Math.max(8, vw - rect.width - 8);
    if (rect.bottom > vh - 8) top = ddPos.top - rect.height - 72;
    if (left !== ddPos.left || top !== ddPos.top) {
      setDdPos({ top, left });
    }
  }, [showReplace, ddPos]);

  const thumbSrc = img.url || img.base64 || '';
  return (
    <div ref={thumbRef} className="relative group/img w-16 h-16 rounded-md overflow-visible border border-gray-200 bg-gray-50">
      <img
        src={thumbSrc}
        alt={img.name}
        className="w-full h-full object-cover rounded-md"
        draggable={false}
      />
      <div className="absolute top-0.5 right-0.5 flex items-center gap-0.5 opacity-0 group-hover/img:opacity-100 transition-opacity">
        {alternatives.length > 0 && (
          <button
            type="button"
            onMouseEnter={handleBtnEnter}
            onMouseLeave={handleLeave}
            className="p-0.5 bg-black/50 hover:bg-black/70 rounded-full"
          >
            <ChevronDown className="w-3 h-3 text-white" />
          </button>
        )}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(img.id); }}
          className="p-0.5 bg-black/50 hover:bg-black/70 rounded-full"
        >
          <X className="w-3 h-3 text-white" />
        </button>
      </div>
      {showReplace && alternatives.length > 0 && (
        <div
          ref={dropdownRef}
          onMouseEnter={handleDropdownEnter}
          onMouseLeave={handleLeave}
          className="fixed w-[240px] max-h-[200px] overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg z-[9999]"
          style={{ top: ddPos.top, left: ddPos.left }}
        >
          <div className="py-1">
            <div className="px-2.5 py-1 text-[10px] text-black/40 font-medium uppercase tracking-wider">
              Replace with
            </div>
            {alternatives.map(file => (
              <button
                key={file.path}
                type="button"
                onClick={() => { onReplace(img.id, file); setShowReplace(false); }}
                className="w-full flex items-center gap-1.5 px-2.5 py-1.5 text-left text-xs text-gray-700 hover:bg-orange-50 hover:text-orange-900 transition-colors"
              >
                <File className="w-3 h-3 flex-shrink-0 text-gray-400" />
                <span className="font-medium truncate">{file.name}</span>
                <span className="text-[10px] text-black/25 truncate ml-auto max-w-[40%]">
                  {file.relativePath}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Rotating typewriter hint ─────────────────────────────────────────────────

interface HintItem {
  text: string;
  isPrompt?: boolean;
}

function RotatingHint({ hints, onTab }: { hints: HintItem[]; onTab?: () => void }) {
  const [idx, setIdx] = useState(0);
  const [displayed, setDisplayed] = useState('');
  const [phase, setPhase] = useState<'typing' | 'hold' | 'fading'>('typing');

  const current = hints[idx];

  useEffect(() => {
    setDisplayed('');
    setPhase('typing');

    let charIdx = 0;
    let rafId: number;
    const charDuration = 30;
    const startTime = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const target = Math.min(Math.floor(elapsed / charDuration), current.text.length);
      if (target > charIdx) {
        charIdx = target;
        setDisplayed(current.text.slice(0, charIdx));
      }
      if (charIdx < current.text.length) {
        rafId = requestAnimationFrame(tick);
      } else {
        setPhase('hold');
      }
    };
    rafId = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(rafId);
  }, [idx, current.text]);

  useEffect(() => {
    if (phase !== 'hold') return;
    const holdTimer = setTimeout(() => setPhase('fading'), 2500);
    return () => clearTimeout(holdTimer);
  }, [phase]);

  useEffect(() => {
    if (phase !== 'fading') return;
    const fadeTimer = setTimeout(() => {
      setIdx(prev => (prev + 1) % hints.length);
    }, 400);
    return () => clearTimeout(fadeTimer);
  }, [phase, hints.length]);

  const showTabBtn = current.isPrompt;

  return (
    <div
      className={clsx(
        "flex items-center gap-2 text-[13px] text-black/45 leading-relaxed transition-opacity duration-300",
        phase === 'fading' ? 'opacity-0' : 'opacity-100',
      )}
    >
      <span className="text-black/25 select-none">{'>'}</span>
      <span>{displayed}<span className="animate-pulse">|</span></span>
      {showTabBtn && (
        <button
          type="button"
          onClick={onTab}
          className={clsx(
            "inline-flex items-center px-1.5 py-0.5 border rounded text-[10px] font-mono font-medium transition-all ml-1 flex-shrink-0 shadow-[0_1px_0_rgba(0,0,0,0.06)] pointer-events-auto",
            phase !== 'typing'
              ? "bg-black/[0.06] hover:bg-black/[0.1] border-black/[0.06] text-black/35 hover:text-black/55 opacity-100"
              : "opacity-0 pointer-events-none border-transparent"
          )}
        >
          Tab ↵
        </button>
      )}
    </div>
  );
}

export interface ExploreWelcomeProps {
  input: string;
  onInputChange: (value: string) => void;
  attachedImages: AttachedImage[];
  onAddImages: (images: AttachedImage[]) => void;
  onRemoveImage: (imageId: string) => void;
  attachedFiles: AttachedFile[];
  onRemoveFile: (fileId: string) => void;
  onSend: (message: string, images?: AttachedImage[], agentId?: string) => void;
  onForkWorkflow?: (workflowId: string) => void;
  onWorkflowDrop?: (workflowId: string) => void;
  onSelectAgent?: (agentId: string) => void;
  onCollapse?: () => void;
  projectId?: string;
  selectedAgentId?: AgentId;
  onSelectedAgentIdChange?: (agentId: AgentId) => void;
  fileTree?: FileNode[];
  onAddFile?: (path: string, name: string, type: 'file' | 'folder') => void;
}

export const ExploreWelcome = observer(function ExploreWelcome({
  input,
  onInputChange,
  attachedImages,
  onAddImages,
  onRemoveImage,
  attachedFiles,
  onRemoveFile,
  onSend,
  onForkWorkflow,
  onWorkflowDrop,
  onSelectAgent,
  onCollapse,
  projectId,
  selectedAgentId: externalAgentId,
  onSelectedAgentIdChange,
  fileTree,
  onAddFile,
}: ExploreWelcomeProps) {
  const { profile, user } = useAuth();
  const { t } = useTranslation();
  const displayName = profile?.username || (user?.user_metadata as any)?.name || '';
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

  // --- UI-only local state (animations, menus) ---
  const [isSending, setIsSending] = useState(false);
  const [shake, setShake] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [isAgentMenuOpen, setIsAgentMenuOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- container width for responsive grid ---
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setContainerWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const gridCols = containerWidth >= 640 ? 3 : containerWidth >= 420 ? 2 : 1;

  // --- agents ---
  const { agents, loading: agentsLoading } = useChatAgents();
  const currentAgent = agents.find(a => a.id === externalAgentId) || agents[0];

  const [agentFlash, setAgentFlash] = useState(false);
  const prevAgentIdRef = useRef(externalAgentId);
  useEffect(() => {
    if (prevAgentIdRef.current !== externalAgentId) {
      prevAgentIdRef.current = externalAgentId;
      setAgentFlash(true);
      const timer = setTimeout(() => setAgentFlash(false), 1500);
      return () => clearTimeout(timer);
    }
  }, [externalAgentId]);

  // --- workflow gallery ---
  const { workflows: publicWorkflows, loading: loadingWorkflows, fork } = usePublicWorkflows();
  const { create: createWorkflow } = useCreateWorkflow();
  const [forkingId, setForkingId] = useState<string | null>(null);
  const [detailWorkflow, setDetailWorkflow] = useState<PublicWorkflowListItem | null>(null);
  const [isCreatingWorkflow, setIsCreatingWorkflow] = useState(false);
  const [showAllAgents, setShowAllAgents] = useState(false);

  const handleForkOnly = useCallback(async (workflowId: string): Promise<string> => {
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
  }, [fork]);

  const handleNavigateToWorkflow = useCallback((workflowId: string) => {
    onForkWorkflow?.(workflowId);
  }, [onForkWorkflow]);

  const handleCreateNewWorkflow = useCallback(async () => {
    if (isCreatingWorkflow) return;
    setIsCreatingWorkflow(true);
    try {
      const now = new Date();
      const timestamp = now.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      }).replace(/\//g, '-');
      const newWorkflow = await createWorkflow({ name: `New Workflow ${timestamp}` });
      onForkWorkflow?.(newWorkflow.id);
    } catch (error) {
      console.error('Failed to create workflow:', error);
    } finally {
      setIsCreatingWorkflow(false);
    }
  }, [isCreatingWorkflow, createWorkflow, onForkWorkflow]);

  // --- image upload ---
  const handleUpload = () => fileInputRef.current?.click();

  const handleFileSelect = useCallback(async (files: File[]) => {
    const images = await Promise.all(files.map(f => fileToAttachedImage(f)));
    onAddImages(images);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [onAddImages]);

  // Image files from workspace for replace dropdown
  const imageFiles = useMemo(() => {
    if (!fileTree) return [];
    const rootPfx = fileTree.length > 0 ? (fileTree[0].path || fileTree[0].id || '').replace(/[/\\]$/, '') : '';
    return flattenAllFiles(fileTree, rootPfx).filter(f => {
      const dot = f.name.lastIndexOf('.');
      return dot >= 0 && IMAGE_EXTENSIONS.has(f.name.slice(dot).toLowerCase());
    });
  }, [fileTree]);

  const handleImageReplace = useCallback((oldImageId: string, newFile: FlatFileItem) => {
    onRemoveImage(oldImageId);
    onAddFile?.(newFile.path, newFile.name, 'file');
  }, [onRemoveImage, onAddFile]);

  // Hide file chips already shown as inline @file mentions; strip image @file refs from editor text
  const inlineFileNames = new Set(extractFilePaths(input).map(p => p.split(/[/\\]/).pop() || p));
  const extraFiles = attachedFiles.filter(f => !inlineFileNames.has(f.name));

  const imageNames = useMemo(() => new Set(attachedImages.map(img => img.name)), [attachedImages]);
  const displayInput = useMemo(() => {
    if (imageNames.size === 0) return input;
    return input.split('\n').map(line => {
      const segments = parseQuickStartMessage(line);
      return segments
        .filter(seg => !(seg.type === 'file' && imageNames.has(seg.name)))
        .map(seg => {
          if (seg.type === 'text') return seg.value;
          const needsQuotes = seg.path.includes(' ');
          return needsQuotes ? `@"${seg.path}"` : `@${seg.path}`;
        })
        .join('');
    }).join('\n').replace(/\s{2,}/g, ' ').trim();
  }, [input, imageNames]);

  const handleInlineFileRemove = useCallback((fileName: string) => {
    const file = attachedFiles.find(f => f.name === fileName);
    if (file) onRemoveFile(file.id);
  }, [attachedFiles, onRemoveFile]);

  // --- hints ---
  const showHints = !input.trim() && attachedFiles.length === 0 && attachedImages.length === 0;
  const hintItems = useMemo<HintItem[]>(() => [
    { text: t('explore.hints.dragWorkflow') },
    { text: t('explore.hints.clickCard') },
  ], [t]);
  const handleTabHint = useCallback(() => {
    if (!showHints) return false;
    onInputChange(t('explore.hints.prompt'));
    return true;
  }, [showHints, onInputChange, t]);

  // --- send ---
  const hasContent = input.trim() || attachedFiles.length > 0 || attachedImages.length > 0;

  // When the project was just created (currentProject still null in stale closure),
  // defer the send until React re-renders with the new currentProject.
  const [pendingMessage, setPendingMessage] = useState<{ text: string; images?: AttachedImage[]; agentId?: string } | null>(null);
  useEffect(() => {
    if (!pendingMessage || !currentProject) return;
    const { text, images, agentId } = pendingMessage;
    setPendingMessage(null);
    onSend(text, images, agentId);
  }, [pendingMessage, currentProject, onSend]);

  const handleStartGen = async () => {
    if (isSending) return;
    if (!hasContent) {
      setShake(true);
      setTimeout(() => setShake(false), 400);
      return;
    }
    setIsSending(true);
    const imagesToSend = attachedImages.length > 0 ? [...attachedImages] : undefined;
    try {
      await handleEnsureProject();
      if (currentProject) {
        // Project was already set before this call; closure is up-to-date.
        onSend(input, imagesToSend, currentAgent?.id);
      } else {
        // Project was just created; wait for React to flush before sending.
        setPendingMessage({ text: input, images: imagesToSend, agentId: currentAgent?.id });
      }
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="w-full min-h-full flex flex-col items-center justify-center px-8 py-10 bg-canvas text-[#1f1f1f] relative">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={e => { if (e.target.files?.length) { handleFileSelect(Array.from(e.target.files)); } }}
      />
        {/* Subtle background pattern */}
        <div
          className="absolute inset-0 opacity-[0.4] pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
            backgroundSize: '24px 24px'
          }}
        />

        {/* Content */}
        <div ref={containerRef} className="w-full max-w-[720px] mx-auto relative z-10 animate-in fade-in zoom-in-95 duration-500">
          {/* Greeting */}
          <h2 className="text-[28px] font-black text-black/90 tracking-tight mb-1.5">
            {displayName ? `Hello, ${displayName}.` : t('explore.headline')}
          </h2>
          <p className="text-[13px] text-black/40 font-medium mb-6">
            {t('explore.subtitle')}
          </p>

          {/* Chat-style input box */}
          <div
            onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault();
              setDragOver(false);
              const workflowId = e.dataTransfer.getData('application/x-workflow-id');
              if (workflowId) {
                onWorkflowDrop?.(workflowId);
                return;
              }
              const filePath = e.dataTransfer.getData('application/x-file-path');
              const fileName = e.dataTransfer.getData('application/x-file-name');
              const fileType = e.dataTransfer.getData('application/x-file-type') as 'file' | 'folder';
              if (filePath && fileName) {
                onAddFile?.(filePath, fileName, fileType || 'file');
                return;
              }
              const imageFiles = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
              if (imageFiles.length) {
                handleFileSelect(imageFiles);
              }
            }}
            className={clsx(
              "relative group flex flex-col rounded-lg transition-all duration-200",
              dragOver ? "bg-orange-500/10 ring-1 ring-orange-400" : "bg-black/[0.04]",
              shake && "animate-shake ring-1 ring-red-400",
            )}
          >
            {attachedImages.length > 0 && (
              <div className="flex flex-wrap gap-2 px-3 pt-2.5 pb-1">
                {attachedImages.map((img) => (
                  <ImageThumbnail
                    key={img.id}
                    img={img}
                    onRemove={onRemoveImage}
                    onReplace={handleImageReplace}
                    imageFiles={imageFiles}
                  />
                ))}
              </div>
            )}
            {extraFiles.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-3 pt-2.5 pb-1">
                {extraFiles.map((file) => (
                  <div
                    key={file.id}
                    className="inline-flex items-center gap-1.5 px-2 py-1 bg-orange-50/80 border border-orange-200/60 rounded-md text-xs text-orange-900 group/file hover:bg-orange-100/80 transition-colors"
                  >
                    {file.type === 'folder' ? (
                      <Folder className="w-3 h-3 flex-shrink-0 text-orange-700" />
                    ) : (
                      <File className="w-3 h-3 flex-shrink-0 text-orange-700" />
                    )}
                    <span className="max-w-[200px] truncate font-medium">{file.name}</span>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onRemoveFile(file.id); }}
                      className="opacity-0 group-hover/file:opacity-100 transition-opacity p-0.5 hover:bg-orange-200 rounded flex-shrink-0 ml-0.5"
                    >
                      <X className="w-3 h-3 text-orange-700" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="relative">
              {showHints && (
                <div className="absolute top-3.5 left-4 right-4 z-10 pointer-events-none">
                  <RotatingHint hints={hintItems} onTab={handleTabHint} />
                </div>
              )}
              <RichTextInput
                content={displayInput}
                onChange={onInputChange}
                onSubmit={handleStartGen}
                onFileRemove={handleInlineFileRemove}
                onTab={handleTabHint}
                onPasteFiles={handleFileSelect}
                fileTree={fileTree}
                onAddFile={onAddFile}
                placeholder={showHints ? '' : t('explore.placeholder')}
                className="px-4 pt-3.5 pb-0"
              />
            </div>
            <div className="flex items-end justify-between px-2.5 py-2 bg-transparent gap-2">
              <div className="flex items-center gap-1">
                <button
                  onClick={handleUpload}
                  title={t('explore.uploadTitle')}
                  className="w-7 h-7 rounded-sm flex items-center justify-center text-black/30 hover:text-black/60 hover:bg-black/5 transition-colors"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleStartGen}
                  disabled={isSending || !hasContent}
                  className={clsx(
                    "w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 transition-all duration-200",
                    hasContent && !isSending
                      ? "bg-[#FF4D00] text-white hover:bg-[#E64500] shadow-sm"
                      : "bg-black/10 text-black/25 cursor-not-allowed"
                  )}
                >
                  {isSending
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <ArrowUp className="w-4 h-4 stroke-[2.5px]" />
                  }
                </button>
              </div>
            </div>
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
            onLoadQuickStart={onWorkflowDrop}
            projectId={projectId}
            onEnsureProject={handleEnsureProject}
          />
        )}
    </div>
  );
})
