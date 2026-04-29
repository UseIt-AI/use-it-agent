/**
 * Workflow API — 离线优先：工作流与发布元数据存于 localStorage
 */

import { API_URL } from '@/config/runtimeEnv';
import { getOptionalApiBearerToken } from '@/services/apiAuth';
import { LOCAL_OFFLINE_USER_ID, offlineDeleteWorkflow, offlineGetPublication, offlineGetWorkflow, offlineListWorkflowsForOwner, offlinePutPublication, offlinePutWorkflow } from '@/services/localOfflineStore';
import type {
  Graph,
  Workflow,
  WorkflowListItem,
  PublicWorkflowListItem,
  WorkflowPublication,
  CreateWorkflowParams,
  UpdateWorkflowParams,
  UpdatePublicationParams,
} from './types';

export class WorkflowApiError extends Error {
  code: string;
  details?: any;

  constructor(code: string, message: string, details?: any) {
    super(message);
    this.name = 'WorkflowApiError';
    this.code = code;
    this.details = details;
  }
}

const WORKFLOW_TTL = 5000;
const workflowPromiseCache = new Map<string, Promise<Workflow>>();
const workflowDataCache = new Map<string, { data: Workflow; ts: number }>();
let workflowListPromise: Promise<WorkflowListItem[]> | null = null;
let workflowListCache: { data: WorkflowListItem[]; ts: number } | null = null;

function invalidateWorkflowCaches(id?: string) {
  workflowListCache = null;
  if (id) {
    workflowDataCache.delete(id);
  } else {
    workflowDataCache.clear();
  }
}

function nowIso() {
  return new Date().toISOString();
}

function emptyPublication(workflowId: string): WorkflowPublication {
  const t = nowIso();
  return {
    workflow_id: workflowId,
    status: 'draft',
    is_featured: false,
    featured_at: null,
    sort_order: 0,
    category: null,
    tags: [],
    icon: null,
    cover_url: null,
    fork_count: 0,
    run_count: 0,
    bundled_skills: [],
    example_files: [],
    created_at: t,
    updated_at: t,
  };
}

export async function getWorkflowList(): Promise<WorkflowListItem[]> {
  const userId = LOCAL_OFFLINE_USER_ID;

  if (workflowListCache && Date.now() - workflowListCache.ts < WORKFLOW_TTL) {
    return workflowListCache.data;
  }

  if (workflowListPromise) return workflowListPromise;

  workflowListPromise = (async () => {
    try {
      const rows = offlineListWorkflowsForOwner(userId);
      const result: WorkflowListItem[] = rows
        .map((w) => ({
          id: w.id,
          name: w.name,
          description: w.description,
          updated_at: w.updated_at,
          is_public: w.is_public,
        }))
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      workflowListCache = { data: result, ts: Date.now() };
      return result;
    } finally {
      workflowListPromise = null;
    }
  })();

  return workflowListPromise;
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const cached = workflowDataCache.get(id);
  if (cached && Date.now() - cached.ts < WORKFLOW_TTL) {
    return cached.data;
  }

  const inflight = workflowPromiseCache.get(id);
  if (inflight) return inflight;

  const promise = (async () => {
    const data = offlineGetWorkflow(id);
    if (!data) {
      throw new WorkflowApiError('WORKFLOW_NOT_FOUND', `Workflow not found: ${id}`);
    }
    workflowDataCache.set(id, { data, ts: Date.now() });
    return data;
  })();

  workflowPromiseCache.set(id, promise);
  try {
    return await promise;
  } finally {
    workflowPromiseCache.delete(id);
  }
}

export async function getWorkflowGraph(id: string): Promise<Graph> {
  const workflow = await getWorkflow(id);
  return workflow.definition;
}

export async function createWorkflow(params: CreateWorkflowParams): Promise<Workflow> {
  const id = crypto.randomUUID();
  const t = nowIso();
  const defaultGraph: Graph = {
    nodes: [],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  };

  const row: Workflow = {
    id,
    owner_id: LOCAL_OFFLINE_USER_ID,
    name: params.name,
    description: params.description ?? null,
    version: '1.0',
    definition: params.definition || defaultGraph,
    is_public: false,
    created_at: t,
    updated_at: t,
    quick_start_messages: params.quick_start_messages ?? undefined,
  };

  offlinePutWorkflow(row);
  offlinePutPublication(emptyPublication(id));
  invalidateWorkflowCaches();
  return row;
}

export async function updateWorkflow(id: string, params: UpdateWorkflowParams): Promise<Workflow> {
  const existing = offlineGetWorkflow(id);
  if (!existing) {
    throw new WorkflowApiError('WORKFLOW_NOT_FOUND', 'Workflow not found');
  }

  const updated: Workflow = {
    ...existing,
    updated_at: nowIso(),
    name: params.name !== undefined ? params.name : existing.name,
    description: params.description !== undefined ? params.description : existing.description,
    definition: params.definition !== undefined ? params.definition : existing.definition,
    is_public: params.is_public !== undefined ? params.is_public : existing.is_public,
    quick_start_messages:
      params.quick_start_messages !== undefined
        ? params.quick_start_messages ?? undefined
        : existing.quick_start_messages,
  };

  offlinePutWorkflow(updated);
  invalidateWorkflowCaches(id);
  return updated;
}

export async function saveWorkflowGraph(id: string, graph: Graph): Promise<void> {
  const existing = offlineGetWorkflow(id);
  if (!existing) throw new WorkflowApiError('WORKFLOW_NOT_FOUND', 'Workflow not found');
  offlinePutWorkflow({
    ...existing,
    definition: graph,
    updated_at: nowIso(),
  });
  invalidateWorkflowCaches(id);
}

export async function deleteWorkflow(id: string): Promise<void> {
  offlineDeleteWorkflow(id);
  invalidateWorkflowCaches(id);
}

export async function duplicateWorkflow(id: string): Promise<Workflow> {
  const original = await getWorkflow(id);
  return createWorkflow({
    name: `${original.name} (副本)`,
    description: original.description || undefined,
    definition: original.definition,
    quick_start_messages: original.quick_start_messages ?? null,
  });
}

export async function workflowExists(id: string): Promise<boolean> {
  return !!offlineGetWorkflow(id);
}

export type WorkflowChangeCallback = (workflow: Workflow) => void;

export function subscribeToWorkflow(_id: string, _onUpdate: WorkflowChangeCallback): () => void {
  return () => {};
}

let _publicWorkflowsCache: { data: PublicWorkflowListItem[]; ts: number } | null = null;
const PUBLIC_WORKFLOWS_TTL = 5 * 60 * 1000;

export async function getPublicWorkflows(forceRefresh = false): Promise<PublicWorkflowListItem[]> {
  if (!forceRefresh && _publicWorkflowsCache && Date.now() - _publicWorkflowsCache.ts < PUBLIC_WORKFLOWS_TTL) {
    return _publicWorkflowsCache.data;
  }

  const items: PublicWorkflowListItem[] = [];
  for (const w of offlineListWorkflowsForOwner(LOCAL_OFFLINE_USER_ID)) {
    if (!w.is_public) continue;
    const pub = offlineGetPublication(w.id);
    if (!pub || pub.status !== 'published') continue;
    if (!pub.is_featured) continue;
    items.push({
      id: w.id,
      name: w.name,
      description: w.description,
      updated_at: w.updated_at,
      is_public: w.is_public,
      status: pub.status,
      is_featured: pub.is_featured,
      sort_order: pub.sort_order,
      category: pub.category,
      tags: pub.tags,
      icon: pub.icon,
      cover_url: pub.cover_url,
      fork_count: pub.fork_count,
      run_count: pub.run_count,
      bundled_skills: pub.bundled_skills,
      example_files: pub.example_files,
      quick_start_messages: w.quick_start_messages,
    });
  }
  items.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  _publicWorkflowsCache = { data: items, ts: Date.now() };
  return items;
}

export async function getWorkflowPublication(workflowId: string): Promise<WorkflowPublication | null> {
  return offlineGetPublication(workflowId) ?? null;
}

export async function upsertWorkflowPublication(
  workflowId: string,
  params: UpdatePublicationParams,
): Promise<WorkflowPublication> {
  const prev = offlineGetPublication(workflowId) ?? emptyPublication(workflowId);
  const next: WorkflowPublication = {
    ...prev,
    updated_at: nowIso(),
    status: params.status !== undefined ? params.status : prev.status,
    category: params.category !== undefined ? params.category : prev.category,
    tags: params.tags !== undefined ? params.tags : prev.tags,
    icon: params.icon !== undefined ? params.icon : prev.icon,
    cover_url: params.cover_url !== undefined ? params.cover_url : prev.cover_url,
    bundled_skills: params.bundled_skills !== undefined ? params.bundled_skills : prev.bundled_skills,
    example_files: params.example_files !== undefined ? params.example_files : prev.example_files,
  };
  offlinePutPublication(next);
  return next;
}

export async function forkPublicWorkflow(id: string): Promise<Workflow> {
  const original = await getWorkflow(id);
  if (!original.is_public) {
    throw new WorkflowApiError('PERMISSION_DENIED', 'Cannot fork non-public workflow');
  }
  return createWorkflow({
    name: `${original.name} (Fork)`,
    description: original.description || undefined,
    definition: original.definition,
    quick_start_messages: original.quick_start_messages ?? null,
  });
}

export interface AssetPresignUploadRequest {
  workflow_id: string;
  asset_type: 'skill' | 'example';
  files: Array<{
    filename: string;
    relative_path: string;
    content_type?: string;
    size_bytes?: number;
  }>;
}

export interface AssetPresignUploadFile {
  filename: string;
  relative_path: string;
  s3_key: string;
  upload_url: string;
  headers: Record<string, string>;
  expires_at: string;
}

export interface AssetPresignUploadResponse {
  workflow_id: string;
  asset_type: string;
  files: AssetPresignUploadFile[];
}

export async function presignWorkflowAssetUpload(
  _request: AssetPresignUploadRequest,
): Promise<AssetPresignUploadResponse> {
  throw new WorkflowApiError('OFFLINE_UNSUPPORTED', '离线发行版不支持云端资源预签名上传');
}

export interface AssetPresignDownloadRequest {
  workflow_id: string;
  files: Array<{ s3_key: string }>;
}

export interface AssetPresignDownloadFile {
  s3_key: string;
  download_url: string;
  expires_at: string;
}

export interface AssetPresignDownloadResponse {
  workflow_id: string;
  files: AssetPresignDownloadFile[];
}

export async function presignWorkflowAssetDownload(
  _request: AssetPresignDownloadRequest,
): Promise<AssetPresignDownloadResponse> {
  throw new WorkflowApiError('OFFLINE_UNSUPPORTED', '离线发行版不支持云端资源预签名下载');
}

async function fetchWithOptionalGatewayAuth(url: string, init: RequestInit): Promise<Response> {
  const token = getOptionalApiBearerToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(url, { ...init, headers });
}

/** 若自建网关仍提供同名预签名接口，可配置 VITE_API_BEARER_TOKEN 后使用（非 Supabase） */
export async function presignWorkflowAssetUploadViaGateway(
  request: AssetPresignUploadRequest,
): Promise<AssetPresignUploadResponse> {
  const res = await fetchWithOptionalGatewayAuth(`${API_URL}/api/upload/workflow-assets/presign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => 'Unknown error');
    throw new WorkflowApiError('PRESIGN_FAILED', `Failed to presign upload: ${detail}`);
  }
  return (await res.json()) as AssetPresignUploadResponse;
}

export async function presignWorkflowAssetDownloadViaGateway(
  request: AssetPresignDownloadRequest,
): Promise<AssetPresignDownloadResponse> {
  const res = await fetchWithOptionalGatewayAuth(`${API_URL}/api/download/workflow-assets/presign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => 'Unknown error');
    throw new WorkflowApiError('PRESIGN_FAILED', `Failed to presign download: ${detail}`);
  }
  return (await res.json()) as AssetPresignDownloadResponse;
}

export const workflowApi = {
  list: getWorkflowList,
  get: getWorkflow,
  getGraph: getWorkflowGraph,
  create: createWorkflow,
  update: updateWorkflow,
  saveGraph: saveWorkflowGraph,
  delete: deleteWorkflow,
  duplicate: duplicateWorkflow,
  exists: workflowExists,
  subscribe: subscribeToWorkflow,
  listPublic: getPublicWorkflows,
  fork: forkPublicWorkflow,
  getPublication: getWorkflowPublication,
  upsertPublication: upsertWorkflowPublication,
  presignAssetUpload: presignWorkflowAssetUpload,
  presignAssetDownload: presignWorkflowAssetDownload,
};

export default workflowApi;
