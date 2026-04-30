import { useState, useCallback } from 'react';
import { useRecording } from './useRecording';
import { useUpload } from './useUpload';
import { useAnalyze } from './useAnalyze';
import { traceToGraph } from '../../../utils/traceToGraph';
import { createNode } from '../utils/nodeFactory';

type WizardStep = 1 | 2 | 3;

interface UseDemoWizardOptions {
  workflowId: string | undefined;
  setDbNodes: (updater: any) => void;
  setDbEdges: (updater: any) => void;
  save: (force?: boolean) => Promise<void>;
  onComplete: () => void;
}

export function useDemoWizard({
  workflowId,
  setDbNodes,
  setDbEdges,
  save,
  onComplete,
}: UseDemoWizardOptions) {
  const [isOpen, setIsOpen] = useState(false);
  const [step, setStep] = useState<WizardStep>(1);
  const [description, setDescription] = useState('');

  // Recording hook
  const recording = useRecording({
    enabled: isOpen && step === 2,
    onStopComplete: () => {
      // Move to Analyze step when stop completes successfully
      setStep(3);
    },
  });

  // Upload hook
  const upload = useUpload({
    workflowId,
    onComplete: (s3Key) => {
      // Start analysis automatically after upload
      analyze.startAnalysis(s3Key, description);
    },
  });

  // Analyze hook
  const analyze = useAnalyze({ workflowId });

  const open = useCallback(() => {
    setIsOpen(true);
    setStep(1);
  }, []);

  const close = useCallback(() => {
    upload.cancel();
    setIsOpen(false);
    setStep(1);
    setDescription('');
    recording.reset();
    upload.reset();
    analyze.reset();
  }, [upload, recording, analyze]);

  const nextStep = useCallback(() => {
    if (step < 3) {
      setStep((s) => (s + 1) as WizardStep);
    }
  }, [step]);

  const prevStep = useCallback(() => {
    if (step > 1) {
      setStep((s) => (s - 1) as WizardStep);
    }
  }, [step]);

  const handleRecordToggle = useCallback(async () => {
    await recording.toggleRecording(description?.trim() || 'Recording');
  }, [recording, description]);

  const handleStartUpload = useCallback(async () => {
    if (recording.filePath) {
      await upload.startUpload(recording.filePath);
    }
  }, [recording.filePath, upload]);

  const finish = useCallback(async () => {
    if (!workflowId) {
      console.error('handleWizardFinish: workflowId is missing');
      return;
    }

    let graphCreated = false;

    try {
      // If we have analysis result, try to get the trace and build graph
      if (analyze.status === 'done') {
        console.log('Analysis is done, fetching trace...');

        const res = await analyze.getTrace(upload.previewUrl || undefined);
        console.log('Trace response:', res);

        // Check if response contains pre-built ReactFlow graph
        if (res?.graph && res.graph.nodes && res.graph.nodes.length > 0) {
          console.log('Using pre-built ReactFlow graph from backend:', res.graph);
          setDbNodes(res.graph.nodes as any);
          setDbEdges(res.graph.edges as any);
          graphCreated = true;

          console.log('Graph created from backend, saving...');
          setTimeout(() => {
            save(true).catch((err) => {
              console.error('Failed to save workflow after trace:', err);
            });
          }, 200);
          
          onComplete();
          close();
          return;
        }

        // Fallback: Convert trace_data to graph using local converter
        const traceData = res?.trace_data || res?.data || res?.trace || (res?.steps ? res : null);

        if (traceData) {
          console.log('Converting trace to graph using local converter...', traceData);
          const graph = traceToGraph(traceData);
          console.log('Generated graph:', graph);

          if (graph.nodes && graph.nodes.length > 0) {
            setDbNodes(graph.nodes as any);
            setDbEdges(graph.edges as any);
            graphCreated = true;

            console.log('Graph created, saving...');
            setTimeout(() => {
              save(true).catch((err) => {
                console.error('Failed to save workflow after trace:', err);
              });
            }, 200);

            onComplete();
            close();
            return;
          } else {
            console.warn('Generated graph has no nodes, falling back to default');
          }
        } else {
          console.warn('No valid trace data found in response:', res);
        }
      }
    } catch (e: any) {
      console.error('Failed to apply trace to graph:', e);
    }

    // Default Fallback - create a start node with description
    if (!graphCreated) {
      console.log('Creating fallback start node');
      const startNode = createNode('start', { x: 100, y: 100 });
      if (description?.trim()) {
        (startNode.data as any).desc = description.trim();
      }

      setDbNodes([startNode as any]);
      setDbEdges([]);

      console.log('Fallback node created, saving...');
      setTimeout(() => {
        save(true).catch((err) => {
          console.error('Failed to save fallback workflow:', err);
        });
      }, 200);
    }

    onComplete();
    close();
  }, [workflowId, analyze, upload.previewUrl, setDbNodes, setDbEdges, save, description, onComplete, close]);

  return {
    isOpen,
    step,
    description,
    setDescription,
    recording,
    upload,
    analyze,
    open,
    close,
    nextStep,
    prevStep,
    setStep,
    handleRecordToggle,
    handleStartUpload,
    finish,
  };
}


