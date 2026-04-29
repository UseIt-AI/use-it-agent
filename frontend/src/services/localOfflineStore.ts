/**
 * 离线优先：聊天 / 工作流运行 / 节点动作等全部落在浏览器 localStorage，
 * 不依赖 Supabase 或任何云端数据库。
 */
import type { Workflow, WorkflowPublication } from '@/features/workflow/types';
import type { RunNode, NodeAction } from '@/utils/workflowRunTypes';

export const LOCAL_OFFLINE_USER_ID = 'local-user';

const STORAGE_KEY = 'useit.offline.bundle.v1';

export interface OfflineChatRow {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface OfflineMessageRow {
  id: string;
  chat_id: string;
  workflow_run_id: string | null;
  role: string;
  type: string;
  content: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface OfflineWorkflowRunRow {
  id: string;
  project_id: string;
  chat_id: string;
  trigger_message_id: string | null;
  status: string;
  workflow_id: string | null;
  started_at: string;
  completed_at: string | null;
  result_summary: unknown | null;
}

interface OfflineBundle {
  workflows: Record<string, Workflow>;
  publications: Record<string, WorkflowPublication>;
  chats: OfflineChatRow[];
  messages: OfflineMessageRow[];
  workflowRuns: OfflineWorkflowRunRow[];
  runNodes: RunNode[];
  nodeActions: NodeAction[];
}

function emptyBundle(): OfflineBundle {
  return {
    workflows: {},
    publications: {},
    chats: [],
    messages: [],
    workflowRuns: [],
    runNodes: [],
    nodeActions: [],
  };
}

function loadBundle(): OfflineBundle {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyBundle();
    const parsed = JSON.parse(raw) as OfflineBundle;
    return {
      ...emptyBundle(),
      ...parsed,
      workflows: parsed.workflows || {},
      publications: parsed.publications || {},
      chats: Array.isArray(parsed.chats) ? parsed.chats : [],
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      workflowRuns: Array.isArray(parsed.workflowRuns) ? parsed.workflowRuns : [],
      runNodes: Array.isArray(parsed.runNodes) ? parsed.runNodes : [],
      nodeActions: Array.isArray(parsed.nodeActions) ? parsed.nodeActions : [],
    };
  } catch {
    return emptyBundle();
  }
}

function saveBundle(b: OfflineBundle): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(b));
  } catch (e) {
    console.warn('[localOfflineStore] save failed (quota?):', e);
  }
}

function mutate(fn: (b: OfflineBundle) => void): void {
  const b = loadBundle();
  fn(b);
  saveBundle(b);
}

// --- Workflows ---

export function offlineListWorkflowsForOwner(ownerId: string): Workflow[] {
  const b = loadBundle();
  return Object.values(b.workflows).filter((w) => w.owner_id === ownerId);
}

export function offlineGetWorkflow(id: string): Workflow | undefined {
  return loadBundle().workflows[id];
}

export function offlinePutWorkflow(w: Workflow): void {
  mutate((b) => {
    b.workflows[w.id] = w;
  });
}

export function offlineDeleteWorkflow(id: string): void {
  mutate((b) => {
    delete b.workflows[id];
    delete b.publications[id];
  });
}

export function offlineGetPublication(workflowId: string): WorkflowPublication | undefined {
  return loadBundle().publications[workflowId];
}

export function offlinePutPublication(pub: WorkflowPublication): void {
  mutate((b) => {
    b.publications[pub.workflow_id] = pub;
  });
}

// --- Chats ---

export function offlineListChatsByProject(projectId: string): OfflineChatRow[] {
  return loadBundle()
    .chats.filter((c) => c.project_id === projectId)
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
}

export function offlineInsertChat(row: OfflineChatRow): void {
  mutate((b) => {
    b.chats.push(row);
  });
}

export function offlineGetChat(chatId: string): OfflineChatRow | undefined {
  return loadBundle().chats.find((c) => c.id === chatId);
}

export function offlineUpdateChatTitle(chatId: string, title: string): void {
  const now = new Date().toISOString();
  mutate((b) => {
    const c = b.chats.find((x) => x.id === chatId);
    if (c) {
      c.title = title;
      c.updated_at = now;
    }
  });
}

export function offlineDeleteChat(chatId: string): void {
  mutate((b) => {
    b.chats = b.chats.filter((c) => c.id !== chatId);
    b.messages = b.messages.filter((m) => m.chat_id !== chatId);
    b.workflowRuns = b.workflowRuns.filter((r) => r.chat_id !== chatId);
  });
}

export function offlineTouchChat(chatId: string): void {
  const now = new Date().toISOString();
  mutate((b) => {
    const c = b.chats.find((x) => x.id === chatId);
    if (c) c.updated_at = now;
  });
}

// --- Messages ---

export function offlineListMessages(chatId: string, limit: number, offset: number): OfflineMessageRow[] {
  const list = loadBundle()
    .messages.filter((m) => m.chat_id === chatId)
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  return list.slice(offset, offset + limit);
}

export function offlineCountMessages(chatId: string): number {
  return loadBundle().messages.filter((m) => m.chat_id === chatId).length;
}

export function offlineInsertMessage(row: OfflineMessageRow): void {
  mutate((b) => {
    b.messages.push(row);
    offlineTouchChatInBundle(b, row.chat_id);
  });
}

function offlineTouchChatInBundle(b: OfflineBundle, chatId: string): void {
  const c = b.chats.find((x) => x.id === chatId);
  if (c) c.updated_at = new Date().toISOString();
}

export function offlineUpdateMessage(
  messageId: string,
  patch: Partial<Pick<OfflineMessageRow, 'workflow_run_id' | 'metadata' | 'content'>>,
): void {
  mutate((b) => {
    const m = b.messages.find((x) => x.id === messageId);
    if (!m) return;
    Object.assign(m, patch);
    offlineTouchChatInBundle(b, m.chat_id);
  });
}

export function offlineGetMessage(messageId: string): OfflineMessageRow | undefined {
  return loadBundle().messages.find((m) => m.id === messageId);
}

// --- Workflow runs ---

export function offlineListRunsForChat(chatId: string): OfflineWorkflowRunRow[] {
  return loadBundle()
    .workflowRuns.filter((r) => r.chat_id === chatId)
    .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
}

export function offlineInsertWorkflowRun(row: OfflineWorkflowRunRow): void {
  mutate((b) => {
    b.workflowRuns.push(row);
  });
}

export function offlineUpdateWorkflowRun(
  runId: string,
  patch: Partial<Pick<OfflineWorkflowRunRow, 'status' | 'completed_at' | 'result_summary'>>,
): void {
  mutate((b) => {
    const r = b.workflowRuns.find((x) => x.id === runId);
    if (r) Object.assign(r, patch);
  });
}

export function offlineGetWorkflowRun(runId: string): OfflineWorkflowRunRow | undefined {
  return loadBundle().workflowRuns.find((r) => r.id === runId);
}

// --- Run nodes & actions (workflow execution trace) ---

export function offlineInsertRunNode(node: RunNode): void {
  mutate((b) => {
    b.runNodes.push(node);
  });
}

export function offlinePatchRunNode(
  runNodeId: string,
  patch: Partial<RunNode>,
): void {
  mutate((b) => {
    const n = b.runNodes.find((x) => x.id === runNodeId);
    if (n) Object.assign(n, patch);
  });
}

export function offlineInsertNodeAction(action: NodeAction): void {
  mutate((b) => {
    b.nodeActions.push(action);
  });
}

export function offlinePatchNodeAction(actionId: string, patch: Partial<NodeAction>): void {
  mutate((b) => {
    const a = b.nodeActions.find((x) => x.id === actionId);
    if (a) Object.assign(a, patch);
  });
}

export function offlineLoadRunGraph(runId: string): {
  run: OfflineWorkflowRunRow;
  nodes: (RunNode & { actions: NodeAction[] })[];
} {
  const b = loadBundle();
  const run = b.workflowRuns.find((r) => r.id === runId);
  if (!run) throw new Error(`workflow run not found: ${runId}`);
  const nodes = b.runNodes
    .filter((n) => n.run_id === runId)
    .sort((a, b) => (a.step_index ?? 0) - (b.step_index ?? 0))
    .map((node) => ({
      ...node,
      actions: b.nodeActions
        .filter((a) => a.node_id === node.id)
        .sort((x, y) => (x.step_index ?? 0) - (y.step_index ?? 0)),
    }));
  return { run, nodes };
}
