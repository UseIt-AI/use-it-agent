import React, { useEffect, useRef, useState } from 'react';
import type { WorkflowNode } from '@/features/workflow';

export function ToolUseNodeDetails({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  const data = node.data as any;

  const [instruction, setInstruction] = useState(data.instruction || '');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setInstruction(data.instruction || '');
  }, [node.id]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [instruction]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (data.instruction !== instruction) {
        onUpdate?.(node.id, { instruction: instruction });
      }
    }, 250);
    return () => clearTimeout(t);
  }, [instruction, node.id, data.instruction, onUpdate]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col flex-shrink-0">
        <div className="flex items-center justify-between mb-1.5 flex-shrink-0">
          <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instruction</span>
        </div>
        <textarea
          ref={textareaRef}
          rows={1}
          className="w-full min-h-[32px] p-2 text-[11px] bg-black/5 hover:bg-black/10 border border-black/10 rounded-sm resize-none focus:outline-none focus:border-black/30 focus:bg-white placeholder:text-black/20 overflow-hidden leading-relaxed transition-colors"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Enter instruction for the LLM..."
        />
      </div>
    </div>
  );
}
