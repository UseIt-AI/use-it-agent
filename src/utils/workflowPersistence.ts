/**
 * Workflow 执行数据持久化 — 离线优先，写入 localStorage（见 localOfflineStore）
 */

import { compressScreenshot } from './screenshotCompressor';
import type { RunNode, NodeAction } from './workflowRunTypes';
import {
  offlineInsertRunNode,
  offlinePatchRunNode,
  offlineInsertNodeAction,
  offlinePatchNodeAction,
  offlineLoadRunGraph,
  offlineGetWorkflowRun,
} from '@/services/localOfflineStore';

export type { RunNode, NodeAction } from './workflowRunTypes';

const INLINE_DATA_URL_MAX_CHARS = 1_200_000;

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(new Error('readAsDataURL failed'));
    r.readAsDataURL(blob);
  });
}

async function screenshotToInlineDataUrl(base64Image: string): Promise<{ url: string; path: string; expiresAt: number }> {
  const blob = await compressScreenshot(base64Image, {
    maxWidth: parseInt(import.meta.env.VITE_SCREENSHOT_MAX_WIDTH || '1920', 10),
    maxHeight: parseInt(import.meta.env.VITE_SCREENSHOT_MAX_HEIGHT || '1080', 10),
    quality: parseFloat(import.meta.env.VITE_SCREENSHOT_QUALITY || '0.8'),
    format: 'jpeg',
  });
  let dataUrl = await blobToDataUrl(blob);
  if (dataUrl.length > INLINE_DATA_URL_MAX_CHARS) {
    dataUrl = dataUrl.slice(0, INLINE_DATA_URL_MAX_CHARS);
  }
  const path = `inline:jpeg:${Date.now()}`;
  return { url: dataUrl, path, expiresAt: Math.floor(Date.now() / 1000) + 86400 * 365 };
}

export async function createRunNode(
  runId: string,
  nodeId: string,
  nodeType: RunNode['node_type'],
  stepIndex: number,
  options?: {
    title?: string;
    instruction?: string;
  },
): Promise<RunNode> {
  const id = crypto.randomUUID();
  const row: RunNode = {
    id,
    run_id: runId,
    node_id: nodeId,
    node_type: nodeType,
    step_index: stepIndex,
    status: 'running',
    title: options?.title,
    instruction: options?.instruction,
    started_at: new Date().toISOString(),
  };
  offlineInsertRunNode(row);
  return row;
}

export async function updateRunNodeStatus(
  runNodeId: string,
  status: RunNode['status'],
  options?: {
    reasoning?: string;
    output?: string;
    error_message?: string;
    tokens_used?: number;
    progress_current?: number;
    progress_total?: number;
    progress_message?: string;
  },
): Promise<void> {
  const patch: Partial<RunNode> = { status, ...(options || {}) };
  if (status === 'completed' || status === 'failed') {
    patch.completed_at = new Date().toISOString();
  }
  offlinePatchRunNode(runNodeId, patch);
}

export async function updateRunNodeProgress(
  runNodeId: string,
  current: number,
  total?: number,
  message?: string,
): Promise<void> {
  offlinePatchRunNode(runNodeId, {
    progress_current: current,
    progress_total: total,
    progress_message: message,
  });
}

export async function createCuaStepAction(
  runNodeId: string,
  stepIndex: number,
  _userId: string,
  options: {
    title?: string;
    screenshotBase64?: string;
    reasoning?: string;
    content?: string;
    actionDetail?: NodeAction['action_detail'];
  },
): Promise<NodeAction> {
  let screenshotUrl: string | undefined;
  let screenshotPath: string | undefined;
  let screenshotExpiresAt: number | undefined;

  if (options.screenshotBase64) {
    try {
      const r = await screenshotToInlineDataUrl(options.screenshotBase64);
      screenshotUrl = r.url;
      screenshotPath = r.path;
      screenshotExpiresAt = r.expiresAt;
    } catch (e) {
      console.error('[Persistence] screenshot inline encode failed:', e);
    }
  }

  const id = crypto.randomUUID();
  const row: NodeAction = {
    id,
    node_id: runNodeId,
    action_type: 'cua_step',
    step_index: stepIndex,
    status: 'running',
    title: options.title || `Step ${stepIndex}`,
    reasoning: options.reasoning,
    content: options.content,
    action_detail: options.actionDetail,
    screenshot_url: screenshotUrl,
    screenshot_path: screenshotPath,
    screenshot_expires_at: screenshotExpiresAt,
    started_at: new Date().toISOString(),
  };
  offlineInsertNodeAction(row);
  return row;
}

export async function updateCuaStepAction(
  actionId: string,
  options: {
    status?: NodeAction['status'];
    reasoning?: string;
    content?: string;
    actionDetail?: NodeAction['action_detail'];
    duration_ms?: number;
    error_message?: string;
  },
): Promise<void> {
  const patch: Partial<NodeAction> = { ...options };
  if (options.status === 'completed' || options.status === 'failed') {
    patch.completed_at = new Date().toISOString();
  }
  offlinePatchNodeAction(actionId, patch);
}

export async function createToolCallAction(
  runNodeId: string,
  stepIndex: number,
  toolName: string,
  options: {
    title?: string;
    input?: Record<string, any>;
    reasoning?: string;
  },
): Promise<NodeAction> {
  const id = crypto.randomUUID();
  const row: NodeAction = {
    id,
    node_id: runNodeId,
    action_type: 'tool_call',
    step_index: stepIndex,
    status: 'running',
    title: options.title || toolName,
    tool_name: toolName,
    input: options.input,
    reasoning: options.reasoning,
    started_at: new Date().toISOString(),
  };
  offlineInsertNodeAction(row);
  return row;
}

export async function updateToolCallAction(
  actionId: string,
  options: {
    status: NodeAction['status'];
    output?: Record<string, any>;
    reasoning?: string;
    duration_ms?: number;
    error_message?: string;
  },
): Promise<void> {
  offlinePatchNodeAction(actionId, {
    status: options.status,
    output: options.output,
    reasoning: options.reasoning,
    duration_ms: options.duration_ms,
    error_message: options.error_message,
    completed_at: new Date().toISOString(),
  });
}

export async function refreshSignedUrl(path: string): Promise<string> {
  if (path.startsWith('inline:') || path.startsWith('data:')) {
    return path;
  }
  throw new Error('[Persistence] refreshSignedUrl: offline build only supports inline screenshots');
}

export async function loadWorkflowRunData(runId: string): Promise<{
  run: any;
  nodes: (RunNode & { actions: NodeAction[] })[];
}> {
  const { run, nodes } = offlineLoadRunGraph(runId);
  const meta = offlineGetWorkflowRun(runId);
  return {
    run: meta || run,
    nodes,
  };
}

export async function refreshExpiredScreenshots(actions: NodeAction[]): Promise<NodeAction[]> {
  return actions;
}
