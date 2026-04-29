'use client';

import React, { forwardRef, useImperativeHandle, useEffect, useState, useCallback, useMemo } from 'react';
import { File } from 'lucide-react';
import { appAction } from '../chat/handlers/appActions';
import { useChat } from '../chat/hooks/useChat';
import { MessageList, ChatInput } from '../chat/components';
import type { AttachedFile } from '../chat/components/ChatInput';
import type { AttachedImage, Message } from '../chat/handlers/types';
import type { SyncProgressInfo, DeletedFileInfo } from '../chat/components/SyncStatusCard';
import type { FileNode } from '@/features/workspace/file-explorer/types';
import { useWorkflow } from '@/features/workflow';
import { parseQuickStartMessage, stripFileReferences, extractFilePaths } from '@/features/workflow/utils/quickStartParser';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { ExploreWelcome } from './components/ExploreWelcome';
import type { AgentId } from '@/features/chat/hooks/useChat';

/** Shown under the chat when entering a workflow via "Vibe Workflow" (until first user message). */
const VIBE_WORKFLOW_EXAMPLE_PROMPTS = [
  'Help me build a workflow that opens Excel, reads the sales sheet, and writes a short summary into a Word document.',
  'Create a flow that opens the browser, goes to my company portal, and downloads last month’s invoices.',
  'I want a workflow with a user instruction step, then a computer-use node that organizes receipt images from a folder into dated subfolders.',
];

/** 与 Electron `fs-read-file`、输入框粘贴图片范围对齐 */
const IMAGE_FILENAME_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico',
]);

function isImageFileName(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  const dot = lower.lastIndexOf('.');
  if (dot < 0) return false;
  return IMAGE_FILENAME_EXTENSIONS.has(lower.slice(dot));
}

function mimeTypeFromDataUrl(dataUrl: string): string {
  const m = /^data:([^;]+);base64,/.exec(dataUrl);
  return m ? m[1] : 'image/png';
}

/**
 * ChatPanel 暴露的方法接口
 */
export interface ChatPanelRef {
  chatId: string | null;
  switchToChat: (chatId: string, title?: string) => Promise<void>;
  startNewChat: () => void;
  addFile?: (filePath: string, fileName: string, type: 'file' | 'folder') => void | Promise<void>;
  selectAgent?: (agentId: string) => void;
  sendMessage?: (message: string, images?: AttachedImage[], agentId?: string) => void;
}

interface ChatPanelProps {
  onChatIdChange?: (chatId: string | null, title?: string) => void;
  /** 发送前执行（如先触发左侧文件上传），返回 Promise<boolean>，true 继续发送，false 取消发送 */
  onBeforeSend?: () => Promise<boolean>;
  /** 每完成一个节点时调用（如触发左侧文件 explorer 同步/刷新） */
  onNodeEnd?: () => void;
  /** 文件同步进度信息（显示在 loading 区域） */
  syncProgress?: SyncProgressInfo | null;
  /** 取消同步 */
  onCancelSync?: () => void;
  /** 文件删除确认信息 */
  deleteConfirmation?: {
    deletedFiles: DeletedFileInfo[];
  } | null;
  /** 确认删除并继续上传 */
  onConfirmDelete?: (shouldDelete: boolean) => void;
  /** 取消删除确认 */
  onCancelDeleteConfirm?: () => void;
  /** 文件树数据（用于 @ 文件引用） */
  fileTree?: FileNode[];
  /** Explore welcome: fork workflow into workspace */
  onForkWorkflow?: (workflowId: string) => void;
  /** Explore welcome: select agent */
  onExploreSelectAgent?: (agentId: string) => void;
  /** Explore welcome: collapse to sidebar */
  onCollapse?: () => void;
  /** 用户消息已成功提交发送后（非 /app、非取消上传） */
  onMessageSent?: () => void;
  /** Explore welcome: current project id */
  projectId?: string;
  /** Whether the workspace has open tabs (canvas visible) */
  hasWorkspaceTabs?: boolean;
}

/**
 * 工作区聊天面板 - 与精简版共享的核心部分
 */
const ChatPanel = forwardRef<ChatPanelRef, ChatPanelProps>(({ 
  onChatIdChange, 
  onBeforeSend, 
  onNodeEnd, 
  syncProgress,
  onCancelSync,
  deleteConfirmation,
  onConfirmDelete,
  onCancelDeleteConfirm,
  fileTree,
  onForkWorkflow,
  onExploreSelectAgent,
  onCollapse,
  onMessageSent,
  projectId,
  hasWorkspaceTabs,
}, ref) => {
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);

  // Sync selectedComputer <-> activeTargetId via shared store
  const activeTargetId = useWorkspaceStore((s) => s.activeTargetId);
  const setActiveTargetId = useWorkspaceStore((s) => s.setActiveTargetId);
  const isExploreFullscreen = useWorkspaceStore((s) => s.isExploreFullscreen);
  const setExploreFullscreen = useWorkspaceStore((s) => s.setExploreFullscreen);
  const vibeWorkflowHintWorkflowId = useWorkspaceStore((s) => s.vibeWorkflowHintWorkflowId);
  const setVibeWorkflowHintWorkflowId = useWorkspaceStore((s) => s.setVibeWorkflowHintWorkflowId);

  const [envConfigs, setEnvConfigs] = useState<Array<{ id: string; name: string }>>([]);
  useEffect(() => {
    const load = async () => {
      if (window.electron?.getAppConfig) {
        const envs = (await window.electron.getAppConfig('environments')) || [];
        setEnvConfigs(
          (envs as any[]).map((e: any) => ({ id: e.id, name: e.name }))
        );
      }
    };
    load();
    const handler = () => { load(); };
    window.addEventListener('environments-updated', handler);
    return () => window.removeEventListener('environments-updated', handler);
  }, []);

  const selectedComputer = useMemo(() => {
    if (!activeTargetId || activeTargetId === 'local') return 'This PC';
    const env = envConfigs.find((e) => e.id === activeTargetId);
    return env?.name || 'This PC';
  }, [activeTargetId, envConfigs]);

  const handleComputerChange = useCallback((name: string) => {
    if (name === 'This PC') {
      setActiveTargetId('local');
    } else {
      const env = envConfigs.find((e) => e.name === name);
      if (env) setActiveTargetId(env.id);
    }
  }, [envConfigs, setActiveTargetId]);

  const {
    input,
    setInput,
    messages,
    setMessages,
    isLoading,
    setIsLoading,
    isStopping,
    selectedAgentId,
    setSelectedAgentId,
    sendMessage,
    handleStop,
    clearMessages,
    chatId,
    chatTitle,
    switchToChat,
    startNewChat,
    settleAskUser,
  } = useChat({ onNodeEnd });

  // Extract workflow ID from selectedAgentId (format: "workflow:{uuid}")
  const selectedWorkflowId = useMemo(() => {
    if (selectedAgentId && selectedAgentId.startsWith('workflow:')) {
      return selectedAgentId.replace('workflow:', '');
    }
    return null;
  }, [selectedAgentId]);

  // Get workflow data for quick start messages
  const { workflow: selectedWorkflow } = useWorkflow(selectedWorkflowId);
  const quickStartMessages = selectedWorkflow?.quick_start_messages;

  // Workflow drag-and-drop: auto-load first quick start message
  const [workflowDropOver, setWorkflowDropOver] = useState(false);
  const [pendingQuickStartWorkflowId, setPendingQuickStartWorkflowId] = useState<string | null>(null);

  // 包装 sendMessage：先显示用户消息，再执行 onBeforeSend（如发送前上传），最后发送
  const handleSendMessage = useCallback(async (message: string, extraImages?: AttachedImage[], agentId?: string) => {
    if (agentId) setSelectedAgentId(agentId);
    const finalMessage = stripFileReferences(message.trim());

    // DEV: /app slash command — bypass upload and execute app action locally
    if (finalMessage.startsWith('/app ')) {
      const raw = finalMessage.slice(5);
      const spaceIdx = raw.indexOf(' ');
      const actionName = spaceIdx === -1 ? raw : raw.slice(0, spaceIdx);
      let args: Record<string, any> = {};
      if (spaceIdx !== -1) {
        try { args = JSON.parse(raw.slice(spaceIdx + 1)); } catch { args = {}; }
      }
      const userMsg: Message = {
        id: Date.now().toString(), role: 'user', timestamp: Date.now(), content: finalMessage,
        blocks: [{ type: 'text', content: finalMessage }],
      };
      const result = await appAction.executeAction(actionName, args);
      const replyText = result.success
        ? `✅ Action \`${actionName}\` executed.\n${result.data ? '```json\n' + JSON.stringify(result.data, null, 2) + '\n```' : ''}`
        : `❌ Action \`${actionName}\` failed: ${result.error}`;
      const botMsg: Message = {
        id: (Date.now() + 1).toString(), role: 'assistant', timestamp: Date.now(), content: replyText,
        blocks: [{ type: 'text', content: replyText }],
      };
      setMessages((prev) => [...prev.filter((m) => m.id !== 'welcome'), userMsg, botMsg]);
      setInput('');
      return;
    }
    
    // 只有当有消息内容或附加文件时才发送
    if (finalMessage || attachedFiles.length > 0 || attachedImages.length > 0) {
      // 1. 先在界面上显示用户消息
      const tempMessageId = `pending-${Date.now()}`;
      const filesToSend = attachedFiles.length > 0 
        ? attachedFiles.map(f => ({ path: f.path, name: f.name, type: f.type }))
        : undefined;
      const mergedImages = [...attachedImages, ...(extraImages ?? [])];
      const imagesToSend = mergedImages.length > 0 ? mergedImages : undefined;
      
      const userMessage = {
        id: tempMessageId,
        role: 'user' as const,
        content: finalMessage || '',
        timestamp: Date.now(),
        blocks: [{ type: 'text' as const, content: finalMessage || '' }],
        attachedFiles: filesToSend?.map((f, idx) => ({ ...f, id: `file-${Date.now()}-${idx}` })),
        attachedImages: imagesToSend,
      };
      
      // 添加用户消息到界面（移除欢迎消息）
      setMessages((prev) => {
        const withoutWelcome = prev.filter((msg) => msg.id !== 'welcome');
        return [...withoutWelcome, userMessage];
      });

      if (isExploreFullscreen) setExploreFullscreen(false);
      
      // 清空输入框
      setInput('');
      
      // 设置 loading 状态（显示同步卡片）
      setIsLoading(true);
      
      // 2. 执行 onBeforeSend（文件上传/确认）
      if (onBeforeSend) {
        const shouldContinue = await onBeforeSend();
        if (!shouldContinue) {
          // 用户取消，移除刚添加的用户消息，恢复输入
          setMessages((prev) => prev.filter((msg) => msg.id !== tempMessageId));
          setInput(finalMessage);
          setIsLoading(false);
          return;
        }
      }
      
      // 3. 移除临时消息（sendMessage 会重新添加带正确 ID 的消息）
      setMessages((prev) => prev.filter((msg) => msg.id !== tempMessageId));
      setIsLoading(false);
      
      // 4. 调用真正的 sendMessage（传入 agentId，避免 await onBeforeSend 期间 setSelectedAgentId 尚未写入 ref）
      sendMessage(finalMessage || '', selectedComputer, filesToSend, imagesToSend, agentId ? { agentId } : undefined);
      onMessageSent?.();
      // 发送后清空附加文件和图片列表
      setAttachedFiles([]);
      setAttachedImages([]);
    }
  }, [sendMessage, selectedComputer, attachedFiles, attachedImages, onBeforeSend, onMessageSent, setMessages, setInput, setIsLoading]);

  // 添加文件到聊天；若为图片路径则读取为 base64，与粘贴一致进入 attachedImages
  const handleAddFile = useCallback(async (filePath: string, fileName: string, type: 'file' | 'folder') => {
    if (type === 'folder') {
      const newFile: AttachedFile = {
        id: `${Date.now()}-${Math.random()}`,
        path: filePath,
        name: fileName,
        type,
      };
      setAttachedFiles((prev) => [...prev, newFile]);
      return;
    }

    if (isImageFileName(fileName)) {
      const electron = (window as any).electron;
      if (electron?.fsReadFile) {
        try {
          const result = await electron.fsReadFile(filePath);
          if (result?.type === 'image' && typeof result.content === 'string' && result.content.startsWith('data:')) {
            const image: AttachedImage = {
              id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              name: fileName,
              base64: result.content,
              mimeType: mimeTypeFromDataUrl(result.content),
              size: typeof result.size === 'number' ? result.size : 0,
            };
            setAttachedImages((prev) => [...prev, image]);
            return;
          }
        } catch (e) {
          console.error('Failed to load image for chat attachment:', e);
        }
      }
    }

    const newFile: AttachedFile = {
      id: `${Date.now()}-${Math.random()}`,
      path: filePath,
      name: fileName,
      type,
    };
    setAttachedFiles((prev) => [...prev, newFile]);
  }, []);

  // 移除文件
  const handleRemoveFile = useCallback((fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  }, []);

  // 添加图片
  const handleAddImages = useCallback((images: AttachedImage[]) => {
    setAttachedImages((prev) => [...prev, ...images]);
  }, []);

  // 移除图片
  const handleRemoveImage = useCallback((imageId: string) => {
    setAttachedImages((prev) => {
      const removed = prev.find((img) => img.id === imageId);
      if (removed) {
        const name = removed.name;
        setInput((prevInput) => {
          const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const regex = new RegExp(`@"[^"]*?${escaped}"|@[\\w./\\\\-]*?${escaped}`, 'g');
          return prevInput.replace(regex, '').replace(/\s{2,}/g, ' ').trim();
        });
      }
      return prev.filter((img) => img.id !== imageId);
    });
  }, []);

  // 暴露方法给父组件
  useImperativeHandle(ref, () => ({
    chatId,
    switchToChat,
    startNewChat,
    addFile: handleAddFile,
    selectAgent: setSelectedAgentId,
    sendMessage: handleSendMessage,
  }), [chatId, switchToChat, startNewChat, handleAddFile, setSelectedAgentId, handleSendMessage]);

  // 当 chatId 或 chatTitle 变化时通知父组件
  useEffect(() => {
    if (onChatIdChange) {
      onChatIdChange(chatId, chatTitle || undefined);
    }
  }, [chatId, chatTitle, onChatIdChange]);


  // Check if we should show quick start messages - only show when no messages sent yet
  const hasUserMessages = messages.some(msg => msg.role === 'user');
  const showQuickStart = quickStartMessages && quickStartMessages.length > 0 && !hasUserMessages;
  const showVibeWorkflowHints =
    Boolean(vibeWorkflowHintWorkflowId) &&
    selectedWorkflowId === vibeWorkflowHintWorkflowId &&
    !hasUserMessages &&
    !(quickStartMessages && quickStartMessages.length > 0);

  useEffect(() => {
    if (hasUserMessages && vibeWorkflowHintWorkflowId) {
      setVibeWorkflowHintWorkflowId(null);
    }
  }, [hasUserMessages, vibeWorkflowHintWorkflowId, setVibeWorkflowHintWorkflowId]);

  useEffect(() => {
    if (
      vibeWorkflowHintWorkflowId &&
      selectedWorkflowId &&
      selectedWorkflowId !== vibeWorkflowHintWorkflowId
    ) {
      setVibeWorkflowHintWorkflowId(null);
    }
  }, [selectedWorkflowId, vibeWorkflowHintWorkflowId, setVibeWorkflowHintWorkflowId]);

  // Handle quick start message click - parse @file references and attach them
  const handleQuickStartClick = useCallback(async (message: string) => {
    const filePaths = extractFilePaths(message);
    setInput(message);

    if (filePaths.length > 0) {
      const electron = (window as any).electron;
      if (electron?.fsGetProjectRoot) {
        try {
          const projectId = (window as any).__currentProjectId;
          const projectRoot = await electron.fsGetProjectRoot(projectId);
          const normalize = (p: string) => p.replace(/\\/g, '/').replace(/\/$/, '');
          const root = normalize(projectRoot);

          await Promise.all(
            filePaths.map(async (relPath) => {
              const absPath = `${root}/${relPath}`;
              const name = relPath.split('/').pop() || relPath;
              await handleAddFile(absPath, name, 'file');
            })
          );
        } catch (err) {
          console.error('Failed to resolve file paths for quick start:', err);
        }
      }
    }
  }, [setInput, handleAddFile]);

  // Handle workflow drop (from sidebar drag or ExploreWelcome callback)
  const handleWorkflowDropById = useCallback((workflowId: string) => {
    setInput('');
    setAttachedFiles([]);
    setAttachedImages([]);
    setSelectedAgentId(`workflow:${workflowId}`);
    setPendingQuickStartWorkflowId(workflowId);
  }, [setSelectedAgentId]);

  const handleWorkflowDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setWorkflowDropOver(false);

    const workflowId = e.dataTransfer.getData('application/x-workflow-id');
    if (workflowId) {
      handleWorkflowDropById(workflowId);
      return;
    }

    const filePath = e.dataTransfer.getData('application/x-file-path');
    const fileName = e.dataTransfer.getData('application/x-file-name');
    const fileType = e.dataTransfer.getData('application/x-file-type') as 'file' | 'folder';
    if (filePath && fileName) {
      handleAddFile(filePath, fileName, fileType || 'file');
    }
  }, [handleWorkflowDropById, handleAddFile]);

  const handleWorkflowDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes('application/x-workflow-id') ||
        e.dataTransfer.types.includes('application/x-file-path')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      setWorkflowDropOver(true);
    }
  }, []);

  const handleWorkflowDragLeave = useCallback((e: React.DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setWorkflowDropOver(false);
  }, []);

  // When a workflow is dropped and its data loads, auto-load the first quick start message
  useEffect(() => {
    if (
      pendingQuickStartWorkflowId &&
      selectedWorkflow &&
      selectedWorkflow.id === pendingQuickStartWorkflowId &&
      selectedWorkflow.quick_start_messages &&
      selectedWorkflow.quick_start_messages.length > 0
    ) {
      handleQuickStartClick(selectedWorkflow.quick_start_messages[0]);
      setPendingQuickStartWorkflowId(null);
    }
  }, [pendingQuickStartWorkflowId, selectedWorkflow, handleQuickStartClick]);

  const showExploreWelcome = !hasUserMessages && !isLoading && !hasWorkspaceTabs;

  if (showExploreWelcome) {
    return (
      <div className="h-full bg-canvas overflow-y-auto">
        <ExploreWelcome
          input={input}
          onInputChange={setInput}
          attachedImages={attachedImages}
          onAddImages={handleAddImages}
          onRemoveImage={handleRemoveImage}
          attachedFiles={attachedFiles}
          onRemoveFile={handleRemoveFile}
          onSend={handleSendMessage}
          onForkWorkflow={onForkWorkflow}
          onWorkflowDrop={handleWorkflowDropById}
          onSelectAgent={onExploreSelectAgent}
          onCollapse={onCollapse}
          projectId={projectId}
          selectedAgentId={selectedAgentId as AgentId}
          onSelectedAgentIdChange={setSelectedAgentId}
          fileTree={fileTree}
          onAddFile={handleAddFile}
        />
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col h-full bg-canvas overflow-hidden relative ${workflowDropOver ? 'ring-2 ring-inset ring-orange-400 bg-orange-50/30' : ''}`}
      onDragOver={handleWorkflowDragOver}
      onDragLeave={handleWorkflowDragLeave}
      onDrop={handleWorkflowDrop}
    >
      {workflowDropOver && (
        <div className="absolute inset-0 z-50 flex items-center justify-center pointer-events-none">
          <div className="px-5 py-3 bg-white/95 backdrop-blur-sm rounded-xl shadow-lg border border-orange-200 text-sm font-medium text-orange-600">
            Drop to load workflow
          </div>
        </div>
      )}
      {/* 消息区域 */}
      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin-overlay">
        <MessageList 
          messages={messages} 
          isLoading={isLoading}
          syncProgress={syncProgress}
          onCancelSync={onCancelSync}
          deleteConfirmation={deleteConfirmation}
          onConfirmDelete={onConfirmDelete}
          onCancelDeleteConfirm={onCancelDeleteConfirm}
          onAskUserSettle={settleAskUser}
        />
      </div>

      {/* Quick Start Messages */}
      {showQuickStart && (
        <div className="flex-shrink-0 px-4 pb-1.5">
          <div className="max-w-5xl mx-auto w-full">
            <div className="text-[10px] text-black/70 font-medium uppercase tracking-wider mb-1 px-2.5">Quick Start</div>
            <div className="flex flex-col gap-1">
              {quickStartMessages.map((msg, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => handleQuickStartClick(msg)}
                  className="inline-flex items-center flex-wrap gap-0.5 px-2.5 py-1 text-[12px] text-black/50 hover:text-black/80 hover:bg-black/5 rounded transition-colors text-left"
                >
                  {parseQuickStartMessage(msg).map((seg, si) =>
                    seg.type === 'text' ? (
                      <span key={si}>{seg.value}</span>
                    ) : (
                      <span
                        key={si}
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-orange-50/80 border border-orange-200/60 rounded text-[11px] text-orange-800 font-medium"
                      >
                        <File className="w-2.5 h-2.5 flex-shrink-0" />
                        {seg.name}
                      </span>
                    )
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Vibe Workflow: example prompts (no workflow quick_start_messages) */}
      {showVibeWorkflowHints && (
        <div className="flex-shrink-0 px-4 pb-1.5">
          <div className="max-w-5xl mx-auto w-full rounded-lg border border-violet-200/50 bg-violet-50/40 px-3 py-2.5">
            <div className="text-[10px] text-violet-800/90 font-semibold uppercase tracking-wider mb-1 px-0.5">
              Try asking
            </div>
            <p className="text-[11px] text-black/45 mb-2 px-0.5 leading-snug">
              Describe the task in plain language. The assistant can add nodes, connect steps, and adjust your workflow on the canvas.
            </p>
            <div className="flex flex-col gap-1">
              {VIBE_WORKFLOW_EXAMPLE_PROMPTS.map((msg, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => handleQuickStartClick(msg)}
                  className="text-left px-2 py-1.5 text-[12px] text-black/55 hover:text-violet-900 hover:bg-violet-100/60 rounded-md transition-colors leading-snug border border-transparent hover:border-violet-200/60"
                >
                  {msg}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 输入区域 */}
      <div className="flex-shrink-0 px-4 pb-4">
        <div className="max-w-5xl mx-auto w-full">
          <ChatInput  
            input={input}
            setInput={setInput}
            isLoading={isLoading}
            isStopping={isStopping}
            selectedAgentId={selectedAgentId}
            setSelectedAgentId={setSelectedAgentId}
            onSend={handleSendMessage}
            onStop={handleStop}
            chatId={chatId ?? undefined}
            selectedComputer={selectedComputer}
            onComputerChange={handleComputerChange}
            attachedFiles={attachedFiles}
            onRemoveFile={handleRemoveFile}
            attachedImages={attachedImages}
            onAddImages={handleAddImages}
            onRemoveImage={handleRemoveImage}
            fileTree={fileTree}
            onAddFile={handleAddFile}
          />
        </div>
      </div>
    </div>
  );
});

ChatPanel.displayName = 'ChatPanel';

export default ChatPanel;
