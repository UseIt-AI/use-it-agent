import { useState, useCallback, useMemo, RefObject } from 'react';
import type { ReactFlowInstance } from 'reactflow';
import { NODE_CONFIGS } from '../../../types';
import type { NodeType, WorkflowNode } from '../../../types';
import type { WorkflowContextMenuItem } from '../../WorkflowContextMenu';
import { BlockIcon } from '../../block-icon';
import React from 'react';

interface ContextMenuState {
  x: number;
  y: number;
  flowPosition: { x: number; y: number };
  insideLoopId: string | null;
  targetNode?: { id: string; type: string } | null;
}

interface UseContextMenuOptions {
  nodes: any[];
  reactFlowWrapperRef: RefObject<HTMLDivElement | null>;
  reactFlowInstance: ReactFlowInstance | null;
  selectedNodes: WorkflowNode[];
  hasClipboard: boolean;
  addNodeAtPosition: (type: NodeType, position: { x: number; y: number }, parentLoopId?: string | null) => void;
  handleCut: () => void;
  handleCopy: () => void;
  handleCutNode: (nodeId: string) => void;
  handleCopyNode: (nodeId: string) => void;
  handlePasteAt: (position: { x: number; y: number }) => void;
  handleDuplicateNode: (nodeId: string) => void;
  handleDeleteNode: (nodeId: string) => void;
}

export function useContextMenu({
  nodes,
  reactFlowWrapperRef,
  reactFlowInstance,
  selectedNodes,
  hasClipboard,
  addNodeAtPosition,
  handleCut,
  handleCopy,
  handleCutNode,
  handleCopyNode,
  handlePasteAt,
  handleDuplicateNode,
  handleDeleteNode,
}: UseContextMenuOptions) {
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  /**
   * 关闭右键菜单
   */
  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  /**
   * 处理画布右键点击
   */
  const handlePaneContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();

    if (!reactFlowWrapperRef.current || !reactFlowInstance) return;
    const bounds = reactFlowWrapperRef.current.getBoundingClientRect();
    const flowPosition = reactFlowInstance.project({
      x: e.clientX - bounds.left,
      y: e.clientY - bounds.top,
    });

    // 检测点击位置是否在某个 Loop 节点内部
    const loopNode = nodes.find((node: any) => {
      if (node.data?.type !== 'loop') return false;
      const nodeX = node.position?.x || 0;
      const nodeY = node.position?.y || 0;
      const nodeWidth = node.width || node.style?.width || 800;
      const nodeHeight = node.height || node.style?.height || 400;

      return (
        flowPosition.x >= nodeX &&
        flowPosition.x <= nodeX + nodeWidth &&
        flowPosition.y >= nodeY &&
        flowPosition.y <= nodeY + nodeHeight
      );
    });

    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      flowPosition,
      insideLoopId: loopNode?.id || null,
      targetNode: null,
    });
  }, [reactFlowInstance, nodes, reactFlowWrapperRef]);

  /**
   * 处理节点右键点击
   */
  const handleNodeContextMenu = useCallback((e: React.MouseEvent, node: any) => {
    e.preventDefault();

    if (!reactFlowWrapperRef.current || !reactFlowInstance) return;
    const bounds = reactFlowWrapperRef.current.getBoundingClientRect();
    const flowPosition = reactFlowInstance.project({
      x: e.clientX - bounds.left,
      y: e.clientY - bounds.top,
    });

    const isLoopNode = node.data?.type === 'loop';

    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      flowPosition,
      insideLoopId: isLoopNode ? node.id : null,
      targetNode: { id: node.id, type: node.data?.type },
    });
  }, [reactFlowInstance, reactFlowWrapperRef]);

  /**
   * 构建菜单项
   */
  const menuItems = useMemo((): WorkflowContextMenuItem[] => {
    const canCopy = selectedNodes.length > 0;
    const canPaste = hasClipboard;
    const isInsideLoop = !!contextMenu?.insideLoopId;

    // 基础节点选项
    const commonItems = [
      {
        id: 'add-tool-use',
        label: NODE_CONFIGS['tool-use']?.defaultTitle || 'Tool Use',
        icon: React.createElement(BlockIcon, { type: 'tool-use', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('tool-use', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
      {
        id: 'add-computer-use',
        label: 'Computer Use',
        icon: React.createElement(BlockIcon, { type: 'computer-use', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('computer-use', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
      {
        id: 'add-browser-use',
        label: NODE_CONFIGS['browser-use']?.defaultTitle || 'Browser Use',
        icon: React.createElement(BlockIcon, { type: 'browser-use', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('browser-use', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
      {
        id: 'add-code-use',
        label: 'Code Use',
        icon: React.createElement(BlockIcon, { type: 'code-use', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('code-use', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
      {
        id: 'add-end',
        label: 'End',
        icon: React.createElement(BlockIcon, { type: 'end', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('end', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
    ];

    // Loop 内部特有的选项
    const loopItems = isInsideLoop ? [
      {
        id: 'add-loop-start',
        label: 'Loop Start',
        icon: React.createElement(BlockIcon, { type: 'loop-start', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('loop-start', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
      {
        id: 'add-loop-end',
        label: 'Loop End',
        icon: React.createElement(BlockIcon, { type: 'loop-end', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('loop-end', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
    ] : [];

    // 逻辑节点选项
    const logicItems = [
      {
        id: 'add-if-else',
        label: 'If/Else',
        icon: React.createElement(BlockIcon, { type: 'if-else', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('if-else', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
      ...(!isInsideLoop ? [{
        id: 'add-loop',
        label: 'Loop',
        icon: React.createElement(BlockIcon, { type: 'loop', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('loop', contextMenu.flowPosition, null),
      }] : []),
    ];

    const experimentalItems = [
      {
        id: 'add-agent',
        label: NODE_CONFIGS['agent']?.defaultTitle || 'Agent',
        icon: React.createElement(BlockIcon, { type: 'agent', className: 'w-4 h-4' }),
        onClick: () => contextMenu && addNodeAtPosition('agent', contextMenu.flowPosition, contextMenu.insideLoopId),
      },
    ];

    const addBlockChildren = [
      {
        title: 'COMMON AGENTS',
        items: commonItems,
      },
      ...(loopItems.length > 0 ? [{
        title: 'LOOP',
        items: loopItems,
      }] : []),
      {
        title: 'LOGIC',
        items: logicItems,
      },
      {
        title: 'EXPERIMENTAL',
        items: experimentalItems,
      },
    ];

    // 如果右键点击的是非 Loop 节点
    const targetNode = contextMenu?.targetNode;
    const isNodeMenu = targetNode && targetNode.type !== 'loop';
    const isProtectedNode = targetNode && ['start', 'loop-start', 'loop-end'].includes(targetNode.type);

    if (isNodeMenu) {
      if (isProtectedNode) {
        return [
          {
            id: 'protected-info',
            label: targetNode.type === 'start' ? 'Start node cannot be modified' : 'Loop node cannot be modified',
            disabled: true,
            onClick: () => {},
          },
        ];
      }

      return [
        {
          id: 'cut-node',
          label: 'Cut',
          shortcut: 'Ctrl+X',
          onClick: () => handleCutNode(targetNode.id),
        },
        {
          id: 'copy-node',
          label: 'Copy',
          shortcut: 'Ctrl+C',
          onClick: () => handleCopyNode(targetNode.id),
        },
        {
          id: 'duplicate-node',
          label: 'Duplicate',
          shortcut: 'Ctrl+D',
          onClick: () => handleDuplicateNode(targetNode.id),
        },
        { id: 'sep-1', separator: true },
        {
          id: 'delete-node',
          label: 'Delete',
          shortcut: 'Delete',
          onClick: () => handleDeleteNode(targetNode.id),
        },
      ];
    }

    // 默认菜单
    return [
      {
        id: 'paste',
        label: 'Paste Here',
        shortcut: 'Ctrl+V',
        disabled: !canPaste,
        onClick: () => contextMenu && handlePasteAt(contextMenu.flowPosition),
      },
      {
        id: 'cut',
        label: 'Cut',
        shortcut: 'Ctrl+X',
        disabled: !canCopy,
        onClick: handleCut,
      },
      {
        id: 'copy',
        label: 'Copy',
        shortcut: 'Ctrl+C',
        disabled: !canCopy,
        onClick: handleCopy,
      },
      { id: 'sep-1', separator: true },
      {
        id: 'add-block',
        label: '+ Add Node',
        children: addBlockChildren,
      },
    ];
  }, [
    selectedNodes.length,
    hasClipboard,
    contextMenu,
    addNodeAtPosition,
    handleCut,
    handleCopy,
    handleCutNode,
    handleCopyNode,
    handlePasteAt,
    handleDuplicateNode,
    handleDeleteNode,
  ]);

  return {
    contextMenu,
    menuItems,
    closeContextMenu,
    handlePaneContextMenu,
    handleNodeContextMenu,
  };
}

