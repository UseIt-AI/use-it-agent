import { getOptionalApiBearerToken } from '@/services/apiAuth';
import { API_URL } from '@/config/runtimeEnv';
import type { Graph } from '../types';

// --- Types ---

export interface AnalyzeWorkflowVideoRequest {
  app_id: string;
  s3_key: string;
  task_description: string;
}

export interface AnalyzeWorkflowVideoResponse {
  status: string;
  task_id: string;
  efs_output_dir?: string;
}

export interface AnalyzeProgressRequest {
  app_id: string;
}

export interface AnalyzeProgressResponse {
  current_stepId: number;
  total_action_num: number;
  running: 'waiting' | 'running' | 'finished' | 'error';
  error_info?: string;
  start_time?: string;
  end_time?: string;
  efs_domain?: string;
  // 新增进度详情字段
  description?: string;  // 当前步骤描述 (来自 progress_message)
  progress_percent?: number;  // 进度百分比 (0-100)
}

export interface GetTraceRequest {
  app_id: string;
  domain?: string;
  video_url_external?: string;  // External video URL (e.g., CloudFront)
  cover_img_url?: string;       // Cover image URL
}

/**
 * Trace data from Demo Parser
 */
export interface TraceData {
  task_description: string;
  user_id: string;
  trace_id: string;
  video_url: string;
  trajectory: any[];
}

/**
 * Response from get trace API
 * Contains ReactFlow Graph format when available
 */
export interface GetTraceResponse {
  status: string;
  graph?: Graph;           // ReactFlow Graph format (nodes, edges, viewport)
  trace_data?: TraceData;  // Original trace data
}

// --- API ---

async function getAuthHeaders() {
  const token = getOptionalApiBearerToken();
  return {
    'Content-Type': 'application/json',
    'Authorization': token ? `Bearer ${token}` : '',
  };
}

export async function analyzeWorkflowVideo(payload: AnalyzeWorkflowVideoRequest): Promise<AnalyzeWorkflowVideoResponse> {
  const headers = await getAuthHeaders();
  // 与 files_upload 在 main.py 中 prefix="/api" 的挂载一致（同 workflowVideoUpload.ts）
  const res = await fetch(`${API_URL}/api/files/analyze/workflow-video`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Analyze request failed');
  }
  return res.json();
}

export async function getAnalyzeProgress(payload: AnalyzeProgressRequest): Promise<AnalyzeProgressResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/files/analyze/workflow-video/progress`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Get progress failed');
  }
  return res.json();
}

/**
 * Get the analysis trace result
 * 
 * Returns ReactFlow Graph format when available:
 * - graph: { nodes, edges, viewport } - can be directly used with ReactFlow
 * - trace_data: original trace data with trajectory
 */
export async function getAnalyzeTrace(payload: GetTraceRequest): Promise<GetTraceResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/files/analyze/workflow-video/trace`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Get trace failed');
  }
  return res.json();
}

