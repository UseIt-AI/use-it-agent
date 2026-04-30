import React, { useEffect, useRef, useState } from 'react';
import type { WorkflowNode } from '@/features/workflow';

function pickInstruction(data: any): string {
  // 统一使用 instruction 字段，兼容旧数据
  return (
    data?.instruction ||
    data?.query ||  // 旧 browser-use 字段
    data?.human_task_query ||  // 旧 mcp-use/human-in-the-loop 字段
    data?.task_description ||  // 旧 trace_info 字段
    data?.desc ||
    ''
  );
}

export function NodeDescriptionInput({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  // 初始值只在 ID 变化时读取一次
  const [instruction, setInstruction] = useState(() => pickInstruction(node.data));
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 切换选中 node 时，重置 state
  useEffect(() => {
    setInstruction(pickInstruction(node.data));
  }, [node.id]); // 只依赖 ID

  // Auto-resize
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [instruction]);

  // Debounce update - 统一写入 instruction 字段
  useEffect(() => {
    const t = setTimeout(() => {
      if ((node.data as any)?.instruction !== instruction) {
        onUpdate?.(node.id, { instruction });
      }
    }, 250);
    return () => clearTimeout(t);
  }, [instruction, node.id, node.data, onUpdate]);

  return (
    <div className="flex flex-col flex-shrink-0">
      <div className="flex items-center justify-between mb-1.5 flex-shrink-0">
        <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instruction</span>
      </div>
      <textarea
        ref={textareaRef}
        rows={1}
        className="w-full min-h-[32px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-none focus:outline-none focus:border-black/30 placeholder:text-black/20 overflow-hidden leading-relaxed"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        placeholder="Enter instruction..."
      />
    </div>
  );
}


