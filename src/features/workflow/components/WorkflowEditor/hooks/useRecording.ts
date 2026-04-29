import { useState, useEffect, useCallback, useRef } from 'react';

interface RecordingState {
  isRecording: boolean;
  isStopping: boolean;
  duration: number;
  filePath: string | undefined;
  error: string | null;
}

interface UseRecordingOptions {
  enabled: boolean; // Only poll when wizard step 2 is visible
  onStopComplete?: (filePath: string) => void;
}

export function useRecording({ enabled, onStopComplete }: UseRecordingOptions) {
  const [state, setState] = useState<RecordingState>({
    isRecording: false,
    isStopping: false,
    duration: 0,
    filePath: undefined,
    error: null,
  });

  const onStopCompleteRef = useRef(onStopComplete);
  onStopCompleteRef.current = onStopComplete;

  // Subscribe to stop events
  useEffect(() => {
    const offComplete = window.electron?.onRecordingStopComplete?.((payload) => {
      setState((prev) => ({
        ...prev,
        isStopping: false,
        isRecording: false,
        filePath: payload?.filePath || prev.filePath,
        error: payload?.success ? null : (payload?.error || 'Recording stop failed'),
      }));

      if (payload?.success && payload?.filePath) {
        onStopCompleteRef.current?.(payload.filePath);
      }
    });

    const offInitiated = window.electron?.onRecordingStopInitiated?.((payload) => {
      setState((prev) => ({
        ...prev,
        isStopping: !!payload?.stopping,
        filePath: payload?.filePath || prev.filePath,
      }));
    });

    return () => {
      offComplete?.();
      offInitiated?.();
    };
  }, []);

  // Poll status while enabled
  useEffect(() => {
    if (!enabled) return;

    let alive = true;
    const tick = async () => {
      try {
        const status = await window.electron?.recorderGetStatus?.();
        if (!alive || !status) return;
        setState((prev) => ({
          ...prev,
          isRecording: !!status.isRecording,
          isStopping: !!status.isStopping,
          duration: status.duration || 0,
          filePath: status.filePath || prev.filePath,
        }));
      } catch (e: any) {
        console.warn('recorderGetStatus failed:', e);
      }
    };

    tick();
    const interval = window.setInterval(tick, 1000);

    return () => {
      alive = false;
      window.clearInterval(interval);
    };
  }, [enabled]);

  const startRecording = useCallback(async (title?: string) => {
    setState((prev) => ({ ...prev, error: null }));

    if (!window.electron?.recorderStart) {
      setState((prev) => ({
        ...prev,
        error: 'Recording API is not available (preload/IPC not ready).',
      }));
      return false;
    }

    const ok = await window.electron.recorderStart({ title: title || 'Recording' });
    if (!ok) {
      setState((prev) => ({
        ...prev,
        error: 'Failed to start recording (maybe already recording).',
      }));
      return false;
    }
    return true;
  }, []);

  const stopRecording = useCallback(async () => {
    setState((prev) => ({ ...prev, error: null }));

    if (!window.electron?.recorderInitiateStop) {
      setState((prev) => ({
        ...prev,
        error: 'Recording API is not available (preload/IPC not ready).',
      }));
      return false;
    }

    const r = await window.electron.recorderInitiateStop();
    if (r?.success) {
      setState((prev) => ({
        ...prev,
        isStopping: true,
        filePath: r.filePath || prev.filePath,
      }));
      return true;
    } else {
      setState((prev) => ({
        ...prev,
        error: 'Failed to initiate stop recording.',
      }));
      return false;
    }
  }, []);

  const toggleRecording = useCallback(async (title?: string) => {
    if (state.isRecording) {
      return stopRecording();
    } else {
      return startRecording(title);
    }
  }, [state.isRecording, startRecording, stopRecording]);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  const reset = useCallback(() => {
    setState({
      isRecording: false,
      isStopping: false,
      duration: 0,
      filePath: undefined,
      error: null,
    });
  }, []);

  return {
    ...state,
    startRecording,
    stopRecording,
    toggleRecording,
    clearError,
    reset,
  };
}


