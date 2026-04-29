import React, { useEffect, useState, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Info, Video, X, Zap, Plus, Trash2, GripVertical, MousePointer2 } from 'lucide-react';
import type { WorkflowNode } from '@/features/workflow';
import type { ControlPanelMode } from '../../ControlPanel';
import { FIELD_LABEL_CLASS, FIELD_LABEL_WRAP_CLASS, FIELD_TEXTAREA_CLASS } from './formStyles';

// Software logo icon component
function SoftwareLogo({ name, className }: { name: string; className?: string }) {
  const src = `${import.meta.env.BASE_URL}node/${name}.svg`;
  return <img src={src} alt={name} className={className} style={{ objectFit: 'contain' }} />;
}

export const ACTION_TYPES = [
  { value: 'gui', label: 'GUI', icon: <MousePointer2 className="w-3.5 h-3.5" /> },
  { value: 'autocad', label: 'AutoCAD', icon: <SoftwareLogo name="autocad" className="w-3.5 h-3.5" /> },
  { value: 'excel', label: 'Excel', icon: <SoftwareLogo name="excel" className="w-3.5 h-3.5" /> },
  { value: 'word', label: 'Word', icon: <SoftwareLogo name="word" className="w-3.5 h-3.5" /> },
  { value: 'ppt', label: 'PPT', icon: <SoftwareLogo name="ppt" className="w-3.5 h-3.5" /> },
];

function VideoModal({
  open,
  title,
  src,
  poster,
  onClose,
}: {
  open: boolean;
  title: string;
  src: string;
  poster?: string;
  onClose: () => void;
}) {
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-[860px] max-w-[calc(100vw-32px)] bg-canvas border border-divider rounded-xl shadow-2xl overflow-hidden">
        <div className="px-4 h-11 flex items-center justify-between">
          <div className="text-[12px] font-semibold text-black/80 truncate">{title}</div>
          <button
            type="button"
            className="w-9 h-9 inline-flex items-center justify-center rounded-md text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
            onClick={onClose}
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-4 pb-4">
          <div className="w-full aspect-video bg-black rounded-lg overflow-hidden">
            <video className="w-full h-full object-contain" src={src} poster={poster} controls autoPlay />
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function ComputerUseNodeDetails({
  node,
  onUpdate,
  panelMode = 'normal',
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
  panelMode?: ControlPanelMode;
}) {
  const data = node.data as any;

  const [taskDescription, setTaskDescription] = useState(data.instruction || '');
  const [taskTips, setTaskTips] = useState(data.task_tips || '');
  const [actionType, setActionType] = useState(data.action_type || 'gui');
  const [videoOpen, setVideoOpen] = useState(false);

  // Local steps for editing
  // Note: We keep empty strings to allow users to add new steps and fill them later
  const getInitialSteps = useCallback((): string[] => {
    const steps = Array.isArray(data?.steps) ? data.steps : [];
    if (steps.length) return steps.map(String);

    const detailed = Array.isArray(data?.detailed_steps) ? data.detailed_steps : [];
    if (!detailed.length) return [];

    return detailed
      .map((s: any) => s?.caption?.action || s?.caption?.observation_action_after || s?.caption?.observation_action_before)
      .filter(Boolean)
      .map(String);
  }, [data?.steps, data?.detailed_steps]);

  const [localSteps, setLocalSteps] = useState<string[]>(() => getInitialSteps());
  
  // Drag state
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const dragNodeRef = useRef<HTMLDivElement | null>(null);
  
  // Track previous node id to detect node changes
  const prevNodeIdRef = useRef<string>(node.id);

  // Reset on node change (only when switching to a different node)
  useEffect(() => {
    if (prevNodeIdRef.current !== node.id) {
      prevNodeIdRef.current = node.id;
      setTaskDescription(data.instruction || '');
      setTaskTips(data.task_tips || '');
      setActionType(data.action_type || 'gui');
      setLocalSteps(getInitialSteps());
    }
  }, [node.id, data.instruction, data.task_tips, data.action_type, getInitialSteps]);

  // Debounce updates for taskDescription
  useEffect(() => {
    const t = setTimeout(() => {
      if (data.instruction !== taskDescription) {
        onUpdate?.(node.id, { instruction: taskDescription });
      }
    }, 250);
    return () => clearTimeout(t);
  }, [taskDescription, node.id, data.instruction, onUpdate]);

  // Debounce updates for taskTips
  useEffect(() => {
    const t = setTimeout(() => {
      if (data.task_tips !== taskTips) {
        onUpdate?.(node.id, { task_tips: taskTips });
      }
    }, 250);
    return () => clearTimeout(t);
  }, [taskTips, node.id, data.task_tips, onUpdate]);

  // Debounce updates for steps
  useEffect(() => {
    const t = setTimeout(() => {
      const currentSteps = Array.isArray(data?.steps) ? data.steps : [];
      if (JSON.stringify(currentSteps) !== JSON.stringify(localSteps)) {
        onUpdate?.(node.id, { steps: localSteps });
      }
    }, 250);
    return () => clearTimeout(t);
  }, [localSteps, node.id, data?.steps, onUpdate]);

  const handleActionTypeChange = (value: string) => {
    setActionType(value);
    onUpdate?.(node.id, { action_type: value });
  };

  const handleStepChange = (idx: number, value: string) => {
    setLocalSteps((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };

  // Add a new step
  const handleAddStep = useCallback(() => {
    setLocalSteps((prev) => [...prev, '']);
  }, []);

  // Delete a step
  const handleDeleteStep = useCallback((idx: number) => {
    setLocalSteps((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  // Drag handlers
  const handleDragStart = useCallback((e: React.DragEvent, idx: number) => {
    setDragIndex(idx);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(idx));
    // Add a slight delay to show drag effect
    if (dragNodeRef.current) {
      dragNodeRef.current.style.opacity = '0.5';
    }
  }, []);

  const handleDragEnd = useCallback(() => {
    setDragIndex(null);
    setDragOverIndex(null);
    if (dragNodeRef.current) {
      dragNodeRef.current.style.opacity = '1';
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, idx: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragIndex !== null && dragIndex !== idx) {
      setDragOverIndex(idx);
    }
  }, [dragIndex]);

  const handleDragLeave = useCallback(() => {
    setDragOverIndex(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent, dropIdx: number) => {
    e.preventDefault();
    if (dragIndex === null || dragIndex === dropIdx) {
      setDragOverIndex(null);
      return;
    }

    setLocalSteps((prev) => {
      const next = [...prev];
      const [removed] = next.splice(dragIndex, 1);
      next.splice(dropIdx, 0, removed);
      return next;
    });

    setDragIndex(null);
    setDragOverIndex(null);
  }, [dragIndex]);

  const trace = data?.trace_info;
  const coverImg: string | undefined = trace?.cover_img || data?.cover_img;
  const videoUrl: string | undefined =
    trace?.video_url_externel || trace?.video_url || data?.video_url_externel || data?.video_url;
  const fallbackVideo = 'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4';
  const videoSrc = videoUrl || fallbackVideo;

  return (
    <div className="flex flex-col gap-4 flex-1 min-h-0">
      {/* Left: task text, Right: recording + parsed steps */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-0 md:[grid-template-rows:minmax(0,1fr)]">
        {/* Left */}
        <div className="flex flex-col gap-4 min-w-0 min-h-0 overflow-hidden">
          <div className="flex flex-col flex-1 min-h-0">
            <div className={FIELD_LABEL_WRAP_CLASS}>
              <span className={FIELD_LABEL_CLASS}>Instruction</span>
            </div>
            <div className="flex-1 min-h-0 relative">
              <textarea
                className={`${FIELD_TEXTAREA_CLASS} absolute inset-0`}
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                placeholder="Enter instruction for the agent..."
              />
            </div>
          </div>
        </div>

        {/* Right */}
        <div className="flex flex-col min-w-0 min-h-0 overflow-y-auto">
          {/* Header with action buttons */}
          <div className="flex items-center justify-between mb-1.5 flex-shrink-0 gap-2">
            <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider truncate flex-shrink min-w-0">Human Demonstration</span>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <button
                type="button"
                className="w-5 h-5 inline-flex items-center justify-center rounded text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
                title="Generate"
              >
                <Zap className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                className="w-5 h-5 inline-flex items-center justify-center rounded text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
                title="Info"
              >
                <Info className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setVideoOpen(true)}
                className="h-5 px-1.5 rounded text-[10px] bg-black/5 text-black/60 hover:bg-black/10 hover:text-black/90 transition-colors inline-flex items-center gap-1"
                title="Watch video"
              >
                <Video className="w-3 h-3" />
                <span className="font-medium hidden sm:inline">Watch</span>
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5 min-w-0">
            {localSteps.length > 0 && (
              <div className="flex flex-col gap-1.5">
                {localSteps.map((s, idx) => (
                  <div
                    key={idx}
                    ref={dragIndex === idx ? dragNodeRef : null}
                    draggable
                    onDragStart={(e) => handleDragStart(e, idx)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(e) => handleDragOver(e, idx)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, idx)}
                    className={`group flex items-start gap-1.5 rounded-sm transition-all ${
                      dragOverIndex === idx
                        ? 'bg-sky-50 ring-1 ring-sky-300'
                        : dragIndex === idx
                          ? 'opacity-50'
                          : ''
                    }`}
                  >
                    {/* Drag handle */}
                    <div className="flex-shrink-0 pt-[7px] cursor-grab active:cursor-grabbing text-black/20 hover:text-black/40 transition-colors">
                      <GripVertical className="w-3.5 h-3.5" />
                    </div>
                    {/* Step input with delete button inside */}
                    <div className="flex-1 relative group/input">
                      <textarea
                        rows={1}
                        className="w-full min-h-[32px] px-2 pr-7 py-[7px] text-[11px] leading-tight bg-black/5 hover:bg-black/10 border border-black/10 rounded-sm focus:outline-none focus:border-black/30 focus:bg-white placeholder:text-black/20 transition-colors resize-none overflow-hidden"
                        value={s}
                        onChange={(e) => {
                          handleStepChange(idx, e.target.value);
                          e.target.style.height = 'auto';
                          e.target.style.height = `${e.target.scrollHeight}px`;
                        }}
                        onFocus={(e) => {
                          e.target.style.height = 'auto';
                          e.target.style.height = `${e.target.scrollHeight}px`;
                        }}
                        placeholder="Describe this step..."
                      />
                      {/* Delete button inside input */}
                      <button
                        type="button"
                        onClick={() => handleDeleteStep(idx)}
                        className="absolute right-1.5 top-[6px] w-5 h-5 inline-flex items-center justify-center rounded text-black/20 opacity-0 group-hover/input:opacity-100 hover:text-red-500 hover:bg-red-50 transition-all"
                        title="Delete step"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {/* Always visible Add Step button - aligned with text inputs */}
            <div className="flex items-start gap-1.5">
              {/* Placeholder for drag handle alignment */}
              <div className="flex-shrink-0 w-3.5" />
              <button
                type="button"
                onClick={handleAddStep}
                className="flex-1 h-[32px] px-2 flex items-center justify-center gap-1.5 text-[11px] text-black/40 bg-black/5 hover:bg-black/10 rounded-sm border border-dashed border-black/15 hover:border-black/25 transition-colors cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add step</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <VideoModal
        open={videoOpen}
        title="Human Demonstration"
        src={videoSrc}
        poster={coverImg}
        onClose={() => setVideoOpen(false)}
      />
    </div>
  );
}
