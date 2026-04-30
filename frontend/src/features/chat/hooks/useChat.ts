/**
 * useChat Hook - 聊天功能核心逻辑
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CommandHandlerContext,
  Message,
  StreamEvent,
  processEvent,
  handleToolCall,
  handleClientRequest,
  isToolCallEvent,
  type ToolCallEvent,
} from '../handlers';
import { useChatAgents } from './useChatAgents';
import appAction from '../handlers/appActions/registry';
import { API_URL, LOCAL_ENGINE_URL } from '@/config/runtimeEnv';
import {
  LOCAL_OFFLINE_USER_ID,
  offlineGetChat,
  offlineInsertChat,
  offlineInsertMessage,
  offlineInsertWorkflowRun,
  offlineListRunsForChat,
  offlineUpdateMessage,
  offlineUpdateWorkflowRun,
} from '@/services/localOfflineStore';
import { getOptionalApiBearerToken } from '@/services/apiAuth';
import { useProject } from '@/contexts/ProjectContext';
import {
  createPersistenceContext,
  handleEventPersistence,
  type PersistenceContext,
} from '../handlers/persistenceHandler';
import { loadChatMessages } from '@/utils/messageLoader';
import {
  uploadChatAttachmentImages,
  type AttachmentImageUploadResult,
} from '@/utils/chatAttachmentStorage';
import { getLocalEngineUrl, getLocalEngineUrlFresh } from '@/services/computerRouter';
import { logPerf, logSSE, logPersist, createPerfTimer } from '@/utils/logger';
import { buildApiKeySourcePayload } from '@/services/apiKeySourceService';
import { collectMachineContext } from '@/api/localEngine';
import { parseAskProbeCommand, runAskUserProbe } from '../devAskUserProbe';
import { useAskUserStore } from '@/stores/useAskUserStore';
import type { AskUserResponse } from '../handlers/localEngine/types';
/**
 * AgentId:
 * - 当前选中的 Agent/Workflow 的 ID
 * - 格式: `workflow:${workflowId}` (来自数据库的 workflow)
 */
export type AgentId = string;

// 支持的事件类型列表
const SUPPORTED_EVENT_TYPES = [
  'text',
  'error',
  'tool_start',
  'tool_delta',
  'tool_end',
  'tool_call',      // 新标准格式：GUI/Office 操作
  'tool_result',    // 工具调用结果（planner 模式）
  'cua_start',
  'cua_delta',
  'cua_update',
  'cua_end',
  'node_start',
  'node_update',
  'node_end',
  'node_complete',   // 后端 AI Run 可能直接下发，与 node_end 等价
  'client_request',
  'cua_request',
  'workflow_complete',
  'workflow_progress',
  'planner_complete',
  // Orchestrator events
  'orchestrator_decision',
  'orchestrator_observation',
  'orchestrator_complete',
  'workflow_started',
  'done',
];

/**
 * 判断是否为支持的事件类型
 */
function isSupportedEvent(event: any): event is StreamEvent {
  return SUPPORTED_EVENT_TYPES.includes(event.type);
}

export interface UseChatOptions {
  /** 每完成一个节点时调用（用于触发左侧文件 explorer 同步/刷新） */
  onNodeEnd?: () => void;
}

export function useChat(options?: UseChatOptions) {
  const onNodeEndRef = useRef(options?.onNodeEnd);
  onNodeEndRef.current = options?.onNodeEnd;

  const { t } = useTranslation();
  const { currentProject } = useProject();
  const { agents, workflowCapabilities } = useChatAgents();
  const agentsRef = useRef(agents);
  useEffect(() => {
    agentsRef.current = agents;
  }, [agents]);

  const [input, setInput] = useState('');
  // 初始为空，等待 agents 加载后自动选择第一个
  const [selectedAgentId, setSelectedAgentId] = useState<AgentId>('');
  const selectedAgentIdRef = useRef<AgentId>(selectedAgentId);
  useEffect(() => {
    selectedAgentIdRef.current = selectedAgentId;
  }, [selectedAgentId]);

  const [chatId, setChatId] = useState<string | null>(null);
  const [chatTitle, setChatTitle] = useState<string | null>(null);
  const [workflowRunId, setWorkflowRunId] = useState<string | null>(null);
  const [workflowRunStatus, setWorkflowRunStatus] = useState<'running' | 'completed' | 'failed' | null>(null);

  const isWorkflowAgent = (agentId: string) => agentId === 'workflow' || agentId.startsWith('workflow:');
  const getWorkflowIdFromAgent = (agentId: string) => {
    // 从 agentId 中提取 workflow_id（用于写 DB 和 /workflow payload）
    // 现在所有 agent 都是 workflow 格式 (workflow:{uuid})
    if (agentId.startsWith('workflow:')) {
      return agentId.slice('workflow:'.length) || null;
    }
    // 兼容旧格式，尝试从 agents 列表中查找（用 ref 避免 await 后闭包仍是旧列表）
    const agent = agentsRef.current.find((a) => a.id === agentId);
    if (agent?.workflow_id) {
      return agent.workflow_id;
    }
    // 如果找不到，返回 null（后端会处理）
    return null;
  };

  // 自动选择第一个可用的 agent（当 selectedAgentId 为空或无效时）
  useEffect(() => {
    if (agents.length > 0 && (!selectedAgentId || !agents.find((a) => a.id === selectedAgentId))) {
      setSelectedAgentId(agents[0].id as AgentId);
    }
  }, [agents, selectedAgentId]);

  // ==================== Local persistence (Electron app-config preferred) ====================
  // We persist chat_id per (project_id, agentId) so switching agent/workflow can restore the last chat.
  const getChatStorageKey = useCallback(() => {
    const pid = currentProject?.id;
    if (!pid) return null;
    return `${pid}::${selectedAgentId}`;
  }, [currentProject?.id, selectedAgentId]);

  const loadPersistedChatId = useCallback(async (): Promise<string | null> => {
    const key = getChatStorageKey();
    if (!key) return null;

    // Electron: app-config.json
    try {
      const states = await (window.electron?.getAppConfig?.('projectStates') as Promise<any>);
      const persisted = states?.[key]?.chatId;
      if (persisted && typeof persisted === 'string') return persisted;
    } catch {
      // ignore
    }

    // Browser fallback
    try {
      const raw = localStorage.getItem(`useit.chat.${key}`);
      return raw || null;
    } catch {
      return null;
    }
  }, [getChatStorageKey]);

  const loadPersistedWorkflowRun = useCallback(async (): Promise<{ id: string | null; status: any } | null> => {
    const key = getChatStorageKey();
    if (!key) return null;

    // Electron: app-config.json
    try {
      const states = await (window.electron?.getAppConfig?.('projectStates') as Promise<any>);
      const persisted = states?.[key]?.workflowRunId;
      const status = states?.[key]?.workflowRunStatus;
      return { id: typeof persisted === 'string' ? persisted : null, status };
    } catch {
      // ignore
    }

    // Browser fallback
    try {
      const raw = localStorage.getItem(`useit.workflowRun.${key}`);
      const rawStatus = localStorage.getItem(`useit.workflowRunStatus.${key}`);
      return { id: raw || null, status: rawStatus };
    } catch {
      return null;
    }
  }, [getChatStorageKey]);

  const persistChatId = useCallback(
    async (value: string | null) => {
      const key = getChatStorageKey();
      if (!key) return;

      // Electron: app-config.json
      try {
        const states = (await window.electron?.getAppConfig?.('projectStates')) || {};
        const next = { ...(states || {}) };
        next[key] = { ...(next[key] || {}), chatId: value, updatedAt: Date.now() };
        await window.electron?.setAppConfig?.({ projectStates: next });
      } catch {
        // ignore
      }

      // Browser fallback
      try {
        if (value) localStorage.setItem(`useit.chat.${key}`, value);
        else localStorage.removeItem(`useit.chat.${key}`);
      } catch {
        // ignore
      }
    },
    [getChatStorageKey]
  );

  const persistWorkflowRun = useCallback(
    async (value: { id: string | null; status: string | null }) => {
      const key = getChatStorageKey();
      if (!key) return;

      // Electron: app-config.json
      try {
        const states = (await window.electron?.getAppConfig?.('projectStates')) || {};
        const next = { ...(states || {}) };
        next[key] = {
          ...(next[key] || {}),
          workflowRunId: value.id,
          workflowRunStatus: value.status,
          updatedAt: Date.now(),
        };
        await window.electron?.setAppConfig?.({ projectStates: next });
      } catch {
        // ignore
      }

      // Browser fallback
      try {
        if (value.id) localStorage.setItem(`useit.workflowRun.${key}`, value.id);
        else localStorage.removeItem(`useit.workflowRun.${key}`);
        if (value.status) localStorage.setItem(`useit.workflowRunStatus.${key}`, value.status);
        else localStorage.removeItem(`useit.workflowRunStatus.${key}`);
      } catch {
        // ignore
      }
    },
    [getChatStorageKey]
  );

  // 注意：不再自动恢复 chatId
  // 切换 mode 时，应该开始新对话，而不是恢复旧对话
  // 只有用户明确从 Chat History 选择时才加载历史消息

  const ensureSupabaseProject = useCallback(async () => {
    if (!currentProject) {
      logPersist('❌ ensureLocalProject: No project selected');
      throw new Error('No project selected');
    }
    logPersist('✅ 离线模式：使用本机项目 %s', currentProject.id);
    return { userId: LOCAL_OFFLINE_USER_ID };
  }, [currentProject]);

  const ensureChat = useCallback(
    async (firstUserMessage: string) => {
      if (chatId) return chatId;
      if (!currentProject) throw new Error('No project selected');

      await ensureSupabaseProject();

      const title = firstUserMessage.trim().slice(0, 50) || 'New Chat';
      const newChatId = generateUuid();
      const t = new Date().toISOString();
      offlineInsertChat({
        id: newChatId,
        project_id: currentProject.id,
        title,
        created_at: t,
        updated_at: t,
      });
      setChatId(newChatId);
      setChatTitle(title);
      persistChatId(newChatId);
      return newChatId;
    },
    [chatId, currentProject, ensureSupabaseProject, persistChatId]
  );

  const generateUuid = () => {
    const uuid = (globalThis as any).crypto?.randomUUID?.();
    if (!uuid) {
      throw new Error('crypto.randomUUID is not available; cannot create workflow/message ids');
    }
    return uuid as string;
  };

  const loadLatestRunForChat = useCallback(async (cid: string) => {
    const rows = offlineListRunsForChat(cid);
    return (rows.length > 0 ? rows[0] : null) as any;
  }, []);

  const markRunEnded = useCallback(
    async (runId: string, status: 'failed' | 'completed', summary?: any) => {
      try {
        offlineUpdateWorkflowRun(runId, {
          status,
          completed_at: new Date().toISOString(),
          result_summary: summary || null,
        });
      } catch (e) {
        // ignore workflow status update errors
      }
    },
    []
  );

  const ensureWorkflowRun = useCallback(
    async (cid: string, selectedWorkflowId: string, triggerMessageId: string) => {
      const latest = await loadLatestRunForChat(cid);

      if (latest && latest.status === 'running') {
        const latestWorkflowId = latest.workflow_id as string | null;
        if (latestWorkflowId && latestWorkflowId !== selectedWorkflowId) {
          const ok = window.confirm('当前 workflow 未结束，是否新开运行？（将强制结束当前 workflow）');
          if (!ok) {
            return { runId: latest.id as string, reused: true, cancelledNew: true };
          }
          // Force end previous run
          await markRunEnded(latest.id as string, 'failed', {
            cancelled_by_user: true,
            reason: 'user started a new run after switching workflow',
          });
        } else {
          return { runId: latest.id as string, reused: true, cancelledNew: false };
        }
      }

      // Create a new run (status running)
      const runId = generateUuid();
      const runInsert = {
        id: runId,
        project_id: currentProject?.id ?? '',
        chat_id: cid,
        trigger_message_id: triggerMessageId,
        status: 'running',
        workflow_id: selectedWorkflowId,
        started_at: new Date().toISOString(),
        completed_at: null as string | null,
        result_summary: null as unknown | null,
      };
      offlineInsertWorkflowRun(runInsert);
      return { runId, reused: false, cancelledNew: false };
    },
    [currentProject?.id, loadLatestRunForChat, markRunEnded]
  );

  // 初始化消息：根据当前选中的 agent 获取对应的欢迎语
  // 优先从 agents（包含动态 workflow）中查找
  const getInitialMessage = useCallback((agentId: AgentId): Message => {
    const agent = agents.find((a) => a.id === agentId) || agents[0];
    const welcomeMessage = agent?.welcomeMessage || t('chat.defaultWelcome', 'Hello! Please choose an agent to start the conversation.');
    return {
      id: 'welcome',
      role: 'assistant',
      content: welcomeMessage,
      timestamp: Date.now(),
      blocks: [{ type: 'text', content: welcomeMessage }],
    };
  }, [agents, t]);

  const [messages, setMessages] = useState<Message[]>([getInitialMessage('general')]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const processedActionsRef = useRef<Set<string>>(new Set());
  const abortControllerRef = useRef<AbortController | null>(null);

  // 切换 Agent
  const handleAgentChange = useCallback((newAgentId: AgentId) => {
    // Option C: If switching workflow while latest run is still running, prompt user.
    // If user confirms, force-end previous run in Supabase and clear local pointer.
    try {
      const currentWorkflowId = getWorkflowIdFromAgent(selectedAgentId);
      const nextWorkflowId = getWorkflowIdFromAgent(newAgentId);
      const switchingWorkflow = isWorkflowAgent(selectedAgentId) && isWorkflowAgent(newAgentId) && currentWorkflowId && nextWorkflowId && currentWorkflowId !== nextWorkflowId;
      if (switchingWorkflow && workflowRunId && workflowRunStatus === 'running') {
        const ok = window.confirm('当前 workflow 未结束，是否新开运行？（将强制结束当前 workflow）');
        if (!ok) return;
        // Fire and forget; sendMessage will also do a final check before creating a new run.
        markRunEnded(workflowRunId, 'failed', {
          cancelled_by_user: true,
          reason: 'user switched workflow while previous run still running',
        }).catch(() => {});
        setWorkflowRunStatus('failed');
        persistWorkflowRun({ id: workflowRunId, status: 'failed' });
      }
    } catch {
      // ignore prompt errors; do not block agent switch
    }

    setSelectedAgentId(newAgentId);
    
    // 如果当前只有欢迎消息，则更新为新 agent/workflow 的欢迎消息
    setMessages((prev) => {
      const onlyWelcome = prev.length === 1 && prev[0].id === 'welcome';
      if (onlyWelcome) {
        return [getInitialMessage(newAgentId)];
      }
      return prev;
    });
    
    // 如果正在加载，取消当前请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setIsStopping(false);
  }, [selectedAgentId, workflowRunId, workflowRunStatus, markRunEnded, persistWorkflowRun, getInitialMessage]);

  // 停止当前任务
  const handleStop = () => {
    if (abortControllerRef.current) {
      setIsStopping(true);
      abortControllerRef.current.abort();
      abortControllerRef.current = null;

      setMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === 'assistant') {
          const stoppedMessage = `\n\n ${t('workspace.chat.taskStoppedByUser')}`;

          const cancelRunningCards = (blocks: any[]) =>
            blocks.map((block: any) =>
              block.type === 'card' && block.card?.status === 'running'
                ? { ...block, card: { ...block.card, status: 'cancelled' } }
                : block
            );

          if (lastMsg.blocks && lastMsg.blocks.length > 0) {
            const updatedBlocks = cancelRunningCards(lastMsg.blocks);
            const lastBlock = updatedBlocks[updatedBlocks.length - 1];
            if (lastBlock.type === 'text') {
              return prev.map((msg, idx) =>
                idx === prev.length - 1
                  ? {
                      ...msg,
                      blocks: [
                        ...updatedBlocks.slice(0, -1),
                        { ...lastBlock, content: lastBlock.content + stoppedMessage },
                      ],
                    }
                  : msg
              );
            } else {
              return prev.map((msg, idx) =>
                idx === prev.length - 1
                  ? {
                      ...msg,
                      blocks: [...updatedBlocks, { type: 'text', content: stoppedMessage }],
                    }
                  : msg
              );
            }
          }
          // 旧格式
          return prev.map((msg, idx) =>
            idx === prev.length - 1
              ? { ...msg, content: (msg.content || '') + stoppedMessage }
              : msg
          );
        }
        return prev;
      });

      setIsLoading(false);
      setIsStopping(false);
    }
  };

  // 清空消息
  const clearMessages = () => {
    setMessages([]);
    setChatId(null);
    persistChatId(null);
    setWorkflowRunId(null);
    setWorkflowRunStatus(null);
    persistWorkflowRun({ id: null, status: null });
  };

  /**
   * Inline-card answer bridge for `ask_user` (target === 'user').
   *
   * Called by `AskUserCard` (via MessageList) when the user picks an
   * option / submits text / dismisses / timer expires. We:
   *   1. Mutate the `AskUserBlock` in-place inside the message so the
   *      card locks into an 'answered' / 'dismissed' state in history.
   *   2. Resolve the outstanding promise registered by
   *      `handleAskUserCall` — the handler then POSTs the callback to
   *      the orchestrator.
   */
  const settleAskUser = useCallback(
    (toolCallId: string, reply: AskUserResponse) => {
      setMessages((prev) =>
        prev.map((msg) => {
          if (!msg.blocks || msg.blocks.length === 0) return msg;
          let touched = false;
          const blocks = msg.blocks.map((b) => {
            if (b.type !== 'ask_user' || b.toolCallId !== toolCallId) return b;
            if (b.status !== 'pending') return b;
            touched = true;
            return {
              ...b,
              status: (reply.dismissed ? 'dismissed' : 'answered') as
                | 'dismissed'
                | 'answered',
              answer: reply,
            };
          });
          return touched ? { ...msg, blocks } : msg;
        }),
      );
      useAskUserStore.getState().settle(toolCallId, reply);
    },
    [],
  );

  // 附加文件类型
  interface AttachedFileInfo {
    path: string;
    name: string;
    type: 'file' | 'folder';
  }

  // 附加图片类型（发送入口——必须要有 base64，因为这是新粘贴/上传的图片）
  interface AttachedImageInfo {
    id: string;
    name: string;
    base64: string;
    mimeType: string;
    size: number;
  }

  // 发送消息（options.agentId：ChatPanel 在 await onBeforeSend 后调用时传入，避免 setState 尚未同步到 ref）
  const sendMessage = async (
    content: string,
    computerName?: string,
    attachedFiles?: AttachedFileInfo[],
    attachedImages?: AttachedImageInfo[],
    options?: { agentId?: AgentId },
  ) => {
    if (options?.agentId) {
      selectedAgentIdRef.current = options.agentId;
    }
    if (!content.trim() && (!attachedFiles || attachedFiles.length === 0) && (!attachedImages || attachedImages.length === 0)) return;

    // ==================== 本地自测入口：/ask [confirm|choose|multi|input|timeout] ====================
    // 纯前端自测 ask_user 卡片，不调后端。插入一条用户消息 + 一条空的 assistant 消息，
    // 然后把 ask_user block 挂到那条 assistant 消息上。
    const probeKind = parseAskProbeCommand(content);
    if (probeKind) {
      const userMsgId = Date.now().toString();
      const probeBotId = userMsgId + '-ask';
      setMessages((prev) => {
        const withoutWelcome = prev.filter((m) => m.id !== 'welcome');
        return [
          ...withoutWelcome,
          {
            id: userMsgId,
            role: 'user',
            content,
            timestamp: Date.now(),
            blocks: [{ type: 'text', content }],
          },
          {
            id: probeBotId,
            role: 'assistant',
            timestamp: Date.now() + 1,
            blocks: [],
          },
        ];
      });
      setInput('');
      runAskUserProbe(probeKind, { setMessages, botMessageId: probeBotId }).catch((err) => {
        // eslint-disable-next-line no-console
        console.error('[AskUserProbe] failed:', err);
      });
      return;
    }

    if (!currentProject) {
      const errorMessage: Message = {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: '未选择 Project，无法创建对话。请先选择/创建一个 Project。',
        timestamp: Date.now(),
        blocks: [{ type: 'text', content: '未选择 Project，无法创建对话。请先选择/创建一个 Project。' }],
      };
      setMessages((prev) => [...prev, errorMessage]);
      return;
    }

    processedActionsRef.current.clear();
    abortControllerRef.current = new AbortController();

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now(),
      blocks: [{ type: 'text', content }],
      attachedFiles: attachedFiles && attachedFiles.length > 0 
        ? attachedFiles.map((f, idx) => ({ ...f, id: `file-${Date.now()}-${idx}` }))
        : undefined,
      attachedImages: attachedImages && attachedImages.length > 0
        ? [...attachedImages]
        : undefined,
    };

    // 添加用户消息时，移除欢迎消息
    setMessages((prev) => {
      const withoutWelcome = prev.filter((msg) => msg.id !== 'welcome');
      return [...withoutWelcome, userMessage];
    });
    setInput('');
    setIsLoading(true);

    // Supabase: 确保 chat_id（新对话就创建一条 chats 记录）
    let effectiveChatId: string | null = null;
    let effectiveUserId: string | null = null;
    let effectiveWorkflowRunId: string | null = null;
    let effectiveTriggerMessageId: string | null = null;
    try {
      logPersist('🔄 开始持久化流程...');
      const { userId } = await ensureSupabaseProject();
      effectiveUserId = userId;
      logPersist('✅ ensureSupabaseProject 成功, userId: %s', userId);
      
      effectiveChatId = await ensureChat(userMessage.content || content);
      logPersist('✅ ensureChat 成功, chatId: %s', effectiveChatId);

      // 写入用户消息到 messages 表（最小实现：仅存 text + metadata）
      // 使用 ref：sendMessage 内若有 await，闭包里的 selectedAgentId 可能是旧值
      const agentIdForSend = selectedAgentIdRef.current;
      const workflowId = getWorkflowIdFromAgent(agentIdForSend);

      // 1) 先插入用户消息，拿到真实 message_id（用于 workflow_runs.trigger_message_id 外键）
      const msgId = generateUuid();
      effectiveTriggerMessageId = msgId;
      logPersist('📝 插入用户消息, msgId: %s', msgId);

      // Upload attached images to Supabase Storage BEFORE persisting
      // the message, so `metadata.attached_images` only references
      // `{ storage_path, url }` — never raw base64 — which keeps the
      // `messages` row small and makes re-signing trivial on reload.
      //
      // Upload is per-image: each attachment independently either
      // ends up as a storage ref or, if its upload fails, is
      // persisted inline as base64 so chat history & the "redo"
      // backfill path still work. Mixed success is expected and
      // handled — one bad upload does not poison the rest.
      let uploadResults: AttachmentImageUploadResult[] = [];
      if (attachedImages && attachedImages.length > 0 && userId) {
        try {
          uploadResults = await uploadChatAttachmentImages(
            attachedImages.map((img) => ({
              name: img.name,
              base64: img.base64,
              mimeType: img.mimeType,
              size: img.size,
            })),
            userId,
            effectiveChatId,
            msgId,
          );
          const okCount = uploadResults.filter((r) => r.ok).length;
          const failCount = uploadResults.length - okCount;
          if (okCount > 0) {
            logPersist(
              '✅ 附件图片上传 Storage 成功 %d/%d 张',
              okCount,
              uploadResults.length,
            );
          }
          if (failCount > 0) {
            const errors = uploadResults
              .map((r, i) => (r.ok ? null : `[${i}] ${r.error.message}`))
              .filter((s): s is string => s !== null);
            logPersist(
              '⚠️ 附件图片部分上传失败 %d/%d，失败项降级为 base64 内联。错误: %O',
              failCount,
              uploadResults.length,
              errors,
            );
          }
        } catch (uploadErr) {
          // `uploadChatAttachmentImages` uses `Promise.allSettled`
          // internally, so it normally does not throw. This catch
          // handles truly unexpected sync/infra failures (e.g.
          // transient attachment pipeline error) — in that
          // case we degrade every image to base64.
          uploadResults = [];
          logPersist(
            '⚠️ 附件图片上传整体失败，全部降级为 base64 内联: %O',
            uploadErr,
          );
        }
      }

      const persistedAttachedImages = attachedImages && attachedImages.length > 0
        ? attachedImages.map((img, idx) => {
            const result = uploadResults[idx];
            if (result?.ok) {
              const uploaded = result.image;
              return {
                id: img.id,
                name: img.name,
                mime_type: uploaded.mimeType,
                size: uploaded.size,
                storage_path: uploaded.storagePath,
                url: uploaded.url,
                url_expires_at: uploaded.expiresAt,
              };
            }
            // Fallback: keep legacy base64 persistence so the "redo"
            // backfill path still works when Storage is unavailable
            // or this specific image failed to upload.
            return {
              id: img.id,
              name: img.name,
              mime_type: img.mimeType,
              size: img.size,
              base64: img.base64,
            };
          })
        : [];
      const persistedAttachedFiles = attachedFiles && attachedFiles.length > 0
        ? attachedFiles.map((f) => ({
            path: f.path,
            name: f.name,
            type: f.type,
          }))
        : [];

      // Once uploaded, the in-memory `userMessage.attachedImages` should
      // point at the signed URL so the UI doesn't hold on to the large
      // base64 string longer than necessary, and so any later re-render
      // (before Supabase is re-queried) uses the same source the DB has.
      //
      // Only overwrite images whose upload actually succeeded — for
      // failed indices we keep the original in-memory entry (which
      // still has its base64 payload) so the UI can render them.
      if (uploadResults.some((r) => r.ok)) {
        setMessages((prev) => prev.map((m) => {
          if (m.id !== userMessage.id) return m;
          const mergedImages = (m.attachedImages ?? []).map((img, idx) => {
            const result = uploadResults[idx];
            if (!result?.ok) return img;
            const up = result.image;
            return {
              ...img,
              url: up.url,
              storagePath: up.storagePath,
              urlExpiresAt: up.expiresAt,
              // Keep base64 around only for this session — it lets
              // `ensureFreshSignedUrl` fall back to inline render if
              // the signed URL somehow fails to load.
            };
          });
          return { ...m, attachedImages: mergedImages };
        }));
      }

      offlineInsertMessage({
        id: msgId,
        chat_id: effectiveChatId,
        workflow_run_id: null,
        role: 'user',
        type: 'text',
        content: userMessage.content || content,
        metadata: {
          agent_id: agentIdForSend,
          project_id: currentProject.id,
          workflow_id: workflowId,
          attached_images: persistedAttachedImages,
          attached_files: persistedAttachedFiles,
        },
        created_at: new Date().toISOString(),
      });
      logPersist('✅ 用户消息插入成功');

      // 2) 如果是 workflow agent：创建/复用 workflow_run（现在 message 已存在，外键不会失败）
      if (isWorkflowAgent(agentIdForSend) && effectiveChatId && workflowId) {
        const runRes = await ensureWorkflowRun(effectiveChatId, workflowId, msgId);
        effectiveWorkflowRunId = runRes.runId;
        setWorkflowRunId(effectiveWorkflowRunId);
        setWorkflowRunStatus('running');
        persistWorkflowRun({ id: effectiveWorkflowRunId, status: 'running' });
        logPersist('✅ workflow_run 创建/复用成功, runId: %s', effectiveWorkflowRunId);

        // 3) 回填用户消息的 workflow_run_id
        offlineUpdateMessage(msgId, { workflow_run_id: effectiveWorkflowRunId });
      }
      logPersist('✅ 用户消息持久化完成');
    } catch (e) {
      logPersist('❌ 持久化流程失败: %O', e);
      // 不阻塞主流程：后端请求仍可继续
    }

    const botMessageId = (Date.now() + 1).toString();
    
    // 创建空的 assistant 消息（V2 格式）
    const initialBotMessage: Message = {
      id: botMessageId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      blocks: [],
    };
    setMessages((prev) => [...prev, initialBotMessage]);

    try {
      // All requests go through the orchestrator which decides whether
      // to run the selected workflow, perform app actions, or respond.
      const endpoint = `${API_URL}/api/v1/agent`;

      const agentIdForRequest = selectedAgentIdRef.current;
      const workflowId = getWorkflowIdFromAgent(agentIdForRequest);
      const body: Record<string, any> = {
        message: userMessage.content,
        project_id: currentProject.id,
        // 用户机器上项目根目录的绝对路径（Windows 下形如 `D:\Workspace\useit-studio`）。
        // backend planner 用它把 attached_files[].path（相对路径）拼成绝对路径再写进 prompt，
        // 否则 LLM 没办法知道 `workspace/test.pptx` 在用户磁盘上的真实位置，
        // 只能瞎猜（典型的错猜：`C:\Users\Administrator\Desktop\test.pptx`），
        // 然后 ppt_document open 拿到这个伪路径直接 `file not found` 失败。
        project_path: currentProject.path,
        workflow_id: workflowId,
        chat_id: effectiveChatId,
        workflow_run_id: effectiveWorkflowRunId,
        user_id: effectiveUserId,
        // inserted the current user message before this POST, so tell
        // the backend to exclude it from the loaded history.
        trigger_message_id: effectiveTriggerMessageId,
        app_capabilities: appAction.getActionSchemas(),
        workflow_capabilities: workflowCapabilities,
      };

      // Add api_key_source if user has opted for own keys
      const apiKeySourcePayload = buildApiKeySourcePayload();
      if (apiKeySourcePayload) {
        body.api_key_source = apiKeySourcePayload;
      }
      
      // 如果有附加文件，转换为相对路径后添加到请求体
      //
      // 注意：Electron 下 currentProject.path 在 Windows 上通常是反斜杠 (C:\\...)，
      // 而 f.path（来自 file tree/拖拽等）常常是正斜杠 (C:/.../workspace/...)。
      // 直接 startsWith 会因分隔符不一致返回 false，导致把本地绝对路径
      // 当成相对路径发给后端，最终拼出非法 S3 key。
      // 这里统一归一化为正斜杠、并做大小写不敏感比较（Windows 路径大小写不敏感）。
      if (attachedFiles && attachedFiles.length > 0) {
        const toForward = (p: string) => (p || '').replace(/\\/g, '/');
        const rawProjectPath = toForward(currentProject.path).replace(/\/+$/, '');
        const cmpProjectPath = rawProjectPath.toLowerCase();

        body.attached_files = attachedFiles.map(f => {
          const rawFilePath = toForward(f.path);
          let relativePath = rawFilePath;

          if (rawProjectPath && rawFilePath.toLowerCase().startsWith(cmpProjectPath)) {
            relativePath = rawFilePath.slice(rawProjectPath.length).replace(/^\/+/, '');
          }

          return { path: relativePath, name: f.name, type: f.type };
        });
      }

      // 如果有附加图片，以 base64 数据发送
      if (attachedImages && attachedImages.length > 0) {
        body.attached_images = attachedImages.map(img => ({
          name: img.name,
          base64: img.base64,
          mime_type: img.mimeType,
        }));
      }

      // 机器环境感知：并发拉 local-engine 的 /system/* 聚合进 uia_data。
      // 无论采集是否成功，都强制把 uia_data 塞进 body（失败时带 _error 字段），
      // 这样后端从 incoming_request.json 可以明确区分「前端漏发」vs「前端发了但采集失败」。
      const uiaCanary = {
        _frontend_ts: new Date().toISOString(),
        _frontend_build: '2026-04-21-canary-1',
      };
      try {
        const t0 = performance.now();
        const machineCtx = await collectMachineContext();
        const ms = Math.round(performance.now() - t0);
        const keys = Object.keys(machineCtx);
        // eslint-disable-next-line no-console
        console.log('[MachineContext] 摘要', {
          elapsed_ms: ms,
          keys,
          active_window: machineCtx.active_window ?? '(none)',
          open_windows_len: machineCtx.open_windows?.length ?? 0,
          installed_apps_len: machineCtx.installed_apps?.length ?? 0,
        });
        if (machineCtx.open_windows) {
          // eslint-disable-next-line no-console
          console.log('[MachineContext] open_windows:\n' + machineCtx.open_windows);
        }
        if (machineCtx.installed_apps) {
          // eslint-disable-next-line no-console
          console.log(
            '[MachineContext] installed_apps (前 30 条):\n' +
              machineCtx.installed_apps.split('\n').slice(0, 30).join('\n'),
          );
        }
        body.uia_data = {
          ...uiaCanary,
          _keys_collected: keys,
          ...machineCtx,
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        // eslint-disable-next-line no-console
        console.warn('[MachineContext] collect 失败', err);
        body.uia_data = {
          ...uiaCanary,
          _error: `collectMachineContext threw: ${msg}`,
        };
      }

      // 🔍 发送前快照：验证 uia_data 真的进了要发出去的 body
      {
        const serialized = JSON.stringify(body);
        // eslint-disable-next-line no-console
        console.log('[AgentRequest] about to POST', {
          endpoint,
          has_uia_data: 'uia_data' in body,
          uia_data_keys: body.uia_data ? Object.keys(body.uia_data) : null,
          uia_data_json_bytes: body.uia_data
            ? JSON.stringify(body.uia_data).length
            : 0,
          total_body_bytes: serialized.length,
          body_top_keys: Object.keys(body),
        });
      }

      // 🔍 性能追踪：SSE 请求开始
      const sseTimer = createPerfTimer('SSE_REQUEST');
      
      // 可选：若配置了 VITE_API_BEARER_TOKEN，则附加到网关请求（非 Supabase）
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const token = getOptionalApiBearerToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const finalBodyString = JSON.stringify(body);
      {
        const uiaOffset = finalBodyString.indexOf('"uia_data"');
        // eslint-disable-next-line no-console
        console.log('[AgentRequest] final body just before fetch()', {
          endpoint,
          bytes: finalBodyString.length,
          contains_uia_data: uiaOffset !== -1,
          uia_data_offset: uiaOffset,
          uia_data_preview:
            uiaOffset !== -1 ? finalBodyString.slice(uiaOffset, uiaOffset + 300) : null,
        });
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: finalBodyString,
        signal: abortControllerRef.current.signal,
      });

      sseTimer.checkpoint('fetch() 返回 200');

      if (!response.ok) throw new Error(`API Error: ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      sseTimer.checkpoint('reader 创建完成');

      const decoder = new TextDecoder();
      let buffer = '';
      let assistantText = '';
      let isFirstRead = true;
      let isFirstEvent = true;
      let firstClientRequestTime: number | null = null;
      
      // 创建持久化上下文（如果有必要的 IDs）
      let persistenceCtx: PersistenceContext | undefined;
      if (effectiveUserId && effectiveChatId && effectiveWorkflowRunId) {
        persistenceCtx = createPersistenceContext(
          effectiveUserId,
          effectiveChatId,
          effectiveWorkflowRunId
        );
      }

      // 获取目标电脑的 Local Engine URL
      const targetLocalEngineUrl = await getLocalEngineUrl(computerName);

      while (true) {
        const { done, value } = await reader.read();
        
        // 🔍 性能追踪：首次 read() 完成
        if (isFirstRead) {
          sseTimer.checkpoint('首次 reader.read() 完成');
          isFirstRead = false;
        }
        
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            
            // 🔍 性能追踪：首个事件
            if (isFirstEvent) {
              sseTimer.checkpoint(`首个事件到达: ${event.type}`);
              isFirstEvent = false;
            }
            
            logSSE('收到事件: %s %O', event.type, event);

            // 处理器上下文
            // 注意：localEngineUrl 是初始值，但 VM IP 可能变化
            // 执行命令时应使用 getLocalEngineUrlFresh 获取最新 URL
            const ctx: CommandHandlerContext = {
              botMessageId,
              setMessages,
              localEngineUrl: targetLocalEngineUrl,
              computerName: computerName,
              getLocalEngineUrlFresh: () => getLocalEngineUrlFresh(computerName),
              projectPath: currentProject?.path,  // 项目路径，用于 snapshot/screenshot 附带项目文件列表
              userId: effectiveUserId || undefined,
              chatId: effectiveChatId || undefined,
              workflowRunId: effectiveWorkflowRunId || undefined,
            };

            // ==================== 事件处理 ====================
            const isSupported = isSupportedEvent(event);
            logSSE('事件类型: %s, 是否支持: %s', event.type, isSupported);
            if (isSupported) {
              // Orchestrator text event: has `content` string (not `delta`)
              if (event.type === 'text' && typeof (event as any).content === 'string' && !(event as any).delta) {
                assistantText += (event as any).content;
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== botMessageId) return msg;
                    return processEvent({ ...event, type: 'text', delta: (event as any).content } as any, msg);
                  }),
                );
                continue;
              }

              // Orchestrator decision / observation — log only, no UI change
              if (event.type === 'orchestrator_decision' || event.type === 'orchestrator_observation') {
                logSSE('Orchestrator: %s %O', event.type, (event as any).content);
                continue;
              }

              // Orchestrator / stream done signal
              if (event.type === 'done' || event.type === 'orchestrator_complete') {
                logSSE('Orchestrator done');
                continue;
              }

              // workflow_started — the orchestrator decided to run a workflow
              if (event.type === 'workflow_started') {
                logSSE('Orchestrator: workflow started %O', (event as any).content);
                continue;
              }

              // 累积文本内容
              if (event.type === 'text' && typeof (event as any).delta === 'string') {
                assistantText += (event as any).delta;
              }
              
              // 处理 client_request 事件（旧格式，保留兼容）
              if (event.type === 'client_request') {
                // 🔍 性能追踪：首个 client_request
                if (!firstClientRequestTime) {
                  firstClientRequestTime = sseTimer.elapsed();
                  logPerf('📨 首个 client_request 到达 [距请求开始: %sms] requestId: %s', 
                    firstClientRequestTime.toFixed(0), event.requestId);
                }
                handleClientRequest(event, ctx).catch((err) => {
                  console.error('[Chat] handleClientRequest error:', err);
                });
                continue;
              }

              // 处理 tool_call 事件（新标准格式）
              // 根据 target 字段路由到 GUI 或 Office handler
              if (event.type === 'tool_call' && isToolCallEvent(event)) {
                logPerf('🔧 收到 tool_call: %s -> %s', event.target, event.name);
                handleToolCall(event as ToolCallEvent, ctx).catch((err) => {
                  console.error('[Chat] handleToolCall error:', err);
                });
                continue;
              }

              // 处理其他事件（纯函数）
              // 更新 UI
              setMessages((prev) => {
                const newMessages = prev.map((msg) => {
                  if (msg.id !== botMessageId) return msg;
                  const updated = processEvent(event as StreamEvent, msg);
                  return updated;
                });
                return newMessages;
              });
              
              // 持久化到数据库（异步，不阻塞 UI）
              handleEventPersistence(persistenceCtx, event).catch(() => {});

              // 每完成一个节点时触发回调（如左侧文件 explorer 同步/刷新）
              // 后端可能下发 node_end 或 node_complete，均视为节点完成
              if (event.type === 'node_end' || event.type === 'node_complete') {
                try {
                  onNodeEndRef.current?.();
                } catch (err) {
                  console.warn('[useChat] onNodeEnd callback error:', err);
                }
              }

              // 收到 workflow_complete 事件时，立即结束加载状态
              if (event.type === 'workflow_complete') {
                sseTimer.end('workflow_complete 收到');
                setIsLoading(false);
                // 兜底：工作流结束后再触发一次同步，确保最后产出的文件被下载
                try {
                  onNodeEndRef.current?.();
                } catch (err) {
                  console.warn('[useChat] onNodeEnd callback on workflow_complete error:', err);
                }
              }

              continue;
            }
            
            // ==================== 其他事件（工作流特定）====================
            // cua_step_start, cua_step_action 等事件也需要持久化
            if (event.type === 'cua_step_start' || event.type === 'cua_step_action') {
              handleEventPersistence(persistenceCtx, event).catch(() => {});
            }
            
            // 项目信息等透传事件，不需要处理
            if (event.type === 'project_info') {
              continue;
            }
          } catch (e) {
            // ignore parse errors
          }
        }
      }

      // Supabase: 保存 assistant 最终消息（包含截图）
      logPersist('🔄 准备保存 assistant 消息... chatId=%s, userId=%s, textLen=%d',
        effectiveChatId, effectiveUserId, assistantText.length);
      try {
        if (effectiveChatId && effectiveUserId) {
          const workflowId = getWorkflowIdFromAgent(selectedAgentIdRef.current);
          
          // 使用 Promise 从最新的 state 中获取 screenshots 和 blocks
          // 这样可以避免闭包问题，确保获取到最新的 messages
          const { screenshots, blocks } = await new Promise<{ screenshots: string[], blocks: any[] }>((resolve) => {
            setMessages((currentMessages) => {
              const currentMessage = currentMessages.find(m => m.id === botMessageId);
              resolve({
                screenshots: currentMessage?.screenshots || [],
                blocks: currentMessage?.blocks || [],
              });
              return currentMessages; // 不修改 state，只是读取
            });
          });
          
          logPersist('📊 获取到消息内容: blocks=%d, screenshots=%d', blocks.length, screenshots.length);
          
          // 准备 metadata - 保存完整的 blocks 数组
          const metadata: any = {
            agent_id: selectedAgentIdRef.current,
            project_id: currentProject.id,
            workflow_id: workflowId,
            // 如果有 blocks，保存 blocks；否则保存纯文本作为 fallback
            blocks: blocks.length > 0 ? blocks : [{ type: 'text', content: assistantText }],
          };
          
          // 如果有截图，上传到 Supabase Storage
          if (screenshots.length > 0) {
            logPersist('📸 开始上传截图... count=%d', screenshots.length);
            try {
              const { uploadScreenshots } = await import('@/utils/screenshotStorage');
              const uploadResults = await uploadScreenshots(
                screenshots,
                effectiveUserId,      // 用户 ID，用于权限隔离
                effectiveChatId,
                botMessageId
              );
              
              // 保存截图 URL（签名 URL）和路径到 metadata
              metadata.screenshot_urls = uploadResults.map(r => r.url);
              metadata.screenshot_paths = uploadResults.map(r => r.path);
              metadata.screenshot_expires_at = uploadResults.map(r => r.expiresAt);
              metadata.screenshot_count = uploadResults.length;
              logPersist('✅ 截图上传成功: %d 张', uploadResults.length);
            } catch (uploadError) {
              logPersist('❌ 截图上传失败: %O', uploadError);
              // 上传失败不阻塞消息保存，但记录错误
              metadata.screenshot_upload_error = String(uploadError);
            }
          }
          
          logPersist('📝 插入 assistant 消息到本地存储...');
          const assistantMsgId = generateUuid();
          offlineInsertMessage({
            id: assistantMsgId,
            chat_id: effectiveChatId,
            workflow_run_id: effectiveWorkflowRunId,
            role: 'assistant',
            type: 'text',
            content: assistantText,
            metadata,
            created_at: new Date().toISOString(),
          });
          logPersist('✅ assistant 消息保存成功');
        } else {
          logPersist('⚠️ 跳过 assistant 消息保存 - 缺少必要 ID: chatId=%s, userId=%s',
            effectiveChatId, effectiveUserId);
        }
      } catch (e) {
        logPersist('❌ assistant 消息保存异常: %O', e);
      }

      // Mark run completed (serial, non-parallel assumption)
      if (effectiveWorkflowRunId) {
        await markRunEnded(effectiveWorkflowRunId, 'completed', { ok: true });
        setWorkflowRunStatus('completed');
        persistWorkflowRun({ id: effectiveWorkflowRunId, status: 'completed' });
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        if (effectiveWorkflowRunId) {
          await markRunEnded(effectiveWorkflowRunId, 'failed', { cancelled_by_user: true });
          setWorkflowRunStatus('failed');
          persistWorkflowRun({ id: effectiveWorkflowRunId, status: 'failed' });
        }
      } else {
        if (effectiveWorkflowRunId) {
          await markRunEnded(effectiveWorkflowRunId, 'failed', { error: String(error) });
          setWorkflowRunStatus('failed');
          persistWorkflowRun({ id: effectiveWorkflowRunId, status: 'failed' });
        }
        const errorMessage: Message = {
          id: (Date.now() + 2).toString(),
          role: 'assistant',
          content: error + ' Unable to connect to the backend. The server may be unavailable.',
          timestamp: Date.now(),
          blocks: [
            {
              type: 'text',
              content: error + ' Unable to connect to the backend. The server may be unavailable.',
            },
          ],
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  /**
   * 切换到指定的聊天（从 Chat History 选择时调用）
   */
  const switchToChat = useCallback(async (targetChatId: string, targetTitle?: string) => {
    if (targetChatId === chatId) {
      return;
    }
    setIsLoadingHistory(true);
    
    try {
      // 加载 chat 信息（包括 title）
      if (!targetTitle) {
        const chatRow = offlineGetChat(targetChatId);
        targetTitle = chatRow?.title || 'Chat';
      }
      
      // 加载历史消息
      const historyMessages = await loadChatMessages({ chatId: targetChatId, limit: 100 });
      
      // 更新状态
      setChatId(targetChatId);
      setChatTitle(targetTitle || null);
      persistChatId(targetChatId);
      
      if (historyMessages.length > 0) {
        const welcomeMessage = getInitialMessage(selectedAgentId);
        setMessages([welcomeMessage, ...historyMessages]);
      } else {
        setMessages([getInitialMessage(selectedAgentId)]);
      }
      
      // 重置 workflow 状态
      setWorkflowRunId(null);
      setWorkflowRunStatus(null);
      persistWorkflowRun({ id: null, status: null });
    } catch (error) {
      // 加载失败时，仍然切换到该 chat，但显示空消息
      setChatId(targetChatId);
      setChatTitle(targetTitle || 'Chat');
      setMessages([getInitialMessage(selectedAgentId)]);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [chatId, selectedAgentId, persistChatId, persistWorkflowRun, getInitialMessage]);

  /**
   * 开始新对话
   */
  const startNewChat = useCallback(() => {
    
    // 重置 chatId 和 title，下次发消息时会自动创建新的
    setChatId(null);
    setChatTitle(null);
    persistChatId(null);
    
    // 清空消息
    setMessages([getInitialMessage(selectedAgentId)]);
    
    // 重置 workflow 状态
    setWorkflowRunId(null);
    setWorkflowRunStatus(null);
    persistWorkflowRun({ id: null, status: null });
  }, [selectedAgentId, persistChatId, persistWorkflowRun, getInitialMessage]);

  return {
    input,
    setInput,
    messages,
    setMessages,
    isLoading,
    setIsLoading,
    isLoadingHistory,
    isStopping,
    selectedAgentId,
    setSelectedAgentId: handleAgentChange,
    sendMessage,
    handleStop,
    clearMessages,
    chatId,
    chatTitle,
    switchToChat,
    startNewChat,
    settleAskUser,
  };
}
