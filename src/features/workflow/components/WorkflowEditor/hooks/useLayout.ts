import { useCallback } from 'react';
import type { WorkflowNode, WorkflowEdge } from '../../../types';

interface UseLayoutOptions {
  nodes: any[];
  edges: any[];
  workflowId?: string;
  setDbNodes: (nodes: any) => void;
  setLocalNodes: (nodes: any) => void;
}

export function useLayout({
  nodes,
  edges,
  workflowId,
  setDbNodes,
  setLocalNodes,
}: UseLayoutOptions) {
  /**
   * 获取节点尺寸
   */
  const getNodeSize = useCallback((nodeId: string, layoutNodes: WorkflowNode[]) => {
    const DEFAULT_WIDTH = 240;
    const DEFAULT_HEIGHT = 100;

    const node = layoutNodes.find(n => n.id === nodeId);
    if (!node) return { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };

    if (node.data?.type === 'loop') {
      const w = node.width || node.style?.width || 800;
      const h = node.height || node.style?.height || 400;
      return {
        width: typeof w === 'string' ? parseInt(w, 10) : w,
        height: typeof h === 'string' ? parseInt(h, 10) : h,
      };
    }
    return {
      width: node.width || DEFAULT_WIDTH,
      height: node.height || DEFAULT_HEIGHT,
    };
  }, []);

  /**
   * BFS 分层算法
   */
  const bfsLeveling = useCallback((
    nodeIds: string[],
    adjacencyList: Map<string, string[]>,
    inDegreeMap: Map<string, number>
  ): string[][] => {
    const levels: string[][] = [];
    const queue: string[] = [];
    const visited = new Set<string>();

    // 添加入度为0的节点
    nodeIds.forEach(id => {
      if ((inDegreeMap.get(id) || 0) === 0) queue.push(id);
    });

    if (queue.length === 0 && nodeIds.length > 0) {
      queue.push(nodeIds[0]);
    }

    while (queue.length > 0) {
      const layerSize = queue.length;
      const currentLevel: string[] = [];

      for (let i = 0; i < layerSize; i++) {
        const u = queue.shift()!;
        if (visited.has(u)) continue;
        visited.add(u);
        currentLevel.push(u);

        const neighbors = adjacencyList.get(u) || [];
        for (const v of neighbors) {
          inDegreeMap.set(v, (inDegreeMap.get(v) || 0) - 1);
          if ((inDegreeMap.get(v) || 0) <= 0) {
            queue.push(v);
          }
        }
      }
      if (currentLevel.length) levels.push(currentLevel);
    }

    // 处理未访问的节点
    const unvisited = nodeIds.filter(id => !visited.has(id));
    if (unvisited.length > 0) {
      levels.push(unvisited);
    }

    return levels;
  }, []);

  /**
   * 布局 Loop 内部子节点
   */
  const layoutLoopChildren = useCallback((
    loopNode: WorkflowNode,
    layoutNodes: WorkflowNode[],
    edgeList: any[]
  ) => {
    const childNodes = layoutNodes.filter(n => n.parentNode === loopNode.id);
    if (childNodes.length === 0) return;

    // 构建子节点的邻接表
    const childAdj = new Map<string, string[]>();
    const childInDegree = new Map<string, number>();
    childNodes.forEach(n => childInDegree.set(n.id, 0));

    edgeList.forEach(e => {
      if (childInDegree.has(e.source) && childInDegree.has(e.target)) {
        if (!childAdj.has(e.source)) childAdj.set(e.source, []);
        childAdj.get(e.source)?.push(e.target);
        childInDegree.set(e.target, (childInDegree.get(e.target) || 0) + 1);
      }
    });

    const childLevels = bfsLeveling(
      childNodes.map(n => n.id),
      childAdj,
      childInDegree
    );

    // 布局参数
    const CHILD_X_GAP = 60;
    const CHILD_Y_GAP = 30;
    const PADDING_TOP = 60;
    const PADDING_LEFT = 40;
    const PADDING_RIGHT = 40;
    const PADDING_BOTTOM = 40;

    let childX = PADDING_LEFT;
    let maxChildRight = 0;
    let maxChildBottom = 0;

    childLevels.forEach((levelNodeIds) => {
      let maxWidthInLevel = 0;
      let childY = PADDING_TOP;

      levelNodeIds.forEach((nodeId) => {
        const nodeIndex = layoutNodes.findIndex(n => n.id === nodeId);
        if (nodeIndex !== -1) {
          const { width, height } = getNodeSize(nodeId, layoutNodes);

          if (width > maxWidthInLevel) {
            maxWidthInLevel = width;
          }

          layoutNodes[nodeIndex] = {
            ...layoutNodes[nodeIndex],
            position: { x: childX, y: childY },
          };

          const bottom = childY + height;
          if (bottom > maxChildBottom) {
            maxChildBottom = bottom;
          }

          childY += height + CHILD_Y_GAP;
        }
      });

      const levelRight = childX + maxWidthInLevel;
      if (levelRight > maxChildRight) {
        maxChildRight = levelRight;
      }

      childX += maxWidthInLevel + CHILD_X_GAP;
    });

    // 更新 Loop 节点尺寸
    const requiredWidth = maxChildRight + PADDING_RIGHT;
    const requiredHeight = maxChildBottom + PADDING_BOTTOM;

    const MIN_LOOP_WIDTH = 400;
    const MIN_LOOP_HEIGHT = 200;
    const newLoopWidth = Math.max(requiredWidth, MIN_LOOP_WIDTH);
    const newLoopHeight = Math.max(requiredHeight, MIN_LOOP_HEIGHT);

    const loopNodeIndex = layoutNodes.findIndex(n => n.id === loopNode.id);
    if (loopNodeIndex !== -1) {
      layoutNodes[loopNodeIndex] = {
        ...layoutNodes[loopNodeIndex],
        width: newLoopWidth,
        height: newLoopHeight,
        style: {
          ...layoutNodes[loopNodeIndex].style,
          width: newLoopWidth,
          height: newLoopHeight,
        },
      };
    }
  }, [bfsLeveling, getNodeSize]);

  /**
   * 自动布局
   */
  const handleAutoLayout = useCallback(() => {
    const layoutNodes = [...nodes] as WorkflowNode[];
    const topLevelNodes = layoutNodes.filter(n => !n.parentNode);

    if (topLevelNodes.length === 0) return;

    // 第一步：布局所有 Loop 的内部子节点
    const loopNodes = layoutNodes.filter(n => n.data?.type === 'loop');
    loopNodes.forEach(loopNode => {
      layoutLoopChildren(loopNode, layoutNodes, edges);
    });

    // 第二步：构建顶层节点的邻接表
    const adj = new Map<string, string[]>();
    const inDegree = new Map<string, number>();
    topLevelNodes.forEach(n => inDegree.set(n.id, 0));

    edges.forEach(e => {
      if (inDegree.has(e.source) && inDegree.has(e.target)) {
        if (!adj.has(e.source)) adj.set(e.source, []);
        adj.get(e.source)?.push(e.target);
        inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
      }
    });

    const levels = bfsLeveling(
      topLevelNodes.map(n => n.id),
      adj,
      inDegree
    );

    // 第三步：分配顶层节点坐标
    const X_GAP = 80;
    const Y_GAP = 40;

    let currentX = 50;

    levels.forEach((levelNodeIds) => {
      let maxWidthInLevel = 0;
      let currentY = 100;

      levelNodeIds.forEach((nodeId) => {
        const nodeIndex = layoutNodes.findIndex(n => n.id === nodeId);
        if (nodeIndex !== -1) {
          const { width, height } = getNodeSize(nodeId, layoutNodes);

          if (width > maxWidthInLevel) {
            maxWidthInLevel = width;
          }

          layoutNodes[nodeIndex] = {
            ...layoutNodes[nodeIndex],
            position: { x: currentX, y: currentY },
            positionAbsolute: { x: currentX, y: currentY },
          };

          currentY += height + Y_GAP;
        }
      });

      currentX += maxWidthInLevel + X_GAP;
    });

    if (workflowId) {
      setDbNodes(layoutNodes as any);
    } else {
      setLocalNodes(layoutNodes as any);
    }
  }, [nodes, edges, workflowId, setDbNodes, setLocalNodes, bfsLeveling, getNodeSize, layoutLoopChildren]);

  return {
    handleAutoLayout,
  };
}

