import React, { useEffect, useRef, useState } from 'react';
import { Globe, MousePointer2, Code } from 'lucide-react';
import type { WorkflowNode } from '@/features/workflow';

type CapabilityItem = {
  value: string;
  label: string;
  /** File name under public/node/<logo>.svg — used for colored software logos */
  logo?: string;
  /** lucide-react icon component — used for generic capabilities */
  Icon?: React.ComponentType<{ className?: string }>;
};

const AVAILABLE_CAPABILITIES: CapabilityItem[] = [
  { value: 'gui',     label: 'KBM',     Icon: MousePointer2 },
  { value: 'ppt',     label: 'PPT',     logo: 'ppt' },
  { value: 'word',    label: 'Word',    logo: 'word' },
  { value: 'excel',   label: 'Excel',   logo: 'excel' },
  { value: 'autocad', label: 'AutoCAD', logo: 'autocad' },
  { value: 'browser', label: 'Browser', Icon: Globe },
  { value: 'code',    label: 'Code',    Icon: Code },
];

export function AgentNodeDetails({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  const data = node.data as any;

  const [instruction, setInstruction] = useState<string>(data.instruction || '');
  const [groups, setGroups] = useState<string[]>(data.groups || []);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setInstruction(data.instruction || '');
    setGroups(data.groups || []);
  }, [node.id]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [instruction]);

  useEffect(() => {
    const t = setTimeout(() => {
      const patch: Record<string, any> = {};
      if ((data.instruction || '') !== instruction) {
        patch.instruction = instruction;
      }
      if (JSON.stringify(data.groups || []) !== JSON.stringify(groups)) {
        patch.groups = groups;
      }
      if (Object.keys(patch).length > 0) {
        onUpdate?.(node.id, patch);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [instruction, groups, node.id, data.instruction, data.groups, onUpdate]);

  const toggle = (v: string) => {
    setGroups((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col flex-shrink-0">
        <div className="flex items-center justify-between mb-1.5 flex-shrink-0">
          <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">
            Instruction
          </span>
        </div>
        <textarea
          ref={textareaRef}
          rows={1}
          className="w-full min-h-[32px] p-2 text-[11px] bg-black/5 hover:bg-black/10 border border-black/10 rounded-sm resize-none focus:outline-none focus:border-black/30 focus:bg-white placeholder:text-black/20 overflow-hidden leading-relaxed transition-colors"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="e.g. 把 PPT 切到前台"
        />
      </div>

      <div className="flex flex-col flex-shrink-0">
        <div className="flex items-baseline gap-2 mb-2 flex-shrink-0">
          <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">
            Allowed Capabilities
          </span>
          <span className="text-[10px] text-black/50 lowercase tracking-normal">
            empty = all allowed
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {AVAILABLE_CAPABILITIES.map((cap) => {
            const active = groups.includes(cap.value);
            const IconComp = cap.Icon;
            return (
              <button
                key={cap.value}
                type="button"
                onClick={() => toggle(cap.value)}
                aria-pressed={active}
                className={`inline-flex items-center gap-1.5 h-7 pl-2 pr-2.5 rounded-full text-[11px] font-medium transition-colors ${
                  active
                    ? 'bg-amber-500/10 text-amber-700 hover:bg-amber-500/15'
                    : 'bg-transparent text-black/45 hover:bg-black/5 hover:text-black/75'
                }`}
              >
                {cap.logo ? (
                  <img
                    src={`${import.meta.env.BASE_URL}node/${cap.logo}.svg`}
                    alt=""
                    aria-hidden
                    className={`w-4 h-4 object-contain flex-shrink-0 transition-opacity ${active ? 'opacity-100' : 'opacity-60'}`}
                  />
                ) : IconComp ? (
                  <IconComp className="w-4 h-4 flex-shrink-0" />
                ) : null}
                <span className="leading-none">{cap.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
