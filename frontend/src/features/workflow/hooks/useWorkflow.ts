/**
 * Workflow React Hooks
 * 
 * 提供工作流相关的状态管理和操作
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { workflowApi, WorkflowApiError } from '../api';
import type {
  Graph,
  Workflow,
  WorkflowListItem,
  PublicWorkflowListItem,
  WorkflowNode,
  WorkflowEdge,
  Viewport,
  CreateWorkflowParams,
} from '../types';

const WORKFLOW_UPDATED_EVENT = 'workflow-updated';
const dispatchWorkflowUpdate = () => {
  window.dispatchEvent(new Event(WORKFLOW_UPDATED_EVENT));
};

// ==================== usePublicWorkflows ====================

interface UsePublicWorkflowsReturn {
  workflows: PublicWorkflowListItem[];
  loading: boolean;
  error: WorkflowApiError | null;
  refresh: () => Promise<void>;
  fork: (id: string) => Promise<Workflow>;
  forking: boolean;
}

/**
 * Get public/community workflows
 */
export function usePublicWorkflows(): UsePublicWorkflowsReturn {
  const [workflows, setWorkflows] = useState<PublicWorkflowListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<WorkflowApiError | null>(null);
  const [forking, setForking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const data = await workflowApi.listPublic(true);
      if (controller.signal.aborted) return;
      setWorkflows(data);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err)));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial load uses cache (forceRefresh=false)
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    workflowApi.listPublic()
      .then(data => { if (!controller.signal.aborted) setWorkflows(data); })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err))); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  const fork = useCallback(async (id: string) => {
    setForking(true);
    try {
      const result = await workflowApi.fork(id);
      dispatchWorkflowUpdate();
      return result;
    } finally {
      setForking(false);
    }
  }, []);

  return { workflows, loading, error, refresh, fork, forking };
}

// ==================== useWorkflowList ====================

interface UseWorkflowListReturn {
  workflows: WorkflowListItem[];
  loading: boolean;
  error: WorkflowApiError | null;
  refresh: () => Promise<void>;
}

/**
 * 获取工作流列表
 */
export function useWorkflowList(): UseWorkflowListReturn {
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<WorkflowApiError | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await workflowApi.list();
      setWorkflows(data);
    } catch (err) {
      setError(err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const handler = () => refresh();
    window.addEventListener(WORKFLOW_UPDATED_EVENT, handler);
    return () => window.removeEventListener(WORKFLOW_UPDATED_EVENT, handler);
  }, [refresh]);

  return { workflows, loading, error, refresh };
}

// ==================== useWorkflow ====================

interface UseWorkflowReturn {
  workflow: Workflow | null;
  loading: boolean;
  error: WorkflowApiError | null;
  refresh: () => Promise<void>;
  update: (params: { name?: string; description?: string }) => Promise<void>;
  remove: () => Promise<void>;
  duplicate: () => Promise<Workflow>;
}

/**
 * 获取单个工作流
 */
export function useWorkflow(id: string | null): UseWorkflowReturn {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<WorkflowApiError | null>(null);

  const refresh = useCallback(async () => {
    if (!id) {
      setWorkflow(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await workflowApi.get(id);
      setWorkflow(data);
    } catch (err) {
      setError(err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err)));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useCallback(async (params: { name?: string; description?: string }) => {
    if (!id) return;
    const updated = await workflowApi.update(id, params);
    setWorkflow(updated);
    dispatchWorkflowUpdate();
  }, [id]);

  const remove = useCallback(async () => {
    if (!id) return;
    await workflowApi.delete(id);
    setWorkflow(null);
    dispatchWorkflowUpdate();
  }, [id]);

  const duplicateWorkflow = useCallback(async () => {
    if (!id) throw new Error('No workflow to duplicate');
    const result = await workflowApi.duplicate(id);
    dispatchWorkflowUpdate();
    return result;
  }, [id]);

  return { workflow, loading, error, refresh, update, remove, duplicate: duplicateWorkflow };
}

// ==================== useWorkflowGraph ====================

interface UseWorkflowGraphReturn {
  // 图数据
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport: Viewport;
  
  // 状态
  loading: boolean;
  saving: boolean;
  error: WorkflowApiError | null;
  isDirty: boolean;
  
  // 操作
  setNodes: React.Dispatch<React.SetStateAction<WorkflowNode[]>>;
  setEdges: React.Dispatch<React.SetStateAction<WorkflowEdge[]>>;
  setViewport: React.Dispatch<React.SetStateAction<Viewport>>;
  save: (force?: boolean) => Promise<void>;
  refresh: () => Promise<void>;
}

interface UseWorkflowGraphOptions {
  /** 自动保存延迟（毫秒），设为 0 禁用自动保存 */
  autoSaveDelay?: number;
  /** 是否启用实时订阅 */
  enableRealtime?: boolean;
}

/**
 * 管理工作流图数据
 * 
 * 支持自动保存和实时订阅
 */
export function useWorkflowGraph(
  workflowId: string | null,
  options: UseWorkflowGraphOptions = {}
): UseWorkflowGraphReturn {
  const { autoSaveDelay = 2000, enableRealtime = false } = options;

  const [nodes, setNodes] = useState<WorkflowNode[]>([]);
  const [edges, setEdges] = useState<WorkflowEdge[]>([]);
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<WorkflowApiError | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  // 用于追踪初始加载状态
  const isInitialLoad = useRef(true);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // 🔧 FIX: 追踪是否已经成功从数据库加载过数据
  // 这可以防止在数据加载完成之前，空数据被保存到数据库覆盖原有内容
  const hasLoadedOnce = useRef(false);
  
  // 使用 ref 来追踪最新状态，避免闭包陷阱
  const latestDataRef = useRef({ nodes, edges, viewport });
  latestDataRef.current = { nodes, edges, viewport };
  
  const isDirtyRef = useRef(isDirty);
  isDirtyRef.current = isDirty;
  
  const workflowIdRef = useRef(workflowId);
  workflowIdRef.current = workflowId;
  
  const hasLoadedOnceRef = useRef(hasLoadedOnce.current);
  hasLoadedOnceRef.current = hasLoadedOnce.current;

  // ReactFlow requires node.position.{x,y}. If the DB contains dirty nodes (missing position / null entries),
  // ReactFlow will crash at runtime. This sanitizes nodes defensively.
  // 
  // 🔧 FIX: 移除非 loop 节点的 width/height/style 属性，让 ReactFlow 自动测量实际尺寸。
  // 这解决了 AI 生成的 workflow 中节点可点击区域与可视区域不匹配的问题。
  // （后端生成的节点可能设置了固定的 width/height，但实际渲染高度会根据内容动态变化）
  const sanitizeNodes = useCallback((input: any[]): any[] => {
    const arr = Array.isArray(input) ? input : [];
    return arr
      .filter(Boolean)
      .map((n: any) => {
        const pos = n?.position;
        const fallback = n?.positionAbsolute;
        const nextPos =
          pos && typeof pos.x === 'number' && typeof pos.y === 'number'
            ? pos
            : fallback && typeof fallback.x === 'number' && typeof fallback.y === 'number'
              ? fallback
              : { x: 0, y: 0 };

        // Loop 节点需要保留 width/height/style 以支持 resize
        const nodeType = n?.data?.type;
        if (nodeType === 'loop') {
          return {
            ...n,
            position: nextPos,
            positionAbsolute: n?.positionAbsolute ?? nextPos,
          };
        }

        // 非 loop 节点：移除 width/height/style，让 ReactFlow 自动测量
        const { width, height, style, ...rest } = n || {};
        return {
          ...rest,
          position: nextPos,
          positionAbsolute: n?.positionAbsolute ?? nextPos,
        };
      });
  }, []);

  // Backward-compatible migration for node types & titles.
  // - llm -> tool-use
  // - web-search -> browser-use
  // - mcp -> mcp-use
  // - rag-search -> removed (drop node + related edges)
  const migrateGraph = useCallback((graph: any) => {
    const renameType = (t: any) => {
      if (t === 'llm') return 'tool-use';
      if (t === 'web-search') return 'browser-use';
      if (t === 'mcp') return 'mcp-use';
      return t;
    };

    const isRemoved = (t: any) => t === 'rag-search';

    const inputNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
    const migratedNodes = inputNodes
      .filter(Boolean)
      .map((n: any) => {
        const oldType = n?.data?.type;
        if (isRemoved(oldType)) return null;

        const nextType = renameType(oldType);
        const nextData = { ...(n?.data || {}), type: nextType };

        // Keep user-custom titles intact; only migrate legacy default titles.
        if (oldType === 'llm' && nextData.title === 'LLM') nextData.title = 'Tool Use';
        if (oldType === 'web-search' && nextData.title === 'Web Search') nextData.title = 'Browser Use';
        if (oldType === 'mcp' && (nextData.title === 'MCP' || nextData.title === 'MCP 执行')) nextData.title = 'MCP Use';

        return { ...n, data: nextData };
      })
      .filter(Boolean);

    const idSet = new Set(migratedNodes.map((n: any) => n.id));
    const inputEdges = Array.isArray(graph?.edges) ? graph.edges : [];
    const migratedEdges = inputEdges
      .filter(Boolean)
      .filter((e: any) => idSet.has(e.source) && idSet.has(e.target))
      .map((e: any) => {
        const d = e?.data;
        if (!d) return e;
        return {
          ...e,
          data: {
            ...d,
            sourceType: renameType(d.sourceType),
            targetType: d.targetType ? renameType(d.targetType) : d.targetType,
          },
        };
      });

    return {
      ...(graph || {}),
      nodes: migratedNodes,
      edges: migratedEdges,
    };
  }, []);

  // 加载图数据
  const refresh = useCallback(async () => {
    if (!workflowId) {
      setNodes([]);
      setEdges([]);
      setViewport({ x: 0, y: 0, zoom: 1 });
      setLoading(false);
      hasLoadedOnce.current = false;
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const graph = await workflowApi.getGraph(workflowId);
      const migrated = migrateGraph(graph);
      setNodes(sanitizeNodes(migrated.nodes || []) as any);
      setEdges(migrated.edges || []);
      setViewport(migrated.viewport);
      setIsDirty(false);
      isInitialLoad.current = true;
      // 🔧 FIX: 标记数据已成功加载
      hasLoadedOnce.current = true;
      console.log('[useWorkflowGraph] ✅ Data loaded successfully for workflow:', workflowId);
    } catch (err) {
      setError(err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err)));
      hasLoadedOnce.current = false;
    } finally {
      setLoading(false);
    }
  }, [workflowId, sanitizeNodes, migrateGraph]);

  // 🔧 FIX: 当 workflowId 变化时，重置加载状态，防止旧数据被保存
  useEffect(() => {
    // 清除任何待执行的保存操作
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
    }
    // 重置状态
    hasLoadedOnce.current = false;
    isInitialLoad.current = true;
    setIsDirty(false);
    console.log('[useWorkflowGraph] 🔄 WorkflowId changed, resetting state:', workflowId);
  }, [workflowId]);

  // 初始加载
  useEffect(() => {
    refresh();
  }, [refresh]);

  // 保存图数据（使用 ref 避免闭包陷阱和不必要的重新创建）
  const saveRef = useRef<(force?: boolean) => Promise<void>>();
  
  const save = useCallback(async (force: boolean = false) => {
    if (!workflowIdRef.current) return;
    // 如果不是强制保存，则检查 isDirty
    if (!force && !isDirtyRef.current) return;
    
    // 🔧 FIX: 如果数据还没有成功加载过，不允许保存，防止空数据覆盖数据库
    if (!hasLoadedOnceRef.current) {
      console.warn('[useWorkflowGraph] ⚠️ Skipping save: data has not been loaded yet');
      return;
    }
    
    const { nodes: latestNodes, edges: latestEdges, viewport: latestViewport } = latestDataRef.current;
    
    // 🔧 FIX: 空数组不需要保存（新建时就是空的，没有变化）
    if (latestNodes.length === 0 && latestEdges.length === 0) {
      console.log('[useWorkflowGraph] ⏭️ Skipping save: empty graph (no nodes/edges)');
      return;
    }

    setSaving(true);
    try {
      console.log('[useWorkflowGraph] 💾 Saving graph:', { 
        workflowId: workflowIdRef.current, 
        nodesCount: latestNodes.length, 
        edgesCount: latestEdges.length 
      });
      await workflowApi.saveGraph(workflowIdRef.current, { 
        nodes: latestNodes, 
        edges: latestEdges, 
        viewport: latestViewport 
      });
      setIsDirty(false);
    } catch (err) {
      setError(err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err)));
      throw err;
    } finally {
      setSaving(false);
    }
  }, []); // 不依赖任何值，全部从 ref 读取
  
  saveRef.current = save;

  // 数据变化时标记为脏
  useEffect(() => {
    // 跳过初始加载
    if (isInitialLoad.current) {
      isInitialLoad.current = false;
      return;
    }
    
    // 🔧 FIX: 如果数据还没有加载过，不标记为脏，也不触发自动保存
    if (!hasLoadedOnce.current) {
      console.log('[useWorkflowGraph] ⏳ Data not loaded yet, skipping dirty flag');
      return;
    }

    setIsDirty(true);

    // 自动保存
    if (autoSaveDelay > 0) {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveRef.current?.(true).catch(console.error);
      }, autoSaveDelay);
    }

    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [nodes, edges, viewport, autoSaveDelay]); // 移除 save 依赖

  // Use ref for saving state to avoid re-subscribing on every save
  const savingRef = useRef(saving);
  savingRef.current = saving;

  // 实时订阅
  useEffect(() => {
    if (!workflowId || !enableRealtime) return;

    const unsubscribe = workflowApi.subscribe(workflowId, (workflow) => {
      if (!savingRef.current) {
        const migrated = migrateGraph(workflow.definition);
        setNodes(sanitizeNodes(migrated.nodes || []) as any);
        setEdges(migrated.edges || []);
        setViewport(migrated.viewport);
        setIsDirty(false);
      }
    });

    return unsubscribe;
  }, [workflowId, enableRealtime, sanitizeNodes, migrateGraph]);

  // 组件卸载时保存
  useEffect(() => {
    return () => {
      // 🔧 FIX: 只有在数据已经成功加载过的情况下才保存，防止空数据覆盖数据库
      if (isDirtyRef.current && workflowIdRef.current && hasLoadedOnceRef.current) {
        const { nodes, edges, viewport } = latestDataRef.current;
        
        // 🔧 FIX: 空数组不需要保存
        if (nodes.length === 0 && edges.length === 0) {
          console.log('[useWorkflowGraph] 🚪 Component unmounting, skipping save: empty graph');
          return;
        }
        
        // 同步保存（最后一次机会）
        console.log('[useWorkflowGraph] 🚪 Component unmounting, saving dirty data:', {
          workflowId: workflowIdRef.current,
          nodesCount: nodes.length,
          edgesCount: edges.length
        });
        workflowApi.saveGraph(workflowIdRef.current, { nodes, edges, viewport }).catch(console.error);
      } else if (isDirtyRef.current && !hasLoadedOnceRef.current) {
        console.warn('[useWorkflowGraph] ⚠️ Component unmounting with dirty flag but data was never loaded, skipping save');
      }
    };
  }, []);

  return {
    nodes,
    edges,
    viewport,
    loading,
    saving,
    error,
    isDirty,
    setNodes,
    setEdges,
    setViewport,
    save,
    refresh,
  };
}

// ==================== useCreateWorkflow ====================

interface UseCreateWorkflowReturn {
  create: (params: CreateWorkflowParams) => Promise<Workflow>;
  creating: boolean;
  error: WorkflowApiError | null;
}

/**
 * 创建工作流
 */
export function useCreateWorkflow(): UseCreateWorkflowReturn {
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<WorkflowApiError | null>(null);

  const create = useCallback(async (params: CreateWorkflowParams) => {
    setCreating(true);
    setError(null);
    try {
      const result = await workflowApi.create(params);
      dispatchWorkflowUpdate();
      return result;
    } catch (err) {
      const apiError = err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setCreating(false);
    }
  }, []);

  return { create, creating, error };
}

// ==================== useUpdateWorkflow ====================

interface UseUpdateWorkflowReturn {
  update: (id: string, params: { name?: string; description?: string }) => Promise<Workflow>;
  updating: boolean;
  error: WorkflowApiError | null;
}

/**
 * 更新工作流
 */
export function useUpdateWorkflow(): UseUpdateWorkflowReturn {
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<WorkflowApiError | null>(null);

  const update = useCallback(async (id: string, params: { name?: string; description?: string }) => {
    setUpdating(true);
    setError(null);
    try {
      const result = await workflowApi.update(id, params);
      dispatchWorkflowUpdate();
      return result;
    } catch (err) {
      const apiError = err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setUpdating(false);
    }
  }, []);

  return { update, updating, error };
}

// ==================== useDeleteWorkflow ====================

interface UseDeleteWorkflowReturn {
  remove: (id: string) => Promise<void>;
  deleting: boolean;
  error: WorkflowApiError | null;
}

/**
 * 删除工作流
 */
export function useDeleteWorkflow(): UseDeleteWorkflowReturn {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<WorkflowApiError | null>(null);

  const remove = useCallback(async (id: string) => {
    setDeleting(true);
    setError(null);
    try {
      await workflowApi.delete(id);
      dispatchWorkflowUpdate();
    } catch (err) {
      const apiError = err instanceof WorkflowApiError ? err : new WorkflowApiError('UNKNOWN', String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setDeleting(false);
    }
  }, []);

  return { remove, deleting, error };
}
