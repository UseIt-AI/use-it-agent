import { useState, useCallback, useRef } from 'react';
import { presignWorkflowVideoUpload, finalizeWorkflowVideoUpload } from '../../../services/workflowVideoUpload';

type UploadStatus = 'idle' | 'presigning' | 'uploading' | 'finalizing' | 'done' | 'error';

interface UploadState {
  status: UploadStatus;
  percent: number;
  error: string | null;
  s3Key: string | null;
  previewUrl: string | null;
}

interface UseUploadOptions {
  workflowId: string | undefined;
  onComplete?: (s3Key: string, previewUrl: string) => void;
}

export function useUpload({ workflowId, onComplete }: UseUploadOptions) {
  const [state, setState] = useState<UploadState>({
    status: 'idle',
    percent: 0,
    error: null,
    s3Key: null,
    previewUrl: null,
  });

  const cancelRef = useRef<(() => void) | null>(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const startUpload = useCallback(async (filePath: string) => {
    if (!filePath || !workflowId) return false;

    if (!window.electron?.uploadPresignedPut || !window.electron?.onS3UploadProgress) {
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: 'Upload API is not available.',
      }));
      return false;
    }

    setState({
      status: 'presigning',
      percent: 0,
      error: null,
      s3Key: null,
      previewUrl: null,
    });

    let cancelled = false;
    cancelRef.current = () => { cancelled = true; };

    const requestId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const filename = filePath.split(/[/\\]/).pop() || 'recording.mkv';

    const offProgress = window.electron.onS3UploadProgress((p) => {
      if (p?.requestId !== requestId) return;
      setState((prev) => ({ ...prev, percent: p.percent || 0 }));
    });

    try {
      const presign = await presignWorkflowVideoUpload({ filename, workflowId });
      if (cancelled) return false;

      setState((prev) => ({ ...prev, status: 'uploading' }));

      const putRes = await window.electron!.uploadPresignedPut!({
        requestId,
        filePath,
        uploadUrl: presign.upload_url,
        headers: presign.headers,
      });
      if (cancelled) return false;
      if (!putRes?.success) throw new Error(putRes?.error || 'Upload failed');

      setState((prev) => ({ ...prev, status: 'finalizing' }));

      const fin = await finalizeWorkflowVideoUpload({
        fileId: presign.file_id,
        s3Key: presign.s3_key,
        etag: putRes.etag,
        workflowId,
      });
      if (cancelled) return false;

      setState({
        status: 'done',
        percent: 100,
        error: null,
        s3Key: fin.s3_key,
        previewUrl: fin.preview_url,
      });

      onCompleteRef.current?.(fin.s3_key, fin.preview_url);
      return true;

    } catch (e: any) {
      if (cancelled) return false;
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: e?.message || String(e),
      }));
      return false;
    } finally {
      offProgress?.();
      cancelRef.current = null;
    }
  }, [workflowId]);

  const cancel = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    cancel();
    setState({
      status: 'idle',
      percent: 0,
      error: null,
      s3Key: null,
      previewUrl: null,
    });
  }, [cancel]);

  return {
    ...state,
    startUpload,
    cancel,
    reset,
  };
}


