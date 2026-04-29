import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import type { WorkflowNode } from '@/features/workflow';

export function IfElseNodeDetails({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  const data = node.data as any;
  const initial = useMemo(() => {
    const conds = Array.isArray(data.conditions) ? data.conditions : [];
    if (!conds.length) return [{ label: 'if', expression: '' }];
    return conds;
  }, [node.id]); // 仅在切换 node 时初始化

  const [conditions, setConditions] = useState<Array<{ label: string; expression: string }>>(initial);
  const textareaRefs = useRef<Array<HTMLTextAreaElement | null>>([]);

  useEffect(() => {
    setConditions(initial);
    textareaRefs.current = [];
  }, [node.id, initial]);

  // auto-resize for each textarea
  useEffect(() => {
    textareaRefs.current.forEach((ta) => {
      if (!ta) return;
      ta.style.height = 'auto';
      ta.style.height = `${ta.scrollHeight}px`;
    });
  }, [conditions]);

  // debounce write-back
  useEffect(() => {
    const t = setTimeout(() => {
      if (Array.isArray(data.conditions) && JSON.stringify(data.conditions) === JSON.stringify(conditions)) return;
      onUpdate?.(node.id, { conditions });
    }, 250);
    return () => clearTimeout(t);
  }, [conditions, node.id, data.conditions, onUpdate]);

  const updateExpression = (idx: number, value: string) => {
    setConditions((prev) => prev.map((c, i) => (i === idx ? { ...c, expression: value } : c)));
  };

  const addElseIf = () => {
    setConditions((prev) => [...prev, { label: 'else-if', expression: '' }]);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* If Condition */}
      <div className="flex flex-col flex-shrink-0">
        <div className="flex items-center justify-between mb-1.5 flex-shrink-0">
          <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">If Condition</span>
        </div>
        <textarea
          ref={(el) => {
            textareaRefs.current[0] = el;
          }}
          rows={1}
          className="w-full min-h-[32px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-none focus:outline-none focus:border-black/30 placeholder:text-black/20 overflow-hidden leading-relaxed"
          value={conditions[0]?.expression ?? ''}
          onChange={(e) => updateExpression(0, e.target.value)}
          placeholder="Enter if condition..."
        />
      </div>

      {/* Else If Conditions */}
      {conditions.slice(1).map((c, i) => {
        const idx = i + 1;
        return (
          <div key={idx} className="flex flex-col flex-shrink-0">
            <div className="flex items-center justify-between mb-1.5 flex-shrink-0">
              <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Else If Condition</span>
            </div>
            <textarea
              ref={(el) => {
                textareaRefs.current[idx] = el;
              }}
              rows={1}
              className="w-full min-h-[32px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-none focus:outline-none focus:border-black/30 placeholder:text-black/20 overflow-hidden leading-relaxed"
              value={c?.expression ?? ''}
              onChange={(e) => updateExpression(idx, e.target.value)}
              placeholder="Enter else-if condition..."
            />
          </div>
        );
      })}

      <button
        type="button"
        onClick={addElseIf}
        className="inline-flex items-center gap-1.5 text-[11px] text-black/50 hover:text-black/80 transition-colors self-start"
      >
        <Plus className="w-3.5 h-3.5" />
        <span>Add</span>
      </button>
    </div>
  );
}


