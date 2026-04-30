import { useState, useCallback, useRef, useEffect } from 'react';
import { analyzeWorkflowVideo, getAnalyzeProgress, getAnalyzeTrace } from '../../../services/workflowAnalyze';

type AnalyzeStatus = 'idle' | 'analyzing' | 'done' | 'error';

interface AnalyzeState {
  status: AnalyzeStatus;
  progress: number;
  error: string | null;
  description: string | null;
}

interface UseAnalyzeOptions {
  workflowId: string | undefined;
}

export function useAnalyze({ workflowId }: UseAnalyzeOptions) {
  const [state, setState] = useState<AnalyzeState>({
    status: 'idle',
    progress: 0,
    error: null,
    description: null,
  });

  const pollRef = useRef<number | null>(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        window.clearTimeout(pollRef.current);
      }
    };
  }, []);

  const startAnalysis = useCallback(async (s3Key: string, taskDescription?: string) => {
    if (!workflowId) return false;

    try {
      setState({
        status: 'analyzing',
        progress: 0,
        error: null,
        description: null,
      });

      // Kick off analysis
      await analyzeWorkflowVideo({
        app_id: workflowId,
        s3_key: s3Key,
        task_description: taskDescription || 'No description provided',
      });

      // Poll progress
      const poll = async () => {
        try {
          const p = await getAnalyzeProgress({ app_id: workflowId });

          if (p.running === 'finished') {
            setState((prev) => ({
              ...prev,
              status: 'done',
              progress: 100,
              description: null,
            }));
            return;
          }

          if (p.running === 'error') {
            setState((prev) => ({
              ...prev,
              status: 'error',
              error: p.error_info || 'Analysis failed unknown error',
              description: null,
            }));
            return;
          }

          // Update progress
          const pct = p.progress_percent != null
            ? Math.round(p.progress_percent)
            : Math.round((p.current_stepId / (p.total_action_num || 1)) * 100);
          
          setState((prev) => ({
            ...prev,
            progress: Math.min(99, Math.max(0, pct)),
            description: p.description || null,
          }));

          // Continue polling
          pollRef.current = window.setTimeout(poll, 2000);
        } catch (e: any) {
          console.error('Poll failed', e);
          // Retry polling on transient network errors
          pollRef.current = window.setTimeout(poll, 3000);
        }
      };

      poll();
      return true;

    } catch (e: any) {
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: e.message || 'Failed to start analysis',
      }));
      return false;
    }
  }, [workflowId]);

  const getTrace = useCallback(async (videoUrl?: string) => {
    if (!workflowId) return null;

    try {
      const res = await getAnalyzeTrace({
        app_id: workflowId,
        video_url_external: videoUrl,
      });
      return res;
    } catch (e: any) {
      console.error('Failed to get trace:', e);
      setState((prev) => ({
        ...prev,
        error: e?.message || 'Failed to load workflow from demonstration',
      }));
      return null;
    }
  }, [workflowId]);

  const reset = useCallback(() => {
    if (pollRef.current) {
      window.clearTimeout(pollRef.current);
      pollRef.current = null;
    }
    setState({
      status: 'idle',
      progress: 0,
      error: null,
      description: null,
    });
  }, []);

  return {
    ...state,
    startAnalysis,
    getTrace,
    reset,
  };
}


