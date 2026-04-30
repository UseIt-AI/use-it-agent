import { useCallback, useEffect } from 'react';
import type { NodeType, WorkflowNode } from '../../../types';
import { NODE_CONFIGS } from '../../../types';
import { createNodeData, generateNodeId, createLoopWithChildren, getLoopChildFixedPosition } from '../utils/nodeFactory';

interface UseNodeOperationsOptions {
  nodes: any[];
  workflowId?: string;
  loading: boolean;
  setDbNodes: (updater: any) => void;
  setDbEdges: (updater: any) => void;
  setLocalNodes: (updater: any) => void;
  setLocalEdges: (updater: any) => void;
  onLocalNodesChange: (changes: any) => void;
}

export function useNodeOperations({
  nodes,
  workflowId,
  loading,
  setDbNodes,
  setDbEdges,
  setLocalNodes,
  setLocalEdges,
  onLocalNodesChange,
}: UseNodeOperationsOptions) {
  /**
   * 在指定位置添加节点
   */
  const addNodeAtPosition = useCallback((
    type: NodeType,
    position: { x: number; y: number },
    parentLoopId?: string | null
  ) => {
    const cfg = NODE_CONFIGS[type];
    const id = generateNodeId();

    let nodePosition = position;
    let parentNode: string | undefined;
    let extent: 'parent' | undefined;

    if (parentLoopId) {
      const loopNode = nodes.find((n: any) => n.id === parentLoopId);
      if (loopNode) {
        nodePosition = {
          x: position.x - (loopNode.position?.x || 0),
          y: position.y - (loopNode.position?.y || 0),
        };
        parentNode = parentLoopId;
        extent = 'parent';
      }
    }

    let nodesToAdd: WorkflowNode[];

    if (type === 'loop') {
      nodesToAdd = createLoopWithChildren(position);
    } else {
      const newNode: WorkflowNode = {
        id,
        type: 'custom',
        data: createNodeData(type),
        position: nodePosition,
        positionAbsolute: position,
        targetPosition: type === 'start' || type === 'loop-start' ? undefined : 'left',
        sourcePosition: type === 'end' || type === 'loop-end' ? undefined : 'right',
        width: cfg.defaultWidth,
        height: cfg.defaultHeight,
        selected: false,
        parentNode,
        extent,
      };
      nodesToAdd = [newNode];
    }

    if (workflowId) {
      setDbNodes((nds: any) => [...nds, ...nodesToAdd]);
    } else {
      setLocalNodes((nds: any) => [...nds, ...nodesToAdd]);
    }
  }, [nodes, workflowId, setDbNodes, setLocalNodes]);

  /**
   * 删除指定节点
   */
  const handleDeleteNode = useCallback((nodeId: string) => {
    if (workflowId) {
      setDbNodes((nds: any) => nds.filter((n: any) => n.id !== nodeId));
      setDbEdges((eds: any) => eds.filter((e: any) => e.source !== nodeId && e.target !== nodeId));
    } else {
      setLocalNodes((nds: any) => nds.filter((n: any) => n.id !== nodeId));
      setLocalEdges((eds: any) => eds.filter((e: any) => e.source !== nodeId && e.target !== nodeId));
    }
  }, [workflowId, setDbNodes, setDbEdges, setLocalNodes, setLocalEdges]);

  /**
   * 处理节点变化（React Flow 的 onNodesChange）
   */
  const handleNodesChange = useCallback((changes: any) => {
    if (workflowId) {
      setDbNodes((nds: any) => {
        let newNodes = [...nds];
        for (const change of changes) {
          if (change.type === 'position' && change.position) {
            const nodeIndex = newNodes.findIndex(n => n.id === change.id);
            if (nodeIndex !== -1) {
              const node = newNodes[nodeIndex];
              // 阻止 loop-start 和 loop-end 节点的位置变化
              if (node.data?.type === 'loop-start' || node.data?.type === 'loop-end') {
                continue;
              }
              newNodes[nodeIndex] = {
                ...newNodes[nodeIndex],
                position: change.position,
                positionAbsolute: change.position,
              };
            }
          } else if (change.type === 'dimensions' && change.dimensions) {
            const nodeIndex = newNodes.findIndex(n => n.id === change.id);
            if (nodeIndex !== -1) {
              const node = newNodes[nodeIndex];
              newNodes[nodeIndex] = {
                ...node,
                width: change.dimensions.width,
                height: change.dimensions.height,
                style: {
                  ...node.style,
                  width: change.dimensions.width,
                  height: change.dimensions.height,
                },
              };
              
              // 如果是 loop 节点大小变化，更新其子节点 (loop-start, loop-end) 的位置
              if (node.data?.type === 'loop') {
                const loopId = node.id;
                const loopWidth = change.dimensions.width;
                const loopHeight = change.dimensions.height;
                
                newNodes = newNodes.map(n => {
                  if (n.parentNode === loopId) {
                    if (n.data?.type === 'loop-start' || n.data?.type === 'loop-end') {
                      const fixedPos = getLoopChildFixedPosition(n.data.type, loopWidth, loopHeight);
                      return {
                        ...n,
                        position: fixedPos,
                        positionAbsolute: {
                          x: (node.position?.x || 0) + fixedPos.x,
                          y: (node.position?.y || 0) + fixedPos.y,
                        },
                      };
                    }
                  }
                  return n;
                });
              }
            }
          } else if (change.type === 'select') {
            const nodeIndex = newNodes.findIndex(n => n.id === change.id);
            if (nodeIndex !== -1) {
              newNodes[nodeIndex] = {
                ...newNodes[nodeIndex],
                selected: change.selected,
              };
            }
          } else if (change.type === 'remove') {
            const nodeToRemove = newNodes.find(n => n.id === change.id);
            const protectedTypes = ['start', 'loop-start', 'loop-end'];
            if (nodeToRemove && protectedTypes.includes(nodeToRemove.data?.type)) {
              return newNodes;
            }
            newNodes = newNodes.filter(n => n.id !== change.id);
          }
        }
        return newNodes;
      });
    } else {
      // 过滤掉 loop-start 和 loop-end 的位置变化
      const changesToApply = changes.filter((change: any) => {
        if (change.type === 'position') {
          const node = nodes.find((n: any) => n.id === change.id);
          if (node && (node.data?.type === 'loop-start' || node.data?.type === 'loop-end')) {
            return false;
          }
        }
        if (change.type === 'remove') {
          const node = nodes.find((n: any) => n.id === change.id);
          const protectedTypes = ['start', 'loop-start', 'loop-end'];
          if (node && protectedTypes.includes(node.data?.type)) return false;
        }
        return true;
      });
      
      // 处理 loop 节点大小变化时更新子节点位置
      const dimensionChanges = changes.filter((c: any) => c.type === 'dimensions');
      for (const change of dimensionChanges) {
        const node = nodes.find((n: any) => n.id === change.id);
        if (node?.data?.type === 'loop' && change.dimensions) {
          const loopId = node.id;
          const loopWidth = change.dimensions.width;
          const loopHeight = change.dimensions.height;
          
          // 更新 loop-start 和 loop-end 的位置
          setLocalNodes((nds: any) => nds.map((n: any) => {
            if (n.parentNode === loopId) {
              if (n.data?.type === 'loop-start' || n.data?.type === 'loop-end') {
                const fixedPos = getLoopChildFixedPosition(n.data.type, loopWidth, loopHeight);
                return {
                  ...n,
                  position: fixedPos,
                  positionAbsolute: {
                    x: (node.position?.x || 0) + fixedPos.x,
                    y: (node.position?.y || 0) + fixedPos.y,
                  },
                };
              }
            }
            return n;
          }));
        }
      }
      
      onLocalNodesChange(changesToApply);
    }
  }, [workflowId, setDbNodes, setLocalNodes, onLocalNodesChange, nodes]);

  /**
   * 确保始终存在 Start 节点
   */
  useEffect(() => {
    if (loading) return;

    const hasStartNode = nodes.some((n: any) => n.data?.type === 'start');
    if (!hasStartNode && nodes.length === 0) {
      const id = generateNodeId();
      const startNode: WorkflowNode = {
        id,
        type: 'custom',
        data: createNodeData('start'),
        position: { x: 50, y: 50 },
        positionAbsolute: { x: 50, y: 50 },
        width: NODE_CONFIGS['start'].defaultWidth,
        height: NODE_CONFIGS['start'].defaultHeight,
        selected: false,
      };

      if (workflowId) {
        setDbNodes([startNode]);
      } else {
        setLocalNodes([startNode]);
      }
    }
  }, [nodes, loading, workflowId, setDbNodes, setLocalNodes]);

  return {
    addNodeAtPosition,
    handleDeleteNode,
    handleNodesChange,
  };
}

