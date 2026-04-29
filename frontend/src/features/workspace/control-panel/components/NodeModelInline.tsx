import React, { useEffect } from 'react';
import type { WorkflowNode } from '@/features/workflow';
import { InlineMenuSelect } from './node-details/InlineMenuSelect';
import type { MenuOption } from './node-details/InlineMenuSelect';
import {
  AGENT_MODELS,
  DEFAULT_MODEL,
} from './node-details/modelConfig';

export function NodeModelInline({
  node,
  onUpdate,
  options: optionsProp,
  defaultModel: defaultModelProp,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
  /** 不传则与 computer-use / tool-use 一致，使用全量 `AGENT_MODELS` */
  options?: MenuOption[];
  defaultModel?: string;
}) {
  const data = node.data as any;
  const options = optionsProp ?? AGENT_MODELS;
  const fallback = defaultModelProp ?? DEFAULT_MODEL;
  const raw = data.model || fallback;
  const model = options.some((o) => o.value === raw) ? raw : fallback;

  useEffect(() => {
    if (raw === model) return;
    onUpdate?.(node.id, { model });
  }, [raw, model, node.id, onUpdate]);

  const handleModelChange = (value: string) => {
    onUpdate?.(node.id, { model: value });
  };

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      <span className="text-[11px] text-black/40 flex-shrink-0">Model</span>
      <InlineMenuSelect
        value={model}
        options={options}
        onChange={handleModelChange}
        align="right"
      />
    </div>
  );
}
