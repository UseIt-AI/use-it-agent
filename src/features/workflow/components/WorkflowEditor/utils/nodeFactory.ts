import { NODE_CONFIGS } from '../../../types';
import type { NodeData, NodeType, WorkflowNode } from '../../../types';

/**
 * 生成唯一的节点 ID
 */
export function generateNodeId(): string {
  return `${Date.now()}${Math.floor(Math.random() * 1000)}`;
}

/**
 * 根据节点类型创建节点数据
 */
export function createNodeData(type: NodeType): NodeData {
  const base = {
    type,
    title: NODE_CONFIGS[type].defaultTitle,
    desc: '',
    selected: false,
    skills: [],
  } as const;

  switch (type) {
    case 'start':
      return { ...base, type: 'start', variables: [] };
    case 'end':
      return { ...base, type: 'end', outputs: [] };
    case 'tool-use':
      return { ...base, type: 'tool-use', instruction: '' };
    case 'computer-use':
      return { ...base, type: 'computer-use', instruction: '', task_tips: '', model: 'gemini-3-flash-preview', action_type: 'gui' };
    case 'browser-use':
      return { ...base, type: 'browser-use', instruction: '' };
    case 'human-in-the-loop':
      return { ...base, type: 'human-in-the-loop', instruction: '' };
    case 'code-use':
      return { ...base, type: 'code-use', instruction: '' };
    case 'if-else':
      // 默认至少包含一个 If 条件；Else 为隐式分支
      return { ...base, type: 'if-else', conditions: [{ label: 'if', expression: '' }] };
    case 'loop':
      return { ...base, type: 'loop', max_iterations: 10 };
    case 'loop-start':
      return { ...base, type: 'loop-start', title: 'Start' };
    case 'loop-end':
      return { ...base, type: 'loop-end', title: 'End' };
    case 'mcp-use':
      return { ...base, type: 'mcp-use', instruction: '', mcp_server_name: '', mcp_function_info: '' };
    case 'agent':
      return {
        ...base,
        type: 'agent',
        instruction: '',
        groups: [],
        model: 'gemini-3-flash-preview',
      };
    default: {
      const _exhaustive: never = type;
      return _exhaustive;
    }
  }
}

/**
 * 创建完整的节点对象
 */
export function createNode(
  type: NodeType,
  position: { x: number; y: number },
  options?: {
    parentNode?: string;
    extent?: 'parent';
  }
): WorkflowNode {
  const cfg = NODE_CONFIGS[type];
  const id = generateNodeId();

  return {
    id,
    type: 'custom',
    data: createNodeData(type),
    position,
    positionAbsolute: position,
    targetPosition: type === 'start' || type === 'loop-start' ? undefined : 'left',
    sourcePosition: type === 'end' || type === 'loop-end' ? undefined : 'right',
    width: cfg.defaultWidth,
    height: cfg.defaultHeight,
    style: type === 'loop' ? { width: cfg.defaultWidth, height: cfg.defaultHeight, zIndex: -1 } : undefined,
    selected: false,
    parentNode: options?.parentNode,
    extent: options?.extent,
  };
}

/**
 * 计算 loop-start 和 loop-end 在 loop 内的固定位置
 * loop-start: 左侧垂直居中（在内容区域）
 * loop-end: 右侧垂直居中（在内容区域）
 */
export function getLoopChildFixedPosition(
  nodeType: 'loop-start' | 'loop-end',
  loopWidth: number,
  loopHeight: number
): { x: number; y: number } {
  const nodeConfig = NODE_CONFIGS[nodeType];
  const nodeWidth = nodeConfig.defaultWidth;
  const nodeHeight = nodeConfig.defaultHeight;
  
  // 边距（更小的边距，紧贴边缘）
  const marginX = 16;
  
  // Loop 标题区域高度（包含标题和一些间距）
  const loopHeaderHeight = 40;
  
  // 内容区域的高度 = 总高度 - 标题高度
  const contentHeight = loopHeight - loopHeaderHeight;
  
  // 在内容区域内垂直居中
  const centerY = loopHeaderHeight + (contentHeight - nodeHeight) / 2;
  
  if (nodeType === 'loop-start') {
    return { x: marginX, y: centerY };
  } else {
    return { x: loopWidth - nodeWidth - marginX, y: centerY };
  }
}

/**
 * 创建 Loop 节点及其内部的 Start 和 End 节点
 */
export function createLoopWithChildren(position: { x: number; y: number }): WorkflowNode[] {
  const loopId = generateNodeId();
  const cfg = NODE_CONFIGS['loop'];
  const loopWidth = cfg.defaultWidth;
  const loopHeight = cfg.defaultHeight;

  const loopNode: WorkflowNode = {
    id: loopId,
    type: 'custom',
    data: createNodeData('loop'),
    position,
    positionAbsolute: position,
    width: loopWidth,
    height: loopHeight,
    style: { width: loopWidth, height: loopHeight, zIndex: -1 },
    selected: false,
  };

  // 计算 loop-start 和 loop-end 的固定位置
  const startPos = getLoopChildFixedPosition('loop-start', loopWidth, loopHeight);
  const endPos = getLoopChildFixedPosition('loop-end', loopWidth, loopHeight);

  const startNode: WorkflowNode = {
    id: `${generateNodeId()}-start`,
    type: 'custom',
    data: createNodeData('loop-start'),
    position: startPos,
    positionAbsolute: { x: position.x + startPos.x, y: position.y + startPos.y },
    parentNode: loopId,
    extent: 'parent',
    width: NODE_CONFIGS['loop-start'].defaultWidth,
    height: NODE_CONFIGS['loop-start'].defaultHeight,
    selected: false,
    selectable: false,
    draggable: false,
    sourcePosition: 'right',
  };

  const endNode: WorkflowNode = {
    id: `${generateNodeId()}-end`,
    type: 'custom',
    data: createNodeData('loop-end'),
    position: endPos,
    positionAbsolute: { x: position.x + endPos.x, y: position.y + endPos.y },
    parentNode: loopId,
    extent: 'parent',
    targetPosition: 'left',
    width: NODE_CONFIGS['loop-end'].defaultWidth,
    height: NODE_CONFIGS['loop-end'].defaultHeight,
    selected: false,
    selectable: false,
    draggable: false,
  };

  return [loopNode, startNode, endNode];
}

