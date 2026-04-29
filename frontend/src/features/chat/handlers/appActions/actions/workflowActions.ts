/**
 * Workflow Actions
 * 
 * AI-invocable actions for creating, deleting, and editing workflows.
 * 
 * - CRUD operations (create/delete/open) call the workflow API directly.
 * - Graph operations (addNode/deleteNode/connectNodes/etc.) delegate to the
 *   WorkflowEditor's registered API via useWorkflowActionStore.
 */

import { z } from 'zod';
import appAction from '../registry';
import { useWorkflowActionStore, type WorkflowEditorApi } from '@/stores/useWorkflowActionStore';
import { workflowApi } from '@/features/workflow/api';
import { createNode, createLoopWithChildren } from '@/features/workflow/components/WorkflowEditor/utils/nodeFactory';
import { NODE_CONFIGS } from '@/features/workflow/types';
import type { NodeType, WorkflowNode, WorkflowEdge } from '@/features/workflow/types';

const ADDABLE_NODE_TYPES: NodeType[] = [
  'tool-use', 'computer-use', 'browser-use', 'end', 'if-else', 'loop',
];

function getEditorApi() {
  const api = useWorkflowActionStore.getState().editorApi;
  if (!api) {
    throw new Error('No workflow editor is currently open. Open a workflow first.');
  }
  return api;
}

/** Poll for the editor API to become available (after opening a workflow), then run a callback. */
function waitForEditor(targetWorkflowId: string, callback: (api: WorkflowEditorApi) => void, timeoutMs = 5000) {
  const interval = 300;
  let elapsed = 0;
  const poll = setInterval(() => {
    elapsed += interval;
    const api = useWorkflowActionStore.getState().editorApi;
    if (api && api.workflowId === targetWorkflowId) {
      clearInterval(poll);
      // Give React Flow a tick to finish rendering before layout
      setTimeout(() => callback(api), 500);
    } else if (elapsed >= timeoutMs) {
      clearInterval(poll);
    }
  }, interval);
}

// ==================== Workflow CRUD ====================

appAction.registerAction({
  name: 'listWorkflows',
  description: 'List all workflows owned by the current user. Returns name, ID, description, and last updated time for each.',
  handler: async () => {
    const workflows = await workflowApi.list();
    return {
      success: true,
      data: workflows.map((w) => ({
        id: w.id,
        name: w.name,
        description: w.description,
        updatedAt: w.updated_at,
      })),
    };
  },
});


appAction.registerAction({
  name: 'createWorkflow',
  description: 'Create a new workflow with the given name.',
  parameters: z.object({
    name: z.string().describe('Name for the new workflow'),
  }),
  handler: async (args) => {
    const workflow = await workflowApi.create({ name: args.name });
    window.dispatchEvent(new Event('workflow-updated'));
    return { success: true, data: { workflowId: workflow.id, name: workflow.name } };
  },
});

appAction.registerAction({
  name: 'deleteWorkflow',
  description: 'Delete a workflow by ID.',
  parameters: z.object({
    workflowId: z.string().describe('The workflow ID to delete'),
  }),
  handler: async (args) => {
    await workflowApi.delete(args.workflowId);
    window.dispatchEvent(new Event('workflow-updated'));
    return { success: true, data: { deletedWorkflowId: args.workflowId } };
  },
});

appAction.registerAction({
  name: 'renameWorkflow',
  description: 'Rename a workflow by ID.',
  parameters: z.object({
    workflowId: z.string().describe('The workflow ID to rename'),
    name: z.string().describe('New name for the workflow'),
  }),
  handler: async (args) => {
    const workflow = await workflowApi.update(args.workflowId, { name: args.name });
    window.dispatchEvent(new Event('workflow-updated'));
    return { success: true, data: { workflowId: workflow.id, name: workflow.name } };
  },
});

appAction.registerAction({
  name: 'duplicateWorkflow',
  description: 'Duplicate a workflow. Creates a copy with "(副本)" appended to the name.',
  parameters: z.object({
    workflowId: z.string().describe('The workflow ID to duplicate'),
  }),
  handler: async (args) => {
    const copy = await workflowApi.duplicate(args.workflowId);
    window.dispatchEvent(new Event('workflow-updated'));
    return { success: true, data: { workflowId: copy.id, name: copy.name } };
  },
});

appAction.registerAction({
  name: 'openWorkflow',
  description: 'Open a workflow in the editor by dispatching a custom event. The WorkspacePage listens for this event and opens the workflow tab.',
  parameters: z.object({
    workflowId: z.string().describe('The workflow ID to open in the editor'),
  }),
  handler: async (args) => {
    window.dispatchEvent(
      new CustomEvent('app-action:open-workflow', { detail: { workflowId: args.workflowId } })
    );
    return { success: true, data: { openedWorkflowId: args.workflowId } };
  },
});

// ==================== Graph Read Operations ====================

appAction.registerAction({
  name: 'getWorkflowGraph',
  description: 'Get all nodes and edges on the currently open workflow canvas. Returns node IDs, types, positions, data, and all edge connections.',
  handler: async () => {
    const api = getEditorApi();
    const nodes = api.getNodes();
    const edges = api.getEdges();
    return {
      success: true,
      data: {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: (n.data as any)?.type,
          title: (n.data as any)?.title,
          position: n.position,
          parentNode: (n as any).parentNode || null,
          width: n.width,
          height: n.height,
          data: n.data,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: (e as any).sourceHandle || null,
          targetHandle: (e as any).targetHandle || null,
        })),
      },
    };
  },
});

appAction.registerAction({
  name: 'getNodeDetail',
  description: 'Get full configuration data for a specific node by ID.',
  parameters: z.object({
    nodeId: z.string().describe('The node ID to inspect'),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    const nodes = api.getNodes();
    const node = nodes.find((n) => n.id === args.nodeId);
    if (!node) {
      return { success: false, error: `Node not found: ${args.nodeId}` };
    }
    const edges = api.getEdges();
    const incoming = edges.filter((e) => e.target === args.nodeId);
    const outgoing = edges.filter((e) => e.source === args.nodeId);
    return {
      success: true,
      data: {
        id: node.id,
        type: (node.data as any)?.type,
        title: (node.data as any)?.title,
        position: node.position,
        parentNode: (node as any).parentNode || null,
        width: node.width,
        height: node.height,
        data: node.data,
        incomingEdges: incoming.map((e) => ({ id: e.id, source: e.source, sourceHandle: (e as any).sourceHandle })),
        outgoingEdges: outgoing.map((e) => ({ id: e.id, target: e.target, targetHandle: (e as any).targetHandle })),
      },
    };
  },
});

// ==================== Graph Node Operations ====================

appAction.registerAction({
  name: 'addNode',
  description: 'Add a new node to the currently open workflow editor canvas. Returns the new node ID.',
  parameters: z.object({
    type: z.enum(['tool-use', 'computer-use', 'browser-use', 'end', 'if-else', 'loop']).describe('The node type to add'),
    position: z.object({
      x: z.number(),
      y: z.number(),
    }).describe('Canvas position. Defaults to auto-calculated position if omitted.').optional(),
    data: z.record(z.string(), z.any()).describe('Optional data to merge into the node (e.g. { instruction: "..." })').optional(),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    let position = args.position;
    if (!position) {
      const existing = api.getNodes();
      let maxX = 100;
      for (const n of existing) {
        const w = (n as any).width || NODE_CONFIGS[(n.data as any)?.type as NodeType]?.defaultWidth || 240;
        const right = n.position.x + w;
        if (right > maxX) maxX = right;
      }
      position = { x: maxX + 80, y: 200 };
    }
    if (args.type === 'loop') {
      const loopNodes = createLoopWithChildren(position);
      if (args.data) loopNodes[0].data = { ...loopNodes[0].data, ...args.data } as any;
      api.addBulkNodes(loopNodes);
      return { success: true, data: { nodeId: loopNodes[0].id, nodeType: args.type, position } };
    }
    const node = createNode(args.type as NodeType, position);
    if (args.data) node.data = { ...node.data, ...args.data } as any;
    api.addBulkNodes([node]);
    return { success: true, data: { nodeId: node.id, nodeType: args.type, position } };
  },
});

appAction.registerAction({
  name: 'deleteNode',
  description: 'Delete a node from the current workflow by its ID. Protected nodes (start, loop-start, loop-end) cannot be deleted.',
  parameters: z.object({
    nodeId: z.string().describe('The node ID to delete'),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    api.deleteNode(args.nodeId);
    return { success: true, data: { deletedNodeId: args.nodeId } };
  },
});

appAction.registerAction({
  name: 'moveNode',
  description: 'Move a node to a new position on the canvas.',
  parameters: z.object({
    nodeId: z.string().describe('The node ID to move'),
    position: z.object({
      x: z.number(),
      y: z.number(),
    }).describe('New {x, y} position'),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    const nodes = api.getNodes();
    const node = nodes.find((n) => n.id === args.nodeId);
    if (!node) {
      return { success: false, error: `Node not found: ${args.nodeId}` };
    }
    // updateNodeData only patches .data; to move we need direct node mutation via addBulkNodes trick:
    // We delete + re-add, preserving all fields except position
    api.deleteNode(args.nodeId);
    const moved = { ...node, position: args.position };
    api.addBulkNodes([moved as WorkflowNode]);
    return { success: true, data: { nodeId: args.nodeId, position: args.position } };
  },
});

appAction.registerAction({
  name: 'connectNodes',
  description: 'Create an edge between two nodes in the current workflow.',
  parameters: z.object({
    sourceId: z.string().describe('Source node ID'),
    targetId: z.string().describe('Target node ID'),
    sourceHandle: z.string().describe('Source handle ID (optional, for if-else nodes use "if", "else", "elseif-N")').optional(),
    targetHandle: z.string().describe('Target handle ID (optional)').optional(),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    api.connectNodes(args.sourceId, args.targetId, args.sourceHandle, args.targetHandle);
    return {
      success: true,
      data: { sourceId: args.sourceId, targetId: args.targetId },
    };
  },
});

appAction.registerAction({
  name: 'deleteEdge',
  description: 'Delete an edge (connection) from the current workflow by edge ID.',
  parameters: z.object({
    edgeId: z.string().describe('The edge ID to delete'),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    api.deleteEdge(args.edgeId);
    return { success: true, data: { deletedEdgeId: args.edgeId } };
  },
});

appAction.registerAction({
  name: 'updateNodeData',
  description: 'Update the configuration data of a node in the current workflow (e.g. prompt, target application, instructions).',
  parameters: z.object({
    nodeId: z.string().describe('The node ID to update'),
    data: z.record(z.string(), z.any()).describe('Key-value pairs to merge into the node data'),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    api.updateNodeData(args.nodeId, args.data);
    return { success: true, data: { nodeId: args.nodeId, updatedKeys: Object.keys(args.data) } };
  },
});

appAction.registerAction({
  name: 'autoLayout',
  description: 'Automatically arrange all nodes in the current workflow editor for a clean layout.',
  handler: async () => {
    const api = getEditorApi();
    api.autoLayout();
    return { success: true };
  },
});

appAction.registerAction({
  name: 'selectNode',
  description: 'Select a node in the workflow editor (shows its details in the control panel). Pass null to deselect.',
  parameters: z.object({
    nodeId: z.string().nullable().describe('The node ID to select, or null to deselect all'),
  }),
  handler: async (args) => {
    const api = getEditorApi();
    api.selectNode(args.nodeId);
    return { success: true, data: { selectedNodeId: args.nodeId } };
  },
});

appAction.registerAction({
  name: 'clearWorkflow',
  description: 'Clear all nodes and edges from the current workflow canvas, keeping only a single start node.',
  handler: async () => {
    const api = getEditorApi();
    const nodes = api.getNodes();
    const edges = api.getEdges();
    for (const e of edges) {
      api.deleteEdge(e.id);
    }
    for (const n of nodes) {
      const nodeType = (n.data as any)?.type;
      if (nodeType !== 'start') {
        api.deleteNode(n.id);
      }
    }
    return { success: true, data: { message: 'Canvas cleared, start node preserved' } };
  },
});

// ==================== Composite: Build / Add Nodes ====================

interface BuildNodeSpec {
  id?: string;
  type: NodeType;
  data?: Record<string, any>;
  position?: { x: number; y: number };
  /** Place this node inside a loop container (use the loop's spec id) */
  parent?: string;
  /** Connect from the preceding if-else node's handle ("if", "else", "elseif-0", ...) */
  branch?: string;
}

interface BuildEdgeSpec {
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}

const AUTO_LAYOUT_X_GAP = 80;
const AUTO_LAYOUT_Y_START = 200;
const AUTO_LAYOUT_X_START = 100;

interface BuildGraphResult {
  builtNodes: WorkflowNode[];
  builtEdges: WorkflowEdge[];
  idMap: Map<string, string>;
}

/**
 * Shared helper: builds WorkflowNode[] and WorkflowEdge[] from spec arrays.
 * Used by both buildWorkflow (new workflow) and addToWorkflow (append to canvas).
 */
function buildGraph(
  nodeSpecs: BuildNodeSpec[],
  edgeSpec: 'chain' | BuildEdgeSpec[] | undefined,
  startX: number,
  startY: number = AUTO_LAYOUT_Y_START,
): BuildGraphResult {
  const idMap = new Map<string, string>();
  const loopChildIds = new Map<string, { startId: string; endId: string }>();
  const loopContainerInfo = new Map<string, { realId: string; width: number; height: number }>();
  const builtNodes: WorkflowNode[] = [];
  let cursorX = startX;
  const loopChildCounts = new Map<string, number>();

  // First pass: top-level and loop nodes
  for (let i = 0; i < nodeSpecs.length; i++) {
    const spec = nodeSpecs[i];
    if (spec.parent) continue;
    const nodeWidth = NODE_CONFIGS[spec.type as NodeType]?.defaultWidth || 240;
    const position = spec.position || { x: cursorX, y: startY };
    cursorX = position.x + nodeWidth + AUTO_LAYOUT_X_GAP;
    const specId = spec.id || `node-${i}`;

    if (spec.type === 'loop') {
      const loopNodes = createLoopWithChildren(position);
      const loopContainer = loopNodes[0];
      const loopStart = loopNodes[1];
      const loopEnd = loopNodes[2];

      if (spec.data) {
        loopContainer.data = { ...loopContainer.data, ...spec.data } as any;
      }

      idMap.set(specId, loopContainer.id);
      loopChildIds.set(specId, { startId: loopStart.id, endId: loopEnd.id });
      idMap.set(`${specId}:start`, loopStart.id);
      idMap.set(`${specId}:end`, loopEnd.id);
      loopContainerInfo.set(specId, {
        realId: loopContainer.id,
        width: loopContainer.width || 800,
        height: loopContainer.height || 400,
      });
      loopChildCounts.set(specId, 0);

      builtNodes.push(...loopNodes);
    } else {
      const node = createNode(spec.type as NodeType, position);
      if (spec.data) {
        node.data = { ...node.data, ...spec.data } as any;
      }
      idMap.set(specId, node.id);
      builtNodes.push(node);
    }
  }

  // Second pass: resize loop containers if children need more space, then position children
  const LOOP_MARGIN_X = 16;
  const LOOP_HEADER_HEIGHT = 40;
  const CHILD_GAP = 40;
  const loopStartWidth = NODE_CONFIGS['loop-start']?.defaultWidth || 100;
  const loopEndWidth = NODE_CONFIGS['loop-end']?.defaultWidth || 100;

  // 2a: Calculate required width for each loop and resize if needed,
  //     then re-layout all top-level nodes so nothing overlaps.
  const topLevelOrder = nodeSpecs.filter(s => !s.parent);
  let anyResized = false;

  for (const [loopSpecId, info] of loopContainerInfo.entries()) {
    const children = nodeSpecs.filter(s => s.parent === loopSpecId);
    if (children.length === 0) continue;

    // Width calculation
    const totalChildrenWidth = children.reduce(
      (sum, c) => sum + (NODE_CONFIGS[c.type as NodeType]?.defaultWidth || 240),
      0,
    );
    const gaps = (children.length - 1) * CHILD_GAP;
    const requiredInner = totalChildrenWidth + gaps;
    const paddingAroundChildren = CHILD_GAP;
    const requiredWidth =
      LOOP_MARGIN_X + loopStartWidth + paddingAroundChildren +
      requiredInner +
      paddingAroundChildren + loopEndWidth + LOOP_MARGIN_X;

    // Height calculation: tallest child + header + vertical padding
    const tallestChild = Math.max(
      ...children.map((c) => NODE_CONFIGS[c.type as NodeType]?.defaultHeight || 100),
    );
    const verticalPadding = 60;
    const requiredHeight = LOOP_HEADER_HEIGHT + tallestChild + verticalPadding * 2;

    const widthChanged = requiredWidth > info.width;
    const heightChanged = requiredHeight > info.height;

    if (widthChanged) info.width = requiredWidth;
    if (heightChanged) info.height = requiredHeight;

    if (widthChanged || heightChanged) {
      anyResized = true;

      const loopNode = builtNodes.find(n => n.id === info.realId);
      if (loopNode) {
        loopNode.width = info.width;
        loopNode.height = info.height;
        loopNode.style = { ...loopNode.style as any, width: info.width, height: info.height };
      }

      // Reposition loop-start and loop-end after resize
      const childIds = loopChildIds.get(loopSpecId);
      if (childIds) {
        const contentHeight = info.height - LOOP_HEADER_HEIGHT;
        const startNode = builtNodes.find(n => n.id === childIds.startId);
        if (startNode) {
          const startH = startNode.height || NODE_CONFIGS['loop-start']?.defaultHeight || 48;
          startNode.position = {
            x: LOOP_MARGIN_X,
            y: LOOP_HEADER_HEIGHT + (contentHeight - startH) / 2,
          };
        }
        const endNode = builtNodes.find(n => n.id === childIds.endId);
        if (endNode) {
          const endH = endNode.height || NODE_CONFIGS['loop-end']?.defaultHeight || 48;
          endNode.position = {
            x: info.width - loopEndWidth - LOOP_MARGIN_X,
            y: LOOP_HEADER_HEIGHT + (contentHeight - endH) / 2,
          };
        }
      }
    }
  }

  // If any loop was resized, re-layout top-level X positions so subsequent nodes don't overlap
  if (anyResized) {
    let cx = startX;
    for (const spec of topLevelOrder) {
      if (spec.position) continue; // user-specified position, don't move
      const specId = spec.id || `node-${nodeSpecs.indexOf(spec)}`;
      const realId = idMap.get(specId);
      if (!realId) continue;
      const node = builtNodes.find(n => n.id === realId);
      if (!node) continue;

      node.position = { ...node.position, x: cx };
      const w = node.width || NODE_CONFIGS[spec.type as NodeType]?.defaultWidth || 240;
      cx = cx + w + AUTO_LAYOUT_X_GAP;
    }
    cursorX = cx;
  }

  // 2b: Position child nodes inside (now correctly sized) loops
  for (let i = 0; i < nodeSpecs.length; i++) {
    const spec = nodeSpecs[i];
    if (!spec.parent) continue;
    const specId = spec.id || `node-${i}`;
    const parentInfo = loopContainerInfo.get(spec.parent);
    const parentRealId = idMap.get(spec.parent);

    if (!parentInfo || !parentRealId) {
      const position = spec.position || { x: cursorX, y: startY };
      cursorX = position.x + (NODE_CONFIGS[spec.type as NodeType]?.defaultWidth || 240) + AUTO_LAYOUT_X_GAP;
      const node = createNode(spec.type as NodeType, position);
      if (spec.data) node.data = { ...node.data, ...spec.data } as any;
      idMap.set(specId, node.id);
      builtNodes.push(node);
      continue;
    }

    const childIdx = loopChildCounts.get(spec.parent) || 0;
    loopChildCounts.set(spec.parent, childIdx + 1);

    const nodeWidth = NODE_CONFIGS[spec.type as NodeType]?.defaultWidth || 240;
    const nodeHeight = NODE_CONFIGS[spec.type as NodeType]?.defaultHeight || 100;

    // Calculate children region: between loop-start and loop-end
    const childrenStartX = LOOP_MARGIN_X + loopStartWidth + CHILD_GAP;
    const children = nodeSpecs.filter(n => n.parent === spec.parent);
    let offsetX = 0;
    for (let j = 0; j < children.length; j++) {
      if (children[j] === spec) break;
      offsetX += (NODE_CONFIGS[children[j].type as NodeType]?.defaultWidth || 240) + CHILD_GAP;
    }
    const childX = childrenStartX + offsetX;

    const contentHeight = parentInfo.height - LOOP_HEADER_HEIGHT;
    const childY = LOOP_HEADER_HEIGHT + (contentHeight - nodeHeight) / 2;

    const relativePosition = spec.position || { x: childX, y: childY };

    const node = createNode(spec.type as NodeType, relativePosition, {
      parentNode: parentRealId,
      extent: 'parent',
    });
    if (spec.data) node.data = { ...node.data, ...spec.data } as any;
    idMap.set(specId, node.id);
    builtNodes.push(node);
  }

  // Build edges
  const builtEdges: WorkflowEdge[] = [];

  const resolveEdgeEndpoints = (srcSpecId: string, tgtSpecId: string) => {
    let srcId = idMap.get(srcSpecId) || srcSpecId;
    let tgtId = idMap.get(tgtSpecId) || tgtSpecId;

    for (const [loopSpecId, info] of loopChildIds.entries()) {
      if (srcId === info.endId) {
        const tgtNode = builtNodes.find(n => n.id === tgtId);
        const loopRealId = idMap.get(loopSpecId)!;
        if (!tgtNode || (tgtNode as any).parentNode !== loopRealId) {
          srcId = loopRealId;
        }
      }
      if (tgtId === info.startId) {
        const srcNode = builtNodes.find(n => n.id === srcId);
        const loopRealId = idMap.get(loopSpecId)!;
        if (!srcNode || (srcNode as any).parentNode !== loopRealId) {
          tgtId = loopRealId;
        }
      }
    }
    return { srcId, tgtId };
  };

  if (edgeSpec === 'chain' || edgeSpec === undefined) {
    const topLevelSpecs = nodeSpecs.filter(s => !s.parent);

    const getSpecId = (spec: BuildNodeSpec) =>
      spec.id || `node-${nodeSpecs.indexOf(spec)}`;
    const getRealId = (spec: BuildNodeSpec) => idMap.get(getSpecId(spec))!;
    const pushEdge = (srcId: string, tgtId: string, srcHandle?: string, isInLoop = false) => {
      const edgeObj: any = {
        id: `${srcId}-${srcHandle || 'out'}-${tgtId}`,
        source: srcId,
        target: tgtId,
        type: 'custom',
        data: { isInLoop },
        zIndex: 0,
      };
      if (srcHandle) edgeObj.sourceHandle = srcHandle;
      builtEdges.push(edgeObj as WorkflowEdge);
    };

    // Walk top-level specs, handling if-else branch groups
    let i = 0;
    while (i < topLevelSpecs.length) {
      const spec = topLevelSpecs[i];
      if (spec.type === 'end') { i++; continue; }

      // Check if next nodes form a branch group (have `branch` property)
      if (spec.type === 'if-else') {
        const ifElseId = getRealId(spec);
        const branchNodes: BuildNodeSpec[] = [];
        let j = i + 1;
        while (j < topLevelSpecs.length && topLevelSpecs[j].branch) {
          branchNodes.push(topLevelSpecs[j]);
          j++;
        }

        if (branchNodes.length > 0) {
          // Connect if-else → each branch node via its handle
          for (const bSpec of branchNodes) {
            pushEdge(ifElseId, getRealId(bSpec), bSpec.branch);
          }
          // Connect all branch endpoints → merge node (next non-branch node)
          if (j < topLevelSpecs.length) {
            const mergeSpec = topLevelSpecs[j];
            if (mergeSpec.type !== 'start') {
              const mergeId = getRealId(mergeSpec);
              for (const bSpec of branchNodes) {
                pushEdge(getRealId(bSpec), mergeId);
              }
            }
          }
          i = j; // skip past branch group (merge node handled on next iteration's incoming)
          continue;
        }
      }

      // Normal chain: connect this node to next non-branch node
      if (!spec.branch && i + 1 < topLevelSpecs.length) {
        const nextSpec = topLevelSpecs[i + 1];
        if (!nextSpec.branch && nextSpec.type !== 'start') {
          pushEdge(getRealId(spec), getRealId(nextSpec));
        }
      }
      i++;
    }

    // Auto-connect loop internals: loop-start → children → loop-end
    for (const [loopSpecId, info] of loopChildIds.entries()) {
      const children = nodeSpecs.filter(s => s.parent === loopSpecId);
      const childIds = children.map(c => idMap.get(c.id || `node-${nodeSpecs.indexOf(c)}`)!);
      const internalChain = [info.startId, ...childIds, info.endId];
      for (let k = 0; k < internalChain.length - 1; k++) {
        pushEdge(internalChain[k], internalChain[k + 1], undefined, true);
      }
    }
  } else if (Array.isArray(edgeSpec)) {
    for (const e of edgeSpec) {
      const { srcId, tgtId } = resolveEdgeEndpoints(e.source, e.target);
      const sh = e.sourceHandle || undefined;
      const th = e.targetHandle || undefined;
      const edgeObj: any = {
        id: `${srcId}-${sh || 'out'}-${tgtId}-${th || 'in'}`,
        source: srcId,
        target: tgtId,
        type: 'custom',
        data: { isInLoop: false },
        zIndex: 0,
      };
      if (sh) edgeObj.sourceHandle = sh;
      if (th) edgeObj.targetHandle = th;
      builtEdges.push(edgeObj as WorkflowEdge);
    }
  }

  return { builtNodes, builtEdges, idMap };
}

const nodeSpecParameters = z.object({
  id: z.string().describe('Optional user-defined ID (for referencing in edges). Auto-generated if omitted.').optional(),
  type: z.string().describe('Node type'),
  data: z.record(z.string(), z.any()).describe('Optional data to merge into the node').optional(),
  position: z.object({ x: z.number(), y: z.number() }).optional(),
  parent: z.string().describe('Place inside a loop container (use the loop spec id)').optional(),
  branch: z.string().describe('Connect from the preceding if-else node handle ("if", "else", "elseif-0", ...)').optional(),
});

const edgeSpecParameters = z.object({
  source: z.string(),
  target: z.string(),
  sourceHandle: z.string().optional(),
  targetHandle: z.string().optional(),
});

appAction.registerAction({
  name: 'buildWorkflow',
  description: `Create a complete workflow with nodes and edges in one step. Specify nodes as an array (each with a type and optional data). For edges, use "chain" to auto-connect nodes in order, or provide an explicit array of {source, target} objects. The workflow is saved to the database and opened in the editor.`,
  parameters: z.object({
    name: z.string().describe('Workflow name'),
    nodes: z.array(nodeSpecParameters).describe('Array of node specs. Must include at least a "start" node.'),
    edges: z.union([z.literal('chain'), z.array(edgeSpecParameters)]).describe('"chain" to auto-connect nodes in order, or an array of {source, target, sourceHandle?, targetHandle?}').optional(),
  }),
  handler: async (args) => {
    const { name, nodes: nodeSpecs, edges: edgeSpec } = args;

    if (!nodeSpecs || nodeSpecs.length === 0) {
      return { success: false, error: 'At least one node is required' };
    }

    const specs: BuildNodeSpec[] = nodeSpecs.map((n) => ({
      ...n,
      type: n.type as NodeType,
    }));

    const hasStart = specs.some((n) => n.type === 'start');
    if (!hasStart) {
      specs.unshift({ type: 'start' });
    }

    const { builtNodes, builtEdges } = buildGraph(specs, edgeSpec, AUTO_LAYOUT_X_START);

    const workflow = await workflowApi.create({
      name,
      definition: {
        nodes: builtNodes,
        edges: builtEdges,
        viewport: { x: 0, y: 0, zoom: 1 },
      },
    });

    window.dispatchEvent(new Event('workflow-updated'));
    window.dispatchEvent(
      new CustomEvent('app-action:open-workflow', { detail: { workflowId: workflow.id } })
    );

    const nodeList = builtNodes.map((n, i) => {
      const specId = specs[i]?.id || `node-${i}`;
      return { specId, realId: n.id, type: (n.data as any)?.type };
    });

    return {
      success: true,
      data: {
        workflowId: workflow.id,
        name: workflow.name,
        nodeCount: builtNodes.length,
        edgeCount: builtEdges.length,
        nodes: nodeList,
      },
    };
  },
});

// ==================== Composite: Add To Workflow ====================

appAction.registerAction({
  name: 'addToWorkflow',
  description: `Add nodes and edges to the currently open workflow canvas. Same node/edge format as buildWorkflow, but appends to the existing graph instead of creating a new workflow. Optionally connect the first new node to an existing node via connectTo.`,
  parameters: z.object({
    nodes: z.array(nodeSpecParameters).describe('Array of node specs to add.'),
    edges: z.union([z.literal('chain'), z.array(edgeSpecParameters)]).describe('"chain" to auto-connect new nodes in order, or an array of edge specs. Defaults to "chain".').optional(),
    connectTo: z.object({
      nodeId: z.string().describe('Existing node ID to connect FROM'),
      handle: z.string().describe('Source handle on the existing node (optional)').optional(),
    }).describe('Optional: connect an existing canvas node to the first new node.').optional(),
  }),
  handler: async (args) => {
    const { nodes: nodeSpecs, edges: edgeSpec, connectTo } = args;

    if (!nodeSpecs || nodeSpecs.length === 0) {
      return { success: false, error: 'At least one node is required' };
    }

    const specs: BuildNodeSpec[] = nodeSpecs.map((n) => ({
      ...n,
      type: n.type as NodeType,
    }));

    const api = getEditorApi();

    const existingNodes = api.getNodes();
    let maxX = AUTO_LAYOUT_X_START;
    for (const n of existingNodes) {
      const w = (n as any).width || NODE_CONFIGS[(n.data as any)?.type as NodeType]?.defaultWidth || 240;
      const right = n.position.x + w;
      if (right > maxX) maxX = right;
    }
    const startX = maxX + AUTO_LAYOUT_X_GAP;

    const { builtNodes, builtEdges, idMap } = buildGraph(specs, edgeSpec, startX);

    // Bridge edge: connect an existing node to the first new top-level node
    if (connectTo) {
      const firstTopSpec = specs.find(s => !s.parent);
      if (firstTopSpec) {
        const firstSpecId = firstTopSpec.id || `node-${specs.indexOf(firstTopSpec)}`;
        const firstRealId = idMap.get(firstSpecId);
        if (firstRealId) {
          const bridgeEdge: any = {
            id: `${connectTo.nodeId}-${firstRealId}`,
            source: connectTo.nodeId,
            target: firstRealId,
            type: 'custom',
            data: { isInLoop: false },
            zIndex: 0,
          };
          if (connectTo.handle) bridgeEdge.sourceHandle = connectTo.handle;
          builtEdges.unshift(bridgeEdge);
        }
      }
    }

    api.addBulkNodes(builtNodes);
    api.addBulkEdges(builtEdges);

    const nodeList = builtNodes.map((n, i) => {
      const specId = specs[i]?.id || `node-${i}`;
      return { specId, realId: n.id, type: (n.data as any)?.type };
    });

    return {
      success: true,
      data: {
        addedNodeCount: builtNodes.length,
        addedEdgeCount: builtEdges.length,
        nodes: nodeList,
      },
    };
  },
});
