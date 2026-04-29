import React, { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import { useWorkflowActionStore } from '@/stores/useWorkflowActionStore';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  Connection,
  ReactFlowInstance,
  useNodesState,
  useEdgesState,
  MarkerType,
  SelectionMode,
  Panel,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Loader2, AlertCircle, Save, CheckCircle, LayoutTemplate, Hand, MousePointer2, Trash2, Send } from 'lucide-react';

import { useWorkflowGraph } from '../../hooks/useWorkflow';
import { workflowApi } from '../../api';
import { NODE_CONFIGS } from '../../types';
import type { NodeType, Workflow } from '../../types';
import { WorkflowContextMenu } from '../WorkflowContextMenu';
import WorkflowCustomNode from '../WorkflowCustomNode';
import WorkflowCustomEdge from '../WorkflowCustomEdge';
import { createNode } from './utils/nodeFactory';

// Hooks
import {
  useLoop,
  useLayout,
  useClipboard,
  useNodeOperations,
  useContextMenu,
  useDemoWizard,
  useKeyboardShortcuts,
} from './hooks';

// Components
import { DemoWizard, EmptyStateSelector, AddNodeDropdown, PublishDialog } from './components';

// 示例数据
import exampleGraph from '../../example_graph.json';

interface WorkflowEditorProps {
  workflowId?: string;
  onNodeSelect?: (node: any | null) => void;
  onNodeApiReady?: (api: { updateNodeData: (nodeId: string, patch: Record<string, any>) => void }) => void;
}

const nodeTypes = {
  custom: WorkflowCustomNode,
};

const edgeTypes = {
  custom: WorkflowCustomEdge,
};

// 交互模式类型
type InteractionMode = 'pan' | 'select';

export default function WorkflowEditor({ workflowId, onNodeSelect, onNodeApiReady }: WorkflowEditorProps) {
  const reactFlowWrapperRef = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  
  // 交互模式：pan（拖拽画布）或 select（框选）
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('pan');

  // 追踪当前选中的节点 ID，防止 onSelectionChange 在数据更新后用旧数据覆盖 selectedWorkflowNode
  const lastSelectedNodeIdRef = useRef<string | null>(null);

  // Track if the workflow has been initialized via the selection screen
  const [isInitialized, setIsInitialized] = useState(false);

  // Publish dialog
  const [publishOpen, setPublishOpen] = useState(false);
  const [workflowData, setWorkflowData] = useState<Workflow | null>(null);

  useEffect(() => {
    if (workflowId) {
      workflowApi.get(workflowId).then(setWorkflowData).catch(console.error);
    }
  }, [workflowId]);

  // 从 Supabase 加载数据
  const {
    nodes: dbNodes,
    edges: dbEdges,
    loading,
    saving,
    error,
    isDirty,
    setNodes: setDbNodes,
    setEdges: setDbEdges,
    save,
  } = useWorkflowGraph(workflowId || null, {
    autoSaveDelay: 2000,
  });

  // 本地状态
  const [localNodes, setLocalNodes, onLocalNodesChange] = useNodesState(
    !workflowId ? (exampleGraph.nodes as any) : []
  );
  const [localEdges, setLocalEdges, onLocalEdgesChange] = useEdgesState(
    !workflowId ? (exampleGraph.edges as any) : []
  );

  // 选择数据源
  const rawNodes = workflowId ? dbNodes : localNodes;
  const edges = workflowId ? dbEdges : localEdges;

  // 允许外部（ControlPanel）更新 node 的 data
  const updateNodeData = useCallback(
    (nodeId: string, patch: Record<string, any>) => {
      const apply = (nds: any[]) =>
        nds.map((n: any) => (n.id === nodeId ? { ...n, data: { ...(n.data || {}), ...patch } } : n));

      if (workflowId) {
        setDbNodes((nds: any) => apply(nds) as any);
      } else {
        setLocalNodes((nds: any) => apply(nds) as any);
      }
    },
    [workflowId, setDbNodes, setLocalNodes]
  );

  useEffect(() => {
    onNodeApiReady?.({ updateNodeData });
  }, [onNodeApiReady, updateNodeData]);

  // 处理 Loop 节点的 zIndex
  const nodes = useMemo(() => {
    // ReactFlow 嵌套节点（parentNode + extent: 'parent'）要求 parent 必须存在；
    // 否则会直接抛错：Parent node xxx not found
    const idSet = new Set((rawNodes as any[]).map((n: any) => n?.id).filter(Boolean));

    return (rawNodes as any[]).map((node: any) => {
      let next = node;

      // 如果 parentNode 不存在（脏数据 / 删除父节点后遗留），降级为普通节点避免崩溃
      if (next?.parentNode && !idSet.has(next.parentNode)) {
        const { parentNode, extent, ...rest } = next;
        const abs = next.positionAbsolute ?? next.position ?? { x: 0, y: 0 };
        next = {
          ...rest,
          position: abs,
          positionAbsolute: abs,
        };
      } else if (!next?.parentNode && next?.extent === 'parent') {
        // extent=parent 但没有 parentNode 也会导致异常行为，直接去掉
        const { extent, ...rest } = next;
        next = rest;
      }

      // Loop 节点放到最底层
      if (next?.data?.type === 'loop') {
        return {
          ...next,
          zIndex: -1,
          style: { ...next.style, zIndex: -1 },
        };
      }
      return next;
    });
  }, [rawNodes]);

  // edges 也做下清洗：如果 source/target 不存在则过滤，避免后续交互异常
  const safeEdges = useMemo(() => {
    const idSet = new Set((nodes as any[]).map((n: any) => n?.id).filter(Boolean));
    return (edges as any[]).filter((e: any) => idSet.has(e?.source) && idSet.has(e?.target));
  }, [edges, nodes]);

  const selectedEdges = useMemo(() => {
    return (safeEdges as any[]).filter((e: any) => e?.selected) as any[];
  }, [safeEdges]);


  // 剪贴板（需要先获取 selectedNodes，因为 useLoop 需要用到）
  const {
    clipboard,
    selectedNodes,
    handleCopy,
    handleCopyNode,
    handlePasteAt,
    handleDuplicateNode,
  } = useClipboard({
    nodes,
    edges: safeEdges,
    workflowId,
    setDbNodes,
    setDbEdges,
    setLocalNodes,
    setLocalEdges,
  });

  // Loop 相关逻辑（需要 selectedNodes 来支持批量拖拽）
  const { 
    handleNodeDragStop, 
    handleNodeDrag, 
    handleNodeDragStart,
    dropTargetLoopId,
  } = useLoop({
    nodes,
    workflowId,
    setDbNodes,
    setDbEdges,
    setLocalNodes,
    setLocalEdges,
    selectedNodes,
  });

  // 为 Loop 节点添加高亮状态
  const displayNodes = useMemo(() => {
    return nodes.map((node: any) => {
      if (node.data?.type === 'loop' && node.id === dropTargetLoopId) {
        return {
          ...node,
          data: {
            ...node.data,
            isDropTarget: true,
          },
        };
      }
      return node;
    });
  }, [nodes, dropTargetLoopId]);

  // 节点操作
  const { addNodeAtPosition, handleDeleteNode, handleNodesChange } = useNodeOperations({
    nodes,
    workflowId,
    loading,
    setDbNodes,
    setDbEdges,
    setLocalNodes,
    setLocalEdges,
    onLocalNodesChange,
  });

  // 自动布局
  const { handleAutoLayout } = useLayout({
    nodes,
    edges: safeEdges,
    workflowId,
    setDbNodes,
    setLocalNodes,
  });

  // Demo Wizard
  const demoWizard = useDemoWizard({
    workflowId,
    setDbNodes,
    setDbEdges,
    save,
    onComplete: () => setIsInitialized(true),
  });

  // 删除边
  const deleteEdge = useCallback((edgeId: string) => {
    if (workflowId) {
      setDbEdges((eds: any) => eds.filter((e: any) => e.id !== edgeId));
    } else {
      setLocalEdges((eds: any) => eds.filter((e: any) => e.id !== edgeId));
    }
  }, [workflowId, setDbEdges, setLocalEdges]);

  // 批量删除选中的节点
  const handleDeleteSelected = useCallback(() => {
    const protectedTypes = ['start', 'loop-start', 'loop-end'];
    const nodesToDelete = selectedNodes.filter((n) => {
      const t = (n.data as any)?.type;
      // loop 可以删；loop-start/loop-end/start 不能直接删
      if (t === 'loop') return true;
      return !protectedTypes.includes(t);
    });

    const nodeIdsToDelete = new Set(nodesToDelete.map(n => n.id));

    // 级联删除：如果删除 loop，同时删除其所有子节点（包括 loop-start/loop-end 等）
    const loopIdsToDelete = new Set(
      nodesToDelete.filter(n => (n.data as any)?.type === 'loop').map(n => n.id)
    );
    if (loopIdsToDelete.size > 0) {
      (nodes as any[]).forEach((n: any) => {
        if (n?.parentNode && loopIdsToDelete.has(n.parentNode)) {
          nodeIdsToDelete.add(n.id);
        }
      });
    }

    const edgeIdsToDelete = new Set((selectedEdges as any[]).map((e: any) => e.id));

    // 没有任何可删的内容
    if (nodeIdsToDelete.size === 0 && edgeIdsToDelete.size === 0) return;
    
    if (workflowId) {
      setDbNodes((nds: any) => nds.filter((n: any) => !nodeIdsToDelete.has(n.id)));
      setDbEdges((eds: any) =>
        eds.filter((e: any) => {
          // 删除选中边
          if (edgeIdsToDelete.has(e.id)) return false;
          // 删除与被删除节点相连的边
          if (nodeIdsToDelete.has(e.source) || nodeIdsToDelete.has(e.target)) return false;
          return true;
        })
      );
    } else {
      setLocalNodes((nds: any) => nds.filter((n: any) => !nodeIdsToDelete.has(n.id)));
      setLocalEdges((eds: any) =>
        eds.filter((e: any) => {
          if (edgeIdsToDelete.has(e.id)) return false;
          if (nodeIdsToDelete.has(e.source) || nodeIdsToDelete.has(e.target)) return false;
          return true;
        })
      );
    }
  }, [selectedNodes, selectedEdges, workflowId, setDbNodes, setDbEdges, setLocalNodes, setLocalEdges, nodes]);

  // 剪切：复制后删除（支持多选）
  const handleCutSelected = useCallback(() => {
    if (selectedNodes.length === 0) return;
    handleCopy();
    handleDeleteSelected();
  }, [selectedNodes.length, handleCopy, handleDeleteSelected]);

  // 节点菜单中的剪切：复制当前节点后删除
  const handleCutNode = useCallback((nodeId: string) => {
    handleCopyNode(nodeId);
    handleDeleteNode(nodeId);
  }, [handleCopyNode, handleDeleteNode]);

  // 右键菜单
  const {
    contextMenu,
    menuItems,
    closeContextMenu,
    handlePaneContextMenu,
    handleNodeContextMenu,
  } = useContextMenu({
    nodes,
    reactFlowWrapperRef,
    reactFlowInstance,
    selectedNodes,
    hasClipboard: !!clipboard?.nodes?.length,
    addNodeAtPosition,
    handleCut: handleCutSelected,
    handleCopy,
    handleCutNode,
    handleCopyNode,
    handlePasteAt,
    handleDuplicateNode,
    handleDeleteNode,
  });

  // 键盘粘贴时，默认粘贴到当前画布可视区域中心
  const handlePasteAtCenter = useCallback(() => {
    if (!reactFlowInstance || !reactFlowWrapperRef.current) return;
    const bounds = reactFlowWrapperRef.current.getBoundingClientRect();
    const flowPosition = reactFlowInstance.project({
      x: bounds.width / 2,
      y: bounds.height / 2,
    });
    handlePasteAt(flowPosition);
  }, [reactFlowInstance, handlePasteAt]);

  // 键盘快捷键
  useKeyboardShortcuts({
    onDelete: handleDeleteSelected,
    onCut: handleCutSelected,
    onCopy: handleCopy,
    onPaste: handlePasteAtCenter,
    setInteractionMode,
  });

  // 在屏幕中心添加节点
  const handleAddNodeAtCenter = useCallback((type: NodeType) => {
    if (!reactFlowInstance || !reactFlowWrapperRef.current) return;
    
    const bounds = reactFlowWrapperRef.current.getBoundingClientRect();
    const centerX = bounds.width / 2;
    const centerY = bounds.height / 2;
    
    // 将屏幕坐标转换为 flow 坐标
    const flowPosition = reactFlowInstance.project({
      x: centerX,
      y: centerY,
    });
    
    addNodeAtPosition(type, flowPosition, null);
  }, [reactFlowInstance, addNodeAtPosition]);

  // 监听自定义删除边事件
  useEffect(() => {
    const handleDeleteEdge = (e: CustomEvent<{ id: string }>) => {
      deleteEdge(e.detail.id);
    };
    window.addEventListener('deleteEdge', handleDeleteEdge as EventListener);
    return () => {
      window.removeEventListener('deleteEdge', handleDeleteEdge as EventListener);
    };
  }, [deleteEdge]);

  // 边变化处理
  const handleEdgesChange = useCallback((changes: any) => {
    if (workflowId) {
      setDbEdges((eds: any) => {
        let newEdges = [...eds];
        for (const change of changes) {
          if (change.type === 'remove') {
            newEdges = newEdges.filter(e => e.id !== change.id);
          } else if (change.type === 'select') {
            const edgeIndex = newEdges.findIndex(e => e.id === change.id);
            if (edgeIndex !== -1) {
              newEdges[edgeIndex] = {
                ...newEdges[edgeIndex],
                selected: change.selected,
              };
            }
          }
        }
        return newEdges;
      });
    } else {
      onLocalEdgesChange(changes);
    }
  }, [workflowId, setDbEdges, onLocalEdgesChange]);

  // 连接处理
  // 规则：每个 source handle 只能连接一条出边（如果已存在连接，则替换）
  const handleConnect = useCallback((params: Connection) => {
    const sourceHandleId = params.sourceHandle || 'default';
    const targetHandleId = params.targetHandle || 'default';
    
    const newEdge = {
      ...params,
      id: `${params.source}-${sourceHandleId}-${params.target}-${targetHandleId}`,
      type: 'custom',
      data: {
        isInLoop: false,
      },
      zIndex: 0,
    };

    // 更新边的逻辑：确保每个 source handle 只能有一条出边
    const updateEdges = (eds: any[]) => {
      // 查找是否已存在从同一个 source + sourceHandle 出发的边
      const existingEdgeIndex = eds.findIndex(
        (e: any) => e.source === params.source && (e.sourceHandle || 'default') === sourceHandleId
      );
      
      if (existingEdgeIndex !== -1) {
        // 替换现有的边
        const newEdges = [...eds];
        newEdges[existingEdgeIndex] = newEdge;
        return newEdges;
      }
      
      // 没有现有连接，添加新边
      return addEdge(newEdge, eds) as any;
    };

    if (workflowId) {
      setDbEdges(updateEdges);
    } else {
      setLocalEdges(updateEdges);
    }
  }, [workflowId, setDbEdges, setLocalEdges]);

  // Register editor API in the global store so AI app actions can manipulate the graph
  useEffect(() => {
    const api = {
      workflowId: workflowId || null,
      addNodeAtPosition,
      deleteNode: handleDeleteNode,
      updateNodeData,
      addBulkNodes: (newNodes: any[]) => {
        if (workflowId) {
          setDbNodes((nds: any) => [...nds, ...newNodes]);
        } else {
          setLocalNodes((nds: any) => [...nds, ...newNodes]);
        }
      },
      addBulkEdges: (newEdges: any[]) => {
        if (workflowId) {
          setDbEdges((eds: any) => [...eds, ...newEdges]);
        } else {
          setLocalEdges((eds: any) => [...eds, ...newEdges]);
        }
      },
      connectNodes: (sourceId: string, targetId: string, sourceHandle?: string, targetHandle?: string) => {
        handleConnect({
          source: sourceId,
          target: targetId,
          sourceHandle: sourceHandle || null,
          targetHandle: targetHandle || null,
        });
      },
      deleteEdge,
      autoLayout: handleAutoLayout,
      selectNode: (nodeId: string | null) => {
        if (nodeId) {
          const node = (nodes as any[]).find((n: any) => n.id === nodeId);
          onNodeSelect?.(node || null);
        } else {
          onNodeSelect?.(null);
        }
      },
      getNodes: () => nodes as any[],
      getEdges: () => safeEdges as any[],
    };
    useWorkflowActionStore.getState().registerEditor(api);
    return () => {
      useWorkflowActionStore.getState().unregisterEditor(workflowId || null);
    };
  }, [workflowId, addNodeAtPosition, handleDeleteNode, updateNodeData, handleConnect, deleteEdge, handleAutoLayout, nodes, safeEdges, onNodeSelect, setDbNodes, setLocalNodes, setDbEdges, setLocalEdges]);

  // 获取节点颜色
  const getNodeColor = (nodeType: string): string => {
    const config = NODE_CONFIGS[nodeType as NodeType];
    return config?.color || '#3b82f6';
  };

  const handleCreateEmpty = useCallback(async () => {
    setIsInitialized(true);
    if (!workflowId) return;
    
    // Create a start node
    const startNode = createNode('start', { x: 100, y: 100 });
    setDbNodes([startNode as any]);
    
    // Save immediately to persist the change
    setTimeout(() => {
      save(true).catch(console.error);
    }, 100);
  }, [workflowId, setDbNodes, save]);

  // Loading
  if (workflowId && loading) {
    return (
      <div className="w-full h-full bg-[#F8F9FA] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-orange-500" />
          <span className="text-sm text-black/50">Loading workflow...</span>
        </div>
      </div>
    );
  }

  // Error
  if (workflowId && error) {
    return (
      <div className="w-full h-full bg-[#F8F9FA] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <AlertCircle className="w-6 h-6 text-red-500" />
          <span className="text-sm text-black/60">{error.message}</span>
        </div>
      </div>
    );
  }

  // Empty State Selection (New Workflow)
  // Check if there are no nodes OR if there is only a default start node
  // Note: nodes[0].type is 'custom' (ReactFlow type), the actual node type is in nodes[0].data.type
  const hasDefaultStartNodeOnly = nodes.length === 1 && (nodes[0] as any)?.data?.type === 'start';
  // If explicitly initialized, don't show this screen (even if empty or just start node)
  // We only show this if NOT initialized AND (empty OR just start node)
  if (workflowId && !loading && !isInitialized && (nodes.length === 0 || hasDefaultStartNodeOnly)) {
    if (demoWizard.isOpen) {
      return (
        <DemoWizard
          step={demoWizard.step}
          description={demoWizard.description}
          onDescriptionChange={demoWizard.setDescription}
          onClose={demoWizard.close}
          onNextStep={demoWizard.nextStep}
          onPrevStep={demoWizard.prevStep}
          onSetStep={demoWizard.setStep}
          isRecording={demoWizard.recording.isRecording}
          isStopping={demoWizard.recording.isStopping}
          recordDuration={demoWizard.recording.duration}
          recordFilePath={demoWizard.recording.filePath}
          recordError={demoWizard.recording.error}
          onRecordToggle={demoWizard.handleRecordToggle}
          uploadStatus={demoWizard.upload.status}
          uploadPercent={demoWizard.upload.percent}
          uploadError={demoWizard.upload.error}
          previewUrl={demoWizard.upload.previewUrl}
          onStartUpload={demoWizard.handleStartUpload}
          analyzeStatus={demoWizard.analyze.status}
          analyzeProgress={demoWizard.analyze.progress}
          analyzeError={demoWizard.analyze.error}
          analyzeDescription={demoWizard.analyze.description}
          onFinish={demoWizard.finish}
        />
      );
    }

    return (
      <EmptyStateSelector
        onCreateFromDemo={demoWizard.open}
        onCreateFromChat={() => {
          if (nodes.length === 0) {
            handleCreateEmpty();
          } else {
            setIsInitialized(true);
          }
          window.dispatchEvent(new CustomEvent('vibe-workflow-init', { detail: { workflowId } }));
        }}
        onCreateBlank={() => {
          handleCreateEmpty();
        }}
      />
    );
  }

  return (
    <div 
      ref={reactFlowWrapperRef} 
      className={`w-full h-full bg-[#F8F9FA] no-drag relative ${interactionMode === 'select' ? 'mode-select' : 'mode-pan'}`}
    >
      {/* 状态指示器 */}
      {workflowId && (
        <div className="absolute top-3 right-3 z-10 flex items-center gap-2">
          <button
            onClick={async () => {
              if (workflowId) {
                try {
                  const fresh = await workflowApi.get(workflowId);
                  setWorkflowData(fresh);
                } catch (e) {
                  console.error('Failed to refresh workflow data', e);
                }
              }
              setPublishOpen(true);
            }}
            className="flex items-center gap-1.5 px-2 py-1 bg-white/80 hover:bg-white backdrop-blur rounded-md shadow-sm text-xs text-black/60 hover:text-black/90 transition-colors border border-black/5"
            title="Publish"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Publish</span>
          </button>

          <button
            onClick={handleAutoLayout}
            className="flex items-center gap-1.5 px-2 py-1 bg-white/80 hover:bg-white backdrop-blur rounded-md shadow-sm text-xs text-black/60 hover:text-black/90 transition-colors border border-black/5"
            title="Auto Layout"
          >
            <LayoutTemplate className="w-3.5 h-3.5" />
            <span>Layout</span>
          </button>

          {saving ? (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-white/80 backdrop-blur rounded-md shadow-sm text-xs text-black/50">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Saving...</span>
            </div>
          ) : isDirty ? (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-orange-50/80 backdrop-blur rounded-md shadow-sm text-xs text-orange-600">
              <Save className="w-3 h-3" />
              <span>Unsaved</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-green-50/80 backdrop-blur rounded-md shadow-sm text-xs text-green-600">
              <CheckCircle className="w-3 h-3" />
              <span>Saved</span>
            </div>
          )}
        </div>
      )}

      <ReactFlow
        nodes={displayNodes}
        edges={safeEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={setReactFlowInstance}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeDragStart={handleNodeDragStart}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={handleNodeDragStop}
        onPaneContextMenu={handlePaneContextMenu}
        onNodeContextMenu={handleNodeContextMenu}
        onPaneClick={() => {
          closeContextMenu();
          // 点击空白处：清除选中 node（用于 Control Panel 显示）
          lastSelectedNodeIdRef.current = null;
          onNodeSelect?.(null);
        }}
        onNodeClick={(e, node) => {
          closeContextMenu();
          // 同步外部选中 node（用于 Control Panel 显示）
          // NOTE: node 是 ReactFlow 的 Node 对象（包含 id / data / position 等）
          // 这里不强约束类型，交由上层按 WorkflowNode 使用
          lastSelectedNodeIdRef.current = node.id;
          onNodeSelect?.(node as any);
        }}
        onEdgeClick={closeContextMenu}
        onSelectionChange={(selection) => {
          // 框选/Shift 多选等场景不会触发 onNodeClick，这里兜底同步
          const first = selection?.nodes?.[0] ?? null;
          const newId = first?.id ?? null;
          // 防止 React Flow 在节点数据更新后触发 onSelectionChange 用旧数据覆盖 selectedWorkflowNode
          // 只有当选中的节点 ID 真正变化时才更新
          if (newId !== lastSelectedNodeIdRef.current) {
            lastSelectedNodeIdRef.current = newId;
            onNodeSelect?.(first as any);
          }
        }}
        fitView
        attributionPosition="bottom-right"
        proOptions={{ hideAttribution: true }}
        // 框选相关配置
        selectionOnDrag={interactionMode === 'select'}
        panOnDrag={interactionMode === 'pan'}
        selectionMode={SelectionMode.Partial}
        selectNodesOnDrag={false}
        // 多选支持
        multiSelectionKeyCode={['Shift', 'Meta', 'Control']}
        deleteKeyCode={null} // 我们自己处理删除
        defaultEdgeOptions={{
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#94a3b8',
            width: 16,
            height: 16,
          },
        }}
        connectionLineStyle={{ stroke: '#94a3b8', strokeWidth: 1.5 }}
      >
        <Background gap={16} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} className="bg-white border-gray-200 shadow-sm" />
        
        {/* 工具栏 */}
        <Panel position="top-left" className="flex items-center gap-1 bg-white/90 backdrop-blur rounded-lg shadow-sm border border-black/5 p-1">
          <AddNodeDropdown onAddNode={handleAddNodeAtCenter} />
          
          <div className="w-px h-5 bg-gray-200 mx-1" />
          
          <button
            onClick={() => setInteractionMode('pan')}
            className={`flex items-center justify-center w-8 h-8 rounded-md transition-colors ${
              interactionMode === 'pan'
                ? 'bg-orange-100 text-orange-600'
                : 'hover:bg-gray-100 text-gray-600'
            }`}
            title="拖拽模式 (按住空格临时切换)"
          >
            <Hand className="w-4 h-4" />
          </button>
          <button
            onClick={() => setInteractionMode('select')}
            className={`flex items-center justify-center w-8 h-8 rounded-md transition-colors ${
              interactionMode === 'select'
                ? 'bg-orange-100 text-orange-600'
                : 'hover:bg-gray-100 text-gray-600'
            }`}
            title="选择模式 (可框选多个节点)"
          >
            <MousePointer2 className="w-4 h-4" />
          </button>
          
          <div className="w-px h-5 bg-gray-200 mx-1" />
          
          <button
            onClick={handleDeleteSelected}
            disabled={selectedNodes.length === 0}
            className={`flex items-center justify-center w-8 h-8 rounded-md transition-colors ${
              selectedNodes.length > 0
                ? 'hover:bg-red-50 text-red-500 hover:text-red-600'
                : 'text-gray-300 cursor-not-allowed'
            }`}
            title={`删除选中节点 (${selectedNodes.length})`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
          
          {selectedNodes.length > 0 && (
            <span className="text-xs text-gray-500 px-1">
              {selectedNodes.length} Selected
            </span>
          )}
        </Panel>
        
        <MiniMap
          nodeStrokeColor={(n) => {
            const nodeType = n.data?.type as NodeType;
            return getNodeColor(nodeType);
          }}
          nodeColor={(n) => {
            const nodeType = n.data?.type as NodeType;
            const color = getNodeColor(nodeType);
            return `${color}20`;
          }}
          className="border border-gray-200 shadow-sm rounded-lg overflow-hidden"
        />
      </ReactFlow>

      {contextMenu && (
        <WorkflowContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={menuItems}
          onClose={closeContextMenu}
          containerBounds={reactFlowWrapperRef.current?.getBoundingClientRect() ?? null}
        />
      )}

      {workflowData && (
        <PublishDialog
          open={publishOpen}
          workflow={workflowData}
          onClose={() => setPublishOpen(false)}
          onUpdated={(updated) => setWorkflowData(updated)}
        />
      )}
    </div>
  );
}
