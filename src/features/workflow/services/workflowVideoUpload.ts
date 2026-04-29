import { API_URL } from '@/config/runtimeEnv';
import { buildJsonFetchHeaders } from '@/services/apiAuth';

export type PresignResult = {
  file_id: string;
  s3_key: string;
  upload_url: string;
  headers: Record<string, string>;
  expires_at: string;
};

export type FinalizeResult = {
  success: boolean;
  file_id: string;
  s3_key: string;
  preview_url: string;
  preview_expires_at: string;
};

function guessContentType(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.mkv')) return 'video/x-matroska';
  if (lower.endsWith('.mp4')) return 'video/mp4';
  if (lower.endsWith('.webm')) return 'video/webm';
  return 'application/octet-stream';
}

export async function presignWorkflowVideoUpload(args: { filename: string; workflowId?: string; sizeBytes?: number }): Promise<PresignResult> {
  const content_type = guessContentType(args.filename);
  const res = await fetch(`${API_URL}/api/files/upload/workflow-video/presign`, {
    method: 'POST',
    headers: buildJsonFetchHeaders(),
    body: JSON.stringify({
      filename: args.filename,
      content_type,
      size_bytes: args.sizeBytes,
      workflow_id: args.workflowId,
    }),
  });
  if (!res.ok) throw new Error(`Presign failed: HTTP ${res.status}`);
  return (await res.json()) as PresignResult;
}

export async function finalizeWorkflowVideoUpload(args: { fileId: string; s3Key: string; etag?: string; workflowId?: string }): Promise<FinalizeResult> {
  const res = await fetch(`${API_URL}/api/files/upload/workflow-video/finalize`, {
    method: 'POST',
    headers: buildJsonFetchHeaders(),
    body: JSON.stringify({
      file_id: args.fileId,
      s3_key: args.s3Key,
      etag: args.etag,
      workflow_id: args.workflowId,
    }),
  });
  if (!res.ok) throw new Error(`Finalize failed: HTTP ${res.status}`);
  return (await res.json()) as FinalizeResult;
}




