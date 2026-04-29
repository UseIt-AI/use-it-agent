import { useState, useCallback } from 'react';
import type { WorkflowEdge, WorkflowNode } from '../../../types';
import { generateNodeId } from '../utils/nodeFactory';

const WORKFLOW_CLIPBOARD_KEY = 'workflow-editor-node-clipboard-v1';

interface WorkflowClipboardPayload {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

interface UseClipboardOptions {
  nodes: any[];
  edges: any[];
  workflowId?: string;
  setDbNodes: (updater: any) => void;
  setDbEdges: (updater: any) => void;
  setLocalNodes: (updater: any) => void;
  setLocalEdges: (updater: any) => void;
}

function readClipboardFromStorage(): WorkflowClipboardPayload | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(WORKFLOW_CLIPBOARD_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WorkflowClipboardPayload>;
    if (!Array.isArray(parsed?.nodes) || parsed.nodes.length === 0) return null;
    return {
      nodes: parsed.nodes as WorkflowNode[],
      edges: Array.isArray(parsed.edges) ? (parsed.edges as WorkflowEdge[]) : [],
    };
  } catch {
    return null;
  }
}

function writeClipboardToStorage(payload: WorkflowClipboardPayload) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(WORKFLOW_CLIPBOARD_KEY, JSON.stringify(payload));
  } catch {
    // Ignore quota/security errors and keep in-memory clipboard working.
  }
}

/** 画布根 Start 节点不可删除，复制粘贴时也不应产生副本 */
function isRootStartNode(n: WorkflowNode): boolean {
  return n.type === 'start' || (n.data as any)?.type === 'start';
}

export function useClipboard({
  nodes,
  edges,
  workflowId,
  setDbNodes,
  setDbEdges,
  setLocalNodes,
  setLocalEdges,
}: UseClipboardOptions) {
  const [clipboard, setClipboard] = useState<WorkflowClipboardPayload | null>(() => readClipboardFromStorage());

  /**
   * 获取选中的节点
   */
  const selectedNodes = nodes.filter((n: any) => n.selected) as WorkflowNode[];

  const buildClipboardPayload = useCallback((sourceNodes: WorkflowNode[]): WorkflowClipboardPayload => {
    const sourceNodeIds = new Set(sourceNodes.map((n) => n.id));

    // When copying loop nodes, also include all their children
    const loopIds = new Set(
      sourceNodes.filter((n) => (n.data as any)?.type === 'loop').map((n) => n.id)
    );
    if (loopIds.size > 0) {
      for (const n of nodes as WorkflowNode[]) {
        if (n.parentNode && loopIds.has(n.parentNode) && !sourceNodeIds.has(n.id)) {
          sourceNodes = [...sourceNodes, n];
          sourceNodeIds.add(n.id);
        }
      }
    }

    const withoutStart = sourceNodes.filter((n) => !isRootStartNode(n));
    const finalIds = new Set(withoutStart.map((n) => n.id));

    const copiedNodes = withoutStart.map((n) => ({
      ...n,
      selected: false,
      data: { ...(n.data as any), selected: false },
    }));

    // Only keep internal edges so pasted graph stays self-contained.
    const copiedEdges = (edges as WorkflowEdge[])
      .filter((e) => finalIds.has(e.source) && finalIds.has(e.target))
      .map((e) => ({
        ...e,
        selected: false as any,
      }));

    return {
      nodes: copiedNodes,
      edges: copiedEdges,
    };
  }, [edges, nodes]);

  /**
   * 复制选中的节点
   */
  const handleCopy = useCallback(() => {
    if (!selectedNodes.length) return;
    const payload = buildClipboardPayload(selectedNodes);
    if (!payload.nodes.length) return;
    setClipboard(payload);
    writeClipboardToStorage(payload);
  }, [selectedNodes, buildClipboardPayload]);

  /**
   * 复制单个节点到剪贴板
   */
  const handleCopyNode = useCallback((nodeId: string) => {
    const node = nodes.find((n: any) => n.id === nodeId);
    if (!node) return;

    const payload = buildClipboardPayload([node as WorkflowNode]);
    if (!payload.nodes.length) return;
    setClipboard(payload);
    writeClipboardToStorage(payload);
  }, [nodes, buildClipboardPayload]);

  /**
   * 在指定位置粘贴
   */
  const handlePasteAt = useCallback((position: { x: number; y: number }) => {
    const activeClipboard = clipboard?.nodes?.length ? clipboard : readClipboardFromStorage();
    if (!activeClipboard?.nodes?.length) return;

    const nodesToPaste = activeClipboard.nodes.filter((n) => !isRootStartNode(n));
    if (!nodesToPaste.length) return;

    const allowedIds = new Set(nodesToPaste.map((n) => n.id));
    const edgesToPaste = (activeClipboard.edges || []).filter(
      (e) => allowedIds.has(e.source) && allowedIds.has(e.target)
    );

    // Only compute offset from top-level nodes (children have relative positions)
    const topLevelNodes = nodesToPaste.filter((n) => !n.parentNode);
    const positionRefNodes = topLevelNodes.length > 0 ? topLevelNodes : nodesToPaste;
    const minX = Math.min(...positionRefNodes.map((n) => n.position.x));
    const minY = Math.min(...positionRefNodes.map((n) => n.position.y));
    const nodeIdMap = new Map<string, string>();

    // First pass: generate new IDs for all nodes
    for (const n of nodesToPaste) {
      nodeIdMap.set(n.id, generateNodeId());
    }

    const pasted = nodesToPaste.map((n) => {
      const newId = nodeIdMap.get(n.id)!;
      const isChild = !!n.parentNode;

      // Child nodes keep their relative position; top-level nodes get offset
      const newPos = isChild
        ? { ...n.position }
        : { x: position.x + (n.position.x - minX), y: position.y + (n.position.y - minY) };

      return {
        ...n,
        id: newId,
        position: newPos,
        positionAbsolute: isChild ? undefined : newPos,
        selected: false,
        data: { ...(n.data as any), selected: false },
        parentNode: n.parentNode ? nodeIdMap.get(n.parentNode) : undefined,
      } as WorkflowNode;
    });

    const pastedEdges = edgesToPaste.flatMap((edge) => {
      const newSource = nodeIdMap.get(edge.source);
      const newTarget = nodeIdMap.get(edge.target);
      if (!newSource || !newTarget) return [];

      const sourceHandle = edge.sourceHandle || 'default';
      const targetHandle = edge.targetHandle || 'default';
      return [{
        ...edge,
        id: `${newSource}-${sourceHandle}-${newTarget}-${targetHandle}`,
        source: newSource,
        target: newTarget,
        sourceHandle,
        targetHandle,
        selected: false as any,
      }];
    });

    if (workflowId) {
      setDbNodes((nds: any) => [...nds, ...pasted]);
      if (pastedEdges.length > 0) {
        setDbEdges((eds: any) => [...eds, ...pastedEdges]);
      }
    } else {
      setLocalNodes((nds: any) => [...nds, ...pasted]);
      if (pastedEdges.length > 0) {
        setLocalEdges((eds: any) => [...eds, ...pastedEdges]);
      }
    }
  }, [clipboard, setDbNodes, setDbEdges, setLocalNodes, setLocalEdges, workflowId]);

  /**
   * 复制指定节点（并偏移位置）
   */
  const handleDuplicateNode = useCallback((nodeId: string) => {
    const node = nodes.find((n: any) => n.id === nodeId);
    if (!node) return;
    if (isRootStartNode(node as WorkflowNode)) return;

    const isLoop = (node as any).data?.type === 'loop';
    const nodeIdMap = new Map<string, string>();
    const newId = generateNodeId();
    nodeIdMap.set(nodeId, newId);

    const newNodes: any[] = [];

    const newNode = {
      ...node,
      id: newId,
      position: {
        x: (node as any).position.x + 50,
        y: (node as any).position.y + 50,
      },
      positionAbsolute: {
        x: (node as any).positionAbsolute?.x + 50 || (node as any).position.x + 50,
        y: (node as any).positionAbsolute?.y + 50 || (node as any).position.y + 50,
      },
      selected: false,
      data: { ...(node as any).data, selected: false },
    };
    newNodes.push(newNode);

    if (isLoop) {
      const children = nodes.filter((n: any) => n.parentNode === nodeId);
      for (const child of children) {
        const childNewId = generateNodeId();
        nodeIdMap.set(child.id, childNewId);
        newNodes.push({
          ...child,
          id: childNewId,
          position: { ...(child as any).position },
          selected: false,
          data: { ...(child as any).data, selected: false },
          parentNode: newId,
        });
      }
    }

    // Duplicate internal edges between the duplicated nodes
    const dupEdges = (edges as WorkflowEdge[])
      .filter((e) => nodeIdMap.has(e.source) && nodeIdMap.has(e.target))
      .map((e) => {
        const newSource = nodeIdMap.get(e.source)!;
        const newTarget = nodeIdMap.get(e.target)!;
        const sourceHandle = e.sourceHandle || 'default';
        const targetHandle = e.targetHandle || 'default';
        return {
          ...e,
          id: `${newSource}-${sourceHandle}-${newTarget}-${targetHandle}`,
          source: newSource,
          target: newTarget,
          sourceHandle,
          targetHandle,
          selected: false as any,
        };
      });

    if (workflowId) {
      setDbNodes((nds: any) => [...nds, ...newNodes]);
      if (dupEdges.length > 0) {
        setDbEdges((eds: any) => [...eds, ...dupEdges]);
      }
    } else {
      setLocalNodes((nds: any) => [...nds, ...newNodes]);
      if (dupEdges.length > 0) {
        setLocalEdges((eds: any) => [...eds, ...dupEdges]);
      }
    }
  }, [nodes, edges, workflowId, setDbNodes, setDbEdges, setLocalNodes, setLocalEdges]);

  return {
    clipboard,
    selectedNodes,
    handleCopy,
    handleCopyNode,
    handlePasteAt,
    handleDuplicateNode,
  };
}

