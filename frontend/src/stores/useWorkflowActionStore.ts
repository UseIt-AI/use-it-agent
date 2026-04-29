/**
 * Workflow Action Store
 * 
 * Provides imperative workflow operations that can be called from outside
 * React components (e.g. from AI app actions). The WorkflowEditor registers
 * its graph manipulation functions here on mount, and unregisters on unmount.
 * 
 * This is a thin bridge: the actual logic stays in WorkflowEditor hooks,
 * but this store exposes stable references callable via getState().
 */

import { create } from 'zustand';
import type { NodeType, WorkflowNode, WorkflowEdge } from '@/features/workflow/types';

export interface WorkflowEditorApi {
  /** Currently active workflowId in the editor */
  workflowId: string | null;

  // Node operations
  addNodeAtPosition: (type: NodeType, position: { x: number; y: number }, parentLoopId?: string | null) => void;
  deleteNode: (nodeId: string) => void;
  updateNodeData: (nodeId: string, patch: Record<string, any>) => void;

  // Bulk operations (for adding pre-built nodes/edges)
  addBulkNodes: (nodes: WorkflowNode[]) => void;
  addBulkEdges: (edges: WorkflowEdge[]) => void;

  // Edge operations
  connectNodes: (sourceId: string, targetId: string, sourceHandle?: string, targetHandle?: string) => void;
  deleteEdge: (edgeId: string) => void;

  // Layout
  autoLayout: () => void;

  // Selection
  selectNode: (nodeId: string | null) => void;

  // Read state
  getNodes: () => WorkflowNode[];
  getEdges: () => WorkflowEdge[];
}

interface WorkflowActionState {
  /** Registered editor API (null when no editor is mounted) */
  editorApi: WorkflowEditorApi | null;

  /** Register the editor API (called by WorkflowEditor on mount) */
  registerEditor: (api: WorkflowEditorApi) => void;

  /** Unregister the editor API (called by WorkflowEditor on unmount) */
  unregisterEditor: (workflowId?: string | null) => void;
}

export const useWorkflowActionStore = create<WorkflowActionState>()((set, get) => ({
  editorApi: null,

  registerEditor: (api) => set({ editorApi: api }),

  unregisterEditor: (workflowId) => {
    const current = get().editorApi;
    if (!current || (workflowId !== undefined && current.workflowId !== workflowId)) return;
    set({ editorApi: null });
  },
}));
