import { NodeData, WorkflowNode, WorkflowEdge } from '../types';

// Types for the Trace Data from Demo Parser
export interface TraceStep {
  step_idx: number;
  action: string;
  thought?: string;
  element?: any;
  screen_caption?: string;
}

export interface TraceData {
  steps: TraceStep[];
  task_description?: string;  // API 返回的字段名，转换时映射到 instruction
  app_name?: string;
}

const POSITION_X = 100;
const POSITION_Y_START = 100;
const GAP_Y = 200;

function newId(): string {
  // Prefer native crypto UUID (supported in modern browsers + Electron renderer).
  const c = (globalThis as any)?.crypto;
  if (c?.randomUUID) return c.randomUUID();
  // Fallback: not cryptographically strong, but fine for client-side graph IDs.
  return `id_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function traceToGraph(trace: TraceData): { nodes: WorkflowNode[]; edges: WorkflowEdge[] } {
  const nodes: WorkflowNode[] = [];
  const edges: WorkflowEdge[] = [];
  let currentY = POSITION_Y_START;

  // 1. Start Node
  const startId = newId();
  nodes.push({
    id: startId,
    type: 'custom',
    position: { x: POSITION_X, y: currentY },
    positionAbsolute: { x: POSITION_X, y: currentY },
    data: {
      type: 'start',
      title: 'Start',
      selected: false,
      desc: trace.task_description || 'Workflow started',
    } as NodeData,
    selected: false,
  });
  currentY += GAP_Y;

  let previousNodeId = startId;
  let previousNodeType: 'start' | 'computer-use' = 'start';

  // 2. Process Steps -> Computer Use Nodes
  if (trace.steps && trace.steps.length > 0) {
    const computerUseId = newId();
    const stepsList = trace.steps.map(s => s.action).filter(Boolean);
    
    nodes.push({
      id: computerUseId,
      type: 'custom',
      position: { x: POSITION_X, y: currentY },
      positionAbsolute: { x: POSITION_X, y: currentY },
      data: {
        type: 'computer-use',
        title: 'Computer Control',
        selected: false,
        desc: `Execute ${stepsList.length} actions based on demonstration`,
        steps: stepsList,
        instruction: trace.task_description,
      } as NodeData,
      selected: false,
    });

    edges.push({
      id: `${previousNodeId}-${computerUseId}`,
      type: 'custom',
      source: previousNodeId,
      target: computerUseId,
      // Our nodes use default handles (left=target, right=source) without ids.
      // Do NOT set handle ids here; otherwise ReactFlow can't resolve the connection.
      sourceHandle: '' as any,
      targetHandle: '' as any,
      data: { sourceType: 'start', targetType: 'computer-use', isInLoop: false },
      zIndex: 0,
    });

    previousNodeId = computerUseId;
    previousNodeType = 'computer-use';
    currentY += GAP_Y;
  }

  // 3. End Node
  const endId = newId();
  nodes.push({
    id: endId,
    type: 'custom',
    position: { x: POSITION_X, y: currentY },
    positionAbsolute: { x: POSITION_X, y: currentY },
    data: {
      type: 'end',
      title: 'End',
      selected: false,
    } as NodeData,
    selected: false,
  });

  edges.push({
    id: `${previousNodeId}-${endId}`,
    type: 'custom',
    source: previousNodeId,
    target: endId,
    sourceHandle: '' as any,
    targetHandle: '' as any,
    data: { sourceType: previousNodeType, targetType: 'end', isInLoop: false },
    zIndex: 0,
  });

  return { nodes, edges };
}

