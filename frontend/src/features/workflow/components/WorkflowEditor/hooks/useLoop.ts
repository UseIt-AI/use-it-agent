import { useCallback, useState } from 'react';
import type { WorkflowNode, NodeType } from '../../../types';
import { NODE_CONFIGS } from '../../../types';
import { getLoopChildFixedPosition } from '../utils/nodeFactory';

/**
 * 获取节点的实际尺寸
 * 优先使用 React Flow 测量的实际值（node.width/height），
 * 如果没有则使用配置的默认值
 * 
 * 注意：React Flow 会在节点渲染后通过 dimensions 变化事件更新 width/height
 */
const getNodeDimensions = (node: any): { width: number; height: number } => {
  // React Flow 测量后会将实际尺寸存储在 width/height 属性中
  // 也检查 measured 属性（某些版本的 React Flow 使用这个）
  const width = node.width || node.measured?.width;
  const height = node.height || node.measured?.height;
  
  // 如果有测量值，直接使用
  if (width && height) {
    return { width, height };
  }
  
  // 否则使用配置的默认值
  const nodeType = (node.data?.type || node.type || 'llm') as NodeType;
  const config = NODE_CONFIGS[nodeType] || NODE_CONFIGS['llm'];
  
  return {
    width: width || config.defaultWidth,
    height: height || config.defaultHeight,
  };
};

interface UseLoopOptions {
  nodes: any[];
  workflowId?: string;
  setDbNodes: (updater: any) => void;
  setDbEdges: (updater: any) => void;
  setLocalNodes: (updater: any) => void;
  setLocalEdges: (updater: any) => void;
  selectedNodes?: WorkflowNode[];
}

// 当前高亮的 Loop ID（用于拖拽时的视觉反馈）
let highlightedLoopId: string | null = null;

export function useLoop({
  nodes,
  workflowId,
  setDbNodes,
  setDbEdges,
  setLocalNodes,
  setLocalEdges,
  selectedNodes = [],
}: UseLoopOptions) {
  /**
   * 检查节点是否完全在某个 Loop 节点内部
   * @param node 要检查的节点
   * @param allNodes 所有节点
   * @param includeCurrentParent 是否也检查当前的 parentNode
   */
  const checkNodeInLoop = useCallback((
    node: any,
    allNodes: any[],
    includeCurrentParent: boolean = false
  ) => {
    if (!node || node.data?.type === 'loop') return null;

    const nodeX = node.positionAbsolute?.x ?? node.position?.x ?? 0;
    const nodeY = node.positionAbsolute?.y ?? node.position?.y ?? 0;
    const nodeWidth = node.width || 240;
    const nodeHeight = node.height || 100;

    for (const loopNode of allNodes) {
      if (loopNode.data?.type !== 'loop') continue;
      if (!includeCurrentParent && loopNode.id === node.parentNode) continue;

      const loopX = loopNode.position?.x ?? 0;
      const loopY = loopNode.position?.y ?? 0;
      const loopWidth = loopNode.width || loopNode.style?.width || 800;
      const loopHeight = loopNode.height || loopNode.style?.height || 400;

      const isInside = (
        nodeX >= loopX &&
        nodeY >= loopY &&
        nodeX + nodeWidth <= loopX + loopWidth &&
        nodeY + nodeHeight <= loopY + loopHeight
      );

      if (isInside) {
        return loopNode;
      }
    }

    return null;
  }, []);

  /**
   * 处理节点进入/离开 Loop
   */
  const handleNodeLoopChange = useCallback((
    nodeId: string,
    newParentLoopId: string | null,
    nodePosition: { x: number; y: number },
    oldParentLoopId?: string | null,
    isLoopSpecialNode: boolean = false,
    nodeWidth?: number,
    nodeHeight?: number
  ) => {
    /**
     * 计算需要的 loop 大小和位置调整以包含新节点
     * 返回新的位置、尺寸，以及位置偏移量（用于调整子节点的相对位置）
     */
    const calculateRequiredLoopBounds = (
      loopNode: any,
      newNodePos: { x: number; y: number },
      newNodeWidth: number,
      newNodeHeight: number,
      allNodes: any[]
    ): { 
      newPosition: { x: number; y: number }; 
      newWidth: number; 
      newHeight: number;
      positionOffset: { x: number; y: number };
    } | null => {
      const loopX = loopNode.position?.x || 0;
      const loopY = loopNode.position?.y || 0;
      const currentWidth = loopNode.width || loopNode.style?.width || NODE_CONFIGS['loop'].defaultWidth;
      const currentHeight = loopNode.height || loopNode.style?.height || NODE_CONFIGS['loop'].defaultHeight;

      // 获取 loop-start 和 loop-end 的宽度用于计算边距
      const loopStartWidth = NODE_CONFIGS['loop-start'].defaultWidth;
      const loopEndWidth = NODE_CONFIGS['loop-end'].defaultWidth;
      
      // 边距
      const marginLeft = 16 + loopStartWidth + 40;
      const marginRight = 16 + loopEndWidth + 40;
      const marginTop = 60;
      const marginBottom = 40;

      // 收集已有的子节点（排除正在拖入的节点）
      const existingChildren = allNodes.filter(
        (n: any) => n.parentNode === loopNode.id && 
                    n.data?.type !== 'loop-start' && 
                    n.data?.type !== 'loop-end' &&
                    n.id !== nodeId
      );

      // 计算边界（使用绝对坐标）
      let minX = newNodePos.x;
      let minY = newNodePos.y;
      let maxX = newNodePos.x + newNodeWidth;
      let maxY = newNodePos.y + newNodeHeight;

      for (const child of existingChildren) {
        const childAbsX = loopX + (child.position?.x || 0);
        const childAbsY = loopY + (child.position?.y || 0);
        const { width: childWidth, height: childHeight } = getNodeDimensions(child);
        minX = Math.min(minX, childAbsX);
        minY = Math.min(minY, childAbsY);
        maxX = Math.max(maxX, childAbsX + childWidth);
        maxY = Math.max(maxY, childAbsY + childHeight);
      }

      // 计算 Loop 需要的新边界
      // 新的左上角位置：考虑节点可能在 Loop 左边或上边
      const newLoopX = Math.min(loopX, minX - marginLeft);
      const newLoopY = Math.min(loopY, minY - marginTop);
      
      // 新的右下角位置：考虑节点可能在 Loop 右边或下边
      const currentRight = loopX + currentWidth;
      const currentBottom = loopY + currentHeight;
      const newRight = Math.max(currentRight, maxX + marginRight);
      const newBottom = Math.max(currentBottom, maxY + marginBottom);
      
      // 计算最小高度：确保 loop-start/loop-end 能够显示
      // marginTop(60) + loop-start/end 高度(48) + marginBottom(40) = 148
      // 使用 200 作为最小高度，让 Loop 不那么拥挤
      const minLoopHeight = 200;
      
      // 计算新的尺寸
      const newWidth = Math.max(newRight - newLoopX, NODE_CONFIGS['loop'].defaultWidth);
      const newHeight = Math.max(newBottom - newLoopY, minLoopHeight);
      
      // 计算位置偏移量（Loop 移动了多少，子节点需要相应调整）
      const positionOffset = {
        x: loopX - newLoopX,  // 如果 Loop 向左移动，偏移为正数
        y: loopY - newLoopY,  // 如果 Loop 向上移动，偏移为正数
      };

      // 检查是否有变化
      const hasChange = 
        newLoopX !== loopX || 
        newLoopY !== loopY || 
        newWidth !== currentWidth || 
        newHeight !== currentHeight;

      if (!hasChange) return null;

      return {
        newPosition: { x: newLoopX, y: newLoopY },
        newWidth,
        newHeight,
        positionOffset,
      };
    };

    const updateNodes = (nds: any[]) => {
      // 如果是进入 loop，先计算需要的边界调整
      let loopBoundsChange: ReturnType<typeof calculateRequiredLoopBounds> = null;
      let originalLoopNode: any = null;
      
      if (newParentLoopId && !isLoopSpecialNode) {
        originalLoopNode = nds.find((ln: any) => ln.id === newParentLoopId);
        const draggedNode = nds.find((n: any) => n.id === nodeId);
        if (originalLoopNode && draggedNode) {
          const nWidth = nodeWidth || draggedNode.width || 240;
          const nHeight = nodeHeight || draggedNode.height || 100;
          loopBoundsChange = calculateRequiredLoopBounds(originalLoopNode, nodePosition, nWidth, nHeight, nds);
        }
      }

      // 获取 Loop 的新位置（如果有变化）或原位置
      const loopNewX = loopBoundsChange?.newPosition.x ?? originalLoopNode?.position?.x ?? 0;
      const loopNewY = loopBoundsChange?.newPosition.y ?? originalLoopNode?.position?.y ?? 0;

      let result = nds.map((n: any) => {
        // 处理拖入的节点
        if (n.id === nodeId) {
          if (newParentLoopId) {
            // 计算相对于 Loop 新位置的相对坐标
            const relativePosition = {
              x: nodePosition.x - loopNewX,
              y: nodePosition.y - loopNewY,
            };

            return {
              ...n,
              position: relativePosition,
              positionAbsolute: nodePosition,
              parentNode: newParentLoopId,
              ...(isLoopSpecialNode ? { extent: 'parent' as const } : {}),
            };
          } else {
            const { parentNode, extent, ...rest } = n;
            return {
              ...rest,
              position: nodePosition,
              positionAbsolute: nodePosition,
            };
          }
        }

        // 处理 Loop 节点本身
        if (newParentLoopId && n.id === newParentLoopId && loopBoundsChange) {
          return {
            ...n,
            position: loopBoundsChange.newPosition,
            positionAbsolute: loopBoundsChange.newPosition,
            width: loopBoundsChange.newWidth,
            height: loopBoundsChange.newHeight,
            style: {
              ...n.style,
              width: loopBoundsChange.newWidth,
              height: loopBoundsChange.newHeight,
            },
          };
        }

        // 处理 Loop 内已有的子节点（需要调整相对位置，因为 Loop 位置可能变了）
        if (newParentLoopId && n.parentNode === newParentLoopId && loopBoundsChange) {
          const positionOffset = loopBoundsChange.positionOffset;
          
          if (n.data?.type === 'loop-start' || n.data?.type === 'loop-end') {
            // loop-start 和 loop-end 使用固定位置
            const fixedPos = getLoopChildFixedPosition(
              n.data.type, 
              loopBoundsChange.newWidth, 
              loopBoundsChange.newHeight
            );
            return {
              ...n,
              position: fixedPos,
              positionAbsolute: {
                x: loopNewX + fixedPos.x,
                y: loopNewY + fixedPos.y,
              },
            };
          } else {
            // 其他子节点：调整相对位置以保持绝对位置不变
            const newRelativePosition = {
              x: (n.position?.x || 0) + positionOffset.x,
              y: (n.position?.y || 0) + positionOffset.y,
            };
            return {
              ...n,
              position: newRelativePosition,
              positionAbsolute: {
                x: loopNewX + newRelativePosition.x,
                y: loopNewY + newRelativePosition.y,
              },
            };
          }
        }

        return n;
      });

      return result;
    };

    const updateEdges = (eds: any[], nds: any[]) => {
      let filteredEdges = eds.filter((edge: any) => {
        const isSourceNode = edge.source === nodeId;
        const isTargetNode = edge.target === nodeId;

        if (!isSourceNode && !isTargetNode) return true;

        const otherNodeId = isSourceNode ? edge.target : edge.source;
        const otherNode = nds.find((n: any) => n.id === otherNodeId);

        if (!otherNode) return true;

        const otherParent = otherNode.parentNode;

        if (newParentLoopId) {
          if (otherParent !== newParentLoopId) {
            return false;
          }
        } else if (oldParentLoopId) {
          if (otherParent === oldParentLoopId) {
            return false;
          }
        }

        return true;
      });

      // 如果是进入 loop，检查是否需要自动连接 loop-start 和 loop-end
      if (newParentLoopId && !isLoopSpecialNode) {
        // 检查 loop 内是否只有 loop-start 和 loop-end（没有其他业务节点）
        const loopChildren = nds.filter(
          (n: any) => n.parentNode === newParentLoopId && 
                      n.data?.type !== 'loop-start' && 
                      n.data?.type !== 'loop-end' &&
                      n.id !== nodeId
        );
        
        // 如果 loop 原本是空的（只有 loop-start 和 loop-end）
        const isLoopEmpty = loopChildren.length === 0;
        
        if (isLoopEmpty) {
          // 找到 loop-start 和 loop-end 节点
          const loopStartNode = nds.find(
            (n: any) => n.parentNode === newParentLoopId && n.data?.type === 'loop-start'
          );
          const loopEndNode = nds.find(
            (n: any) => n.parentNode === newParentLoopId && n.data?.type === 'loop-end'
          );
          
          if (loopStartNode && loopEndNode) {
            // 检查是否已经有连接
            const hasStartConnection = filteredEdges.some(
              (e: any) => e.source === loopStartNode.id && e.target === nodeId
            );
            const hasEndConnection = filteredEdges.some(
              (e: any) => e.source === nodeId && e.target === loopEndNode.id
            );
            
            // 创建 loop-start -> 拖入节点 的连线
            if (!hasStartConnection) {
              const startEdge = {
                id: `${loopStartNode.id}-default-${nodeId}-default`,
                source: loopStartNode.id,
                target: nodeId,
                sourceHandle: 'default',
                targetHandle: 'default',
                type: 'custom',
                data: { isInLoop: true },
                zIndex: 0,
              };
              filteredEdges.push(startEdge);
            }
            
            // 创建 拖入节点 -> loop-end 的连线
            if (!hasEndConnection) {
              const endEdge = {
                id: `${nodeId}-default-${loopEndNode.id}-default`,
                source: nodeId,
                target: loopEndNode.id,
                sourceHandle: 'default',
                targetHandle: 'default',
                type: 'custom',
                data: { isInLoop: true },
                zIndex: 0,
              };
              filteredEdges.push(endEdge);
            }
          }
        }
      }

      return filteredEdges;
    };

    if (workflowId) {
      setDbNodes((nds: any) => {
        const updatedNodes = updateNodes(nds);
        setDbEdges((eds: any) => updateEdges(eds, updatedNodes));
        return updatedNodes;
      });
    } else {
      setLocalNodes((nds: any) => {
        const updatedNodes = updateNodes(nds);
        setLocalEdges((eds: any) => updateEdges(eds, updatedNodes));
        return updatedNodes;
      });
    }
  }, [workflowId, setDbNodes, setDbEdges, setLocalNodes, setLocalEdges]);

  /**
   * 批量处理多个节点进入/离开 Loop
   * @param nodeInfos 节点信息数组，每个包含 nodeId, position, oldParentLoopId, width, height
   * @param newParentLoopId 目标 loop 的 id，null 表示离开 loop
   */
  const handleBatchNodeLoopChange = useCallback((
    nodeInfos: Array<{
      nodeId: string;
      position: { x: number; y: number };
      width?: number;
      height?: number;
      oldParentLoopId?: string | null;
    }>,
    newParentLoopId: string | null
  ) => {
    const nodeIdSet = new Set(nodeInfos.map(info => info.nodeId));
    const nodePositionMap = new Map(nodeInfos.map(info => [info.nodeId, info.position]));

    /**
     * 计算需要的 loop 大小和位置调整以包含所有子节点
     * 返回新的位置、尺寸，以及位置偏移量（用于调整子节点的相对位置）
     */
    const calculateRequiredLoopBounds = (
      loopNode: any,
      nodesToAdd: typeof nodeInfos,
      allNodes: any[]
    ): { 
      newPosition: { x: number; y: number }; 
      newWidth: number; 
      newHeight: number;
      positionOffset: { x: number; y: number };
    } | null => {
      const loopX = loopNode.position?.x || 0;
      const loopY = loopNode.position?.y || 0;
      const currentWidth = loopNode.width || loopNode.style?.width || NODE_CONFIGS['loop'].defaultWidth;
      const currentHeight = loopNode.height || loopNode.style?.height || NODE_CONFIGS['loop'].defaultHeight;

      // 获取 loop-start 和 loop-end 的宽度用于计算边距
      const loopStartWidth = NODE_CONFIGS['loop-start'].defaultWidth;
      const loopEndWidth = NODE_CONFIGS['loop-end'].defaultWidth;
      
      // 边距：左右各留出 loop-start/loop-end 的空间 + 额外间距
      const marginLeft = 16 + loopStartWidth + 40; // 16 是 loop-start 离左边的距离
      const marginRight = 16 + loopEndWidth + 40;  // 16 是 loop-end 离右边的距离
      const marginTop = 60;    // 顶部边距（包含 loop header）
      const marginBottom = 40; // 底部边距

      // 收集所有需要考虑的节点（新加入的 + 已有的子节点，排除正在拖入的节点）
      const existingChildren = allNodes.filter(
        (n: any) => n.parentNode === loopNode.id && 
                    n.data?.type !== 'loop-start' && 
                    n.data?.type !== 'loop-end' &&
                    !nodeIdSet.has(n.id)
      );

      // 计算所有节点的边界（使用绝对坐标）
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

      // 新加入的节点 - 需要从 allNodes 中获取完整节点信息来得到正确的尺寸
      for (const info of nodesToAdd) {
        const fullNode = allNodes.find((n: any) => n.id === info.nodeId);
        const { width: nodeWidth, height: nodeHeight } = fullNode 
          ? getNodeDimensions(fullNode)
          : { width: info.width || 240, height: info.height || 160 };
        minX = Math.min(minX, info.position.x);
        minY = Math.min(minY, info.position.y);
        maxX = Math.max(maxX, info.position.x + nodeWidth);
        maxY = Math.max(maxY, info.position.y + nodeHeight);
      }

      // 已有的子节点
      for (const child of existingChildren) {
        const childAbsX = loopX + (child.position?.x || 0);
        const childAbsY = loopY + (child.position?.y || 0);
        const { width: childWidth, height: childHeight } = getNodeDimensions(child);
        minX = Math.min(minX, childAbsX);
        minY = Math.min(minY, childAbsY);
        maxX = Math.max(maxX, childAbsX + childWidth);
        maxY = Math.max(maxY, childAbsY + childHeight);
      }

      // 如果没有节点，不需要调整
      if (minX === Infinity) return null;

      // 计算 Loop 需要的新边界
      // 新的左上角位置：考虑节点可能在 Loop 左边或上边
      const newLoopX = Math.min(loopX, minX - marginLeft);
      const newLoopY = Math.min(loopY, minY - marginTop);
      
      // 新的右下角位置：考虑节点可能在 Loop 右边或下边
      const currentRight = loopX + currentWidth;
      const currentBottom = loopY + currentHeight;
      const newRight = Math.max(currentRight, maxX + marginRight);
      const newBottom = Math.max(currentBottom, maxY + marginBottom);
      
      // 计算最小高度：确保 loop-start/loop-end 能够显示
      // marginTop(60) + loop-start/end 高度(48) + marginBottom(40) = 148
      // 使用 200 作为最小高度，让 Loop 不那么拥挤
      const minLoopHeight = 200;
      
      // 计算新的尺寸
      const newWidth = Math.max(newRight - newLoopX, NODE_CONFIGS['loop'].defaultWidth);
      const newHeight = Math.max(newBottom - newLoopY, minLoopHeight);
      
      // 计算位置偏移量（Loop 移动了多少，子节点需要相应调整）
      const positionOffset = {
        x: loopX - newLoopX,  // 如果 Loop 向左移动，偏移为正数
        y: loopY - newLoopY,  // 如果 Loop 向上移动，偏移为正数
      };

      // 检查是否有变化
      const hasChange = 
        newLoopX !== loopX || 
        newLoopY !== loopY || 
        newWidth !== currentWidth || 
        newHeight !== currentHeight;

      if (!hasChange) return null;

      return {
        newPosition: { x: newLoopX, y: newLoopY },
        newWidth,
        newHeight,
        positionOffset,
      };
    };

    const updateNodes = (nds: any[]) => {
      // 如果是进入 loop，先计算需要的边界调整
      let loopBoundsChange: ReturnType<typeof calculateRequiredLoopBounds> = null;
      let originalLoopNode: any = null;
      
      if (newParentLoopId) {
        originalLoopNode = nds.find((ln: any) => ln.id === newParentLoopId);
        if (originalLoopNode) {
          loopBoundsChange = calculateRequiredLoopBounds(originalLoopNode, nodeInfos, nds);
        }
      }

      // 获取 Loop 的新位置（如果有变化）或原位置
      const loopNewX = loopBoundsChange?.newPosition.x ?? originalLoopNode?.position?.x ?? 0;
      const loopNewY = loopBoundsChange?.newPosition.y ?? originalLoopNode?.position?.y ?? 0;

      let result = nds.map((n: any) => {
        // 处理拖入的节点
        if (nodeIdSet.has(n.id)) {
          const nodePosition = nodePositionMap.get(n.id)!;

          if (newParentLoopId) {
            // 计算相对于 Loop 新位置的相对坐标
            const relativePosition = {
              x: nodePosition.x - loopNewX,
              y: nodePosition.y - loopNewY,
            };

            return {
              ...n,
              position: relativePosition,
              positionAbsolute: nodePosition,
              parentNode: newParentLoopId,
            };
          } else {
            const { parentNode, extent, ...rest } = n;
            return {
              ...rest,
              position: nodePosition,
              positionAbsolute: nodePosition,
            };
          }
        }

        // 处理 Loop 节点本身
        if (newParentLoopId && n.id === newParentLoopId && loopBoundsChange) {
          return {
            ...n,
            position: loopBoundsChange.newPosition,
            positionAbsolute: loopBoundsChange.newPosition,
            width: loopBoundsChange.newWidth,
            height: loopBoundsChange.newHeight,
            style: {
              ...n.style,
              width: loopBoundsChange.newWidth,
              height: loopBoundsChange.newHeight,
            },
          };
        }

        // 处理 Loop 内已有的子节点（需要调整相对位置，因为 Loop 位置可能变了）
        if (newParentLoopId && n.parentNode === newParentLoopId && loopBoundsChange) {
          const positionOffset = loopBoundsChange.positionOffset;
          
          if (n.data?.type === 'loop-start' || n.data?.type === 'loop-end') {
            // loop-start 和 loop-end 使用固定位置
            const fixedPos = getLoopChildFixedPosition(
              n.data.type, 
              loopBoundsChange.newWidth, 
              loopBoundsChange.newHeight
            );
            return {
              ...n,
              position: fixedPos,
              positionAbsolute: {
                x: loopNewX + fixedPos.x,
                y: loopNewY + fixedPos.y,
              },
            };
          } else {
            // 其他子节点：调整相对位置以保持绝对位置不变
            const newRelativePosition = {
              x: (n.position?.x || 0) + positionOffset.x,
              y: (n.position?.y || 0) + positionOffset.y,
            };
            return {
              ...n,
              position: newRelativePosition,
              positionAbsolute: {
                x: loopNewX + newRelativePosition.x,
                y: loopNewY + newRelativePosition.y,
              },
            };
          }
        }

        return n;
      });

      return result;
    };

    const updateEdges = (eds: any[], nds: any[]) => {
      let filteredEdges = eds.filter((edge: any) => {
        const isSourceInBatch = nodeIdSet.has(edge.source);
        const isTargetInBatch = nodeIdSet.has(edge.target);

        // 如果连线两端都不在批量节点中，保留
        if (!isSourceInBatch && !isTargetInBatch) return true;

        // 如果连线两端都在批量节点中，保留（内部连线）
        if (isSourceInBatch && isTargetInBatch) return true;

        // 连线一端在批量节点中，另一端在外部
        const externalNodeId = isSourceInBatch ? edge.target : edge.source;
        const externalNode = nds.find((n: any) => n.id === externalNodeId);

        if (!externalNode) return true;

        const externalParent = externalNode.parentNode;

        if (newParentLoopId) {
          // 节点进入 loop：如果外部节点不在同一个 loop 内，断开连线
          if (externalParent !== newParentLoopId) {
            return false;
          }
        } else {
          // 节点离开 loop：如果外部节点还在原来的 loop 内，断开连线
          // 需要检查任一批量节点的旧 parent
          const anyOldParent = nodeInfos.find(info => info.oldParentLoopId)?.oldParentLoopId;
          if (anyOldParent && externalParent === anyOldParent) {
            return false;
          }
        }

        return true;
      });

      // 如果是进入 loop，检查是否需要自动连接 loop-start 和 loop-end
      if (newParentLoopId) {
        // 检查 loop 内是否只有 loop-start 和 loop-end（没有其他业务节点）
        // 注意：需要排除正在拖入的节点，因为此时它们已经被设置了 parentNode
        const loopChildren = nds.filter(
          (n: any) => n.parentNode === newParentLoopId && 
                      n.data?.type !== 'loop-start' && 
                      n.data?.type !== 'loop-end' &&
                      !nodeIdSet.has(n.id)  // 排除正在拖入的节点
        );
        
        // 如果 loop 原本是空的（只有 loop-start 和 loop-end）
        const isLoopEmpty = loopChildren.length === 0;
        
        if (isLoopEmpty && nodeInfos.length > 0) {
          // 找到 loop-start 和 loop-end 节点
          const loopStartNode = nds.find(
            (n: any) => n.parentNode === newParentLoopId && n.data?.type === 'loop-start'
          );
          const loopEndNode = nds.find(
            (n: any) => n.parentNode === newParentLoopId && n.data?.type === 'loop-end'
          );
          
          if (loopStartNode && loopEndNode) {
            // 找到拖入节点中最左侧和最右侧的节点
            let leftmostNode: typeof nodeInfos[0] | null = null;
            let rightmostNode: typeof nodeInfos[0] | null = null;
            let minX = Infinity;
            let maxX = -Infinity;
            
            for (const info of nodeInfos) {
              if (info.position.x < minX) {
                minX = info.position.x;
                leftmostNode = info;
              }
              const nodeWidth = info.width || 240;
              if (info.position.x + nodeWidth > maxX) {
                maxX = info.position.x + nodeWidth;
                rightmostNode = info;
              }
            }
            
            if (leftmostNode && rightmostNode) {
              // 检查 loop-start 是否已经有出边连接到拖入的节点
              const hasStartConnection = filteredEdges.some(
                (e: any) => e.source === loopStartNode.id && nodeIdSet.has(e.target)
              );
              
              // 检查 loop-end 是否已经有入边来自拖入的节点
              const hasEndConnection = filteredEdges.some(
                (e: any) => e.target === loopEndNode.id && nodeIdSet.has(e.source)
              );
              
              // 创建 loop-start -> 最左侧节点 的连线
              if (!hasStartConnection) {
                const startEdge = {
                  id: `${loopStartNode.id}-default-${leftmostNode.nodeId}-default`,
                  source: loopStartNode.id,
                  target: leftmostNode.nodeId,
                  sourceHandle: 'default',
                  targetHandle: 'default',
                  type: 'custom',
                  data: { isInLoop: true },
                  zIndex: 0,
                };
                filteredEdges.push(startEdge);
              }
              
              // 创建 最右侧节点 -> loop-end 的连线
              if (!hasEndConnection) {
                const endEdge = {
                  id: `${rightmostNode.nodeId}-default-${loopEndNode.id}-default`,
                  source: rightmostNode.nodeId,
                  target: loopEndNode.id,
                  sourceHandle: 'default',
                  targetHandle: 'default',
                  type: 'custom',
                  data: { isInLoop: true },
                  zIndex: 0,
                };
                filteredEdges.push(endEdge);
              }
            }
          }
        }
      }

      return filteredEdges;
    };

    if (workflowId) {
      setDbNodes((nds: any) => {
        const updatedNodes = updateNodes(nds);
        setDbEdges((eds: any) => updateEdges(eds, updatedNodes));
        return updatedNodes;
      });
    } else {
      setLocalNodes((nds: any) => {
        const updatedNodes = updateNodes(nds);
        setLocalEdges((eds: any) => updateEdges(eds, updatedNodes));
        return updatedNodes;
      });
    }
  }, [workflowId, setDbNodes, setDbEdges, setLocalNodes, setLocalEdges]);

  /**
   * 处理节点拖拽结束 - 检查是否进入/离开 Loop
   * 支持批量处理选中的多个节点
   */
  const handleNodeDragStop = useCallback((event: React.MouseEvent, node: any) => {
    if (node.data?.type === 'loop') return;

    const isLoopChild = node.data?.type === 'loop-start' || node.data?.type === 'loop-end';
    if (isLoopChild) {
      return;
    }

    // 检查是否是批量拖拽（拖拽的节点是选中节点之一，且有多个选中节点）
    const isDraggedNodeSelected = node.selected;
    const validSelectedNodes = selectedNodes.filter((n: any) => {
      // 排除 loop、loop-start、loop-end 类型的节点
      const nodeType = n.data?.type;
      return nodeType !== 'loop' && nodeType !== 'loop-start' && nodeType !== 'loop-end';
    });
    const isBatchDrag = isDraggedNodeSelected && validSelectedNodes.length > 1;

    if (isBatchDrag) {
      // 批量处理逻辑：
      // - 移入 loop：只要拖拽的节点进入 loop，所有选中节点都跟随进入
      // - 移出 loop：所有选中节点都不在任何 loop 内时，才算移出
      // - 在同一个 loop 内移动：不做任何处理
      
      // 获取选中节点当前的 parent（假设它们在同一个 loop 内，或都不在 loop 内）
      const currentParentLoopId = validSelectedNodes[0]?.parentNode || null;
      
      // 先检查是否仍在当前的 loop 内（如果有的话）
      if (currentParentLoopId) {
        // 检查拖拽的节点是否仍在当前 loop 内
        const stillInCurrentLoop = checkNodeInLoop(node, nodes, true);
        if (stillInCurrentLoop && stillInCurrentLoop.id === currentParentLoopId) {
          // 仍在同一个 loop 内移动，不需要做任何处理
          return;
        }
      }
      
      // 使用拖拽的节点来判断目标 loop（不包含当前 parent）
      const targetLoop = checkNodeInLoop(node, nodes, false);
      const targetLoopId = targetLoop?.id || null;
      
      // 判断是移入还是移出
      const isEnteringLoop = targetLoopId !== null && currentParentLoopId !== targetLoopId;
      const isLeavingLoop = targetLoopId === null && currentParentLoopId !== null;
      
      // 如果是移出 loop，需要检查所有选中节点是否都在 loop 外
      if (isLeavingLoop) {
        const allNodesOutside = validSelectedNodes.every((selectedNode: any) => {
          // 使用 includeCurrentParent=true 来检查是否还在当前 loop 内
          const nodeInLoop = checkNodeInLoop(selectedNode, nodes, true);
          return nodeInLoop === null;
        });
        
        // 如果不是所有节点都在 loop 外，不执行移出操作
        if (!allNodesOutside) {
          return;
        }
      }

      // 计算拖拽节点的位置偏移量
      // ReactFlow 传入的 node 参数包含最新的拖拽位置
      const draggedNodeInNodes = nodes.find((n: any) => n.id === node.id);
      
      // 计算拖拽节点的原始绝对位置
      let draggedOriginalAbsPos: { x: number; y: number };
      if (currentParentLoopId && draggedNodeInNodes) {
        const parentLoop = nodes.find((n: any) => n.id === currentParentLoopId);
        if (parentLoop) {
          draggedOriginalAbsPos = {
            x: (parentLoop.position?.x || 0) + (draggedNodeInNodes.position?.x || 0),
            y: (parentLoop.position?.y || 0) + (draggedNodeInNodes.position?.y || 0),
          };
        } else {
          draggedOriginalAbsPos = draggedNodeInNodes.positionAbsolute || draggedNodeInNodes.position;
        }
      } else if (draggedNodeInNodes) {
        draggedOriginalAbsPos = draggedNodeInNodes.positionAbsolute || draggedNodeInNodes.position;
      } else {
        draggedOriginalAbsPos = node.positionAbsolute || node.position;
      }
      
      // 拖拽后的位置（来自 ReactFlow 传入的 node 参数）
      const draggedNewAbsPos = node.positionAbsolute || node.position;
      
      // 计算偏移量
      const deltaX = draggedNewAbsPos.x - draggedOriginalAbsPos.x;
      const deltaY = draggedNewAbsPos.y - draggedOriginalAbsPos.y;

      // 收集所有需要改变 parent 的节点
      const nodesToChange: Array<{
        nodeId: string;
        position: { x: number; y: number };
        width?: number;
        height?: number;
        oldParentLoopId?: string | null;
      }> = [];

      for (const selectedNode of validSelectedNodes) {
        const currentParent = selectedNode.parentNode;
        
        // 只要当前 parent 与目标 loop 不同，就需要改变
        if (currentParent !== targetLoopId) {
          // 从 nodes 中获取节点状态
          const latestNode = nodes.find((n: any) => n.id === selectedNode.id);
          if (!latestNode) continue;
          
          // 计算节点的原始绝对位置
          let originalAbsPos: { x: number; y: number };
          if (currentParent) {
            const parentLoop = nodes.find((n: any) => n.id === currentParent);
            if (parentLoop) {
              originalAbsPos = {
                x: (parentLoop.position?.x || 0) + (latestNode.position?.x || 0),
                y: (parentLoop.position?.y || 0) + (latestNode.position?.y || 0),
              };
            } else {
              originalAbsPos = latestNode.positionAbsolute || latestNode.position;
            }
          } else {
            originalAbsPos = latestNode.positionAbsolute || latestNode.position;
          }
          
          // 应用偏移量得到新的绝对位置
          const newAbsolutePosition = {
            x: originalAbsPos.x + deltaX,
            y: originalAbsPos.y + deltaY,
          };
          
          nodesToChange.push({
            nodeId: selectedNode.id,
            position: newAbsolutePosition,
            width: latestNode.width,
            height: latestNode.height,
            oldParentLoopId: currentParent,
          });
        }
      }

      if (nodesToChange.length > 0) {
        handleBatchNodeLoopChange(nodesToChange, targetLoopId);
      }
    } else {
      // 单节点处理（原有逻辑）
      const currentParent = node.parentNode;

      if (currentParent) {
        const stillInCurrentLoop = checkNodeInLoop(node, nodes, true);
        if (stillInCurrentLoop && stillInCurrentLoop.id === currentParent) {
          return;
        }
      }

      const targetLoop = checkNodeInLoop(node, nodes, false);
      const targetLoopId = targetLoop?.id || null;

      if (currentParent !== targetLoopId) {
        const position = node.positionAbsolute || node.position;
        handleNodeLoopChange(
          node.id, 
          targetLoopId, 
          position, 
          currentParent, 
          false,
          node.width,
          node.height
        );
      }
    }
  }, [nodes, selectedNodes, checkNodeInLoop, handleNodeLoopChange, handleBatchNodeLoopChange]);

  // 高亮状态
  const [dropTargetLoopId, setDropTargetLoopId] = useState<string | null>(null);

  /**
   * 处理节点拖拽中 - 实时检测并高亮目标 Loop
   */
  const handleNodeDrag = useCallback((event: React.MouseEvent, node: any) => {
    if (node.data?.type === 'loop') {
      setDropTargetLoopId(null);
      return;
    }

    const isLoopChild = node.data?.type === 'loop-start' || node.data?.type === 'loop-end';
    if (isLoopChild) {
      setDropTargetLoopId(null);
      return;
    }

    // 检查节点当前的 parent
    const currentParent = node.parentNode;
    
    // 如果节点已经在某个 loop 内，检查是否仍在该 loop 内
    if (currentParent) {
      const stillInCurrentLoop = checkNodeInLoop(node, nodes, true);
      if (stillInCurrentLoop && stillInCurrentLoop.id === currentParent) {
        // 仍在当前 loop 内，不需要高亮
        setDropTargetLoopId(null);
        return;
      }
    }

    // 检查是否进入了新的 loop
    const targetLoop = checkNodeInLoop(node, nodes, false);
    const targetLoopId = targetLoop?.id || null;

    // 只有当目标 loop 与当前 parent 不同时才高亮
    if (targetLoopId && targetLoopId !== currentParent) {
      setDropTargetLoopId(targetLoopId);
    } else {
      setDropTargetLoopId(null);
    }
  }, [nodes, checkNodeInLoop]);

  /**
   * 处理拖拽开始 - 清除高亮
   */
  const handleNodeDragStart = useCallback(() => {
    setDropTargetLoopId(null);
  }, []);

  /**
   * 包装 handleNodeDragStop - 拖拽结束时清除高亮
   */
  const handleNodeDragStopWithClear = useCallback((event: React.MouseEvent, node: any) => {
    setDropTargetLoopId(null);
    handleNodeDragStop(event, node);
  }, [handleNodeDragStop]);

  return {
    checkNodeInLoop,
    handleNodeLoopChange,
    handleNodeDragStop: handleNodeDragStopWithClear,
    handleNodeDrag,
    handleNodeDragStart,
    dropTargetLoopId,
  };
}

