/**
 * WorkflowList - 工作流列表组件
 * 
 * 显示用户的工作流列表，支持新建、打开、批量选择删除
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import clsx from 'clsx';
import { 
  Plus, 
  GitBranch, 
  Trash2, 
  Loader2,
  AlertCircle,
  RefreshCw,
  Edit2,
  Send,
  Check,
  X,
  PanelRight,
} from 'lucide-react';
import { useWorkflowList, useCreateWorkflow, useDeleteWorkflow, useUpdateWorkflow } from '../hooks/useWorkflow';
import { workflowApi } from '../api';
import type { Workflow, WorkflowListItem } from '../types';
import {
  ListItem,
  ListItemText,
  ListItemActions,
  ListItemActionButton,
} from '@/features/workspace/control-panel/components/ListItem';
import { AlertDialog } from '@/components/AlertDialog';
import { PublishDialog } from './WorkflowEditor/components/PublishDialog';

interface WorkflowListProps {
  selectedId?: string | null;
  onSelect?: (workflow: WorkflowListItem) => void;
  onOpenCanvas?: (workflow: WorkflowListItem) => void;
  onCreate?: (workflow: { id: string; name: string }) => void;
  onDelete?: (workflowId: string) => void;
  compact?: boolean;
  onBatchActionsChange?: (actions: React.ReactNode | null) => void;
}

export function WorkflowList({ selectedId: externalSelectedId, onSelect, onOpenCanvas, onCreate, onDelete, compact = false, onBatchActionsChange }: WorkflowListProps) {
  const { workflows, loading, error, refresh } = useWorkflowList();
  const { create, creating } = useCreateWorkflow();
  const { remove, deleting } = useDeleteWorkflow();
  const { update, updating } = useUpdateWorkflow();
  
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<WorkflowListItem | null>(null);
  
  // Publish dialog state
  const [publishWorkflow, setPublishWorkflow] = useState<Workflow | null>(null);
  const [loadingPublish, setLoadingPublish] = useState<string | null>(null);

  // Renaming state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);
  
  // 内部选中状态（如果外部没有传入 selectedId，则使用内部状态）
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const selectedId = externalSelectedId !== undefined ? externalSelectedId : internalSelectedId;

  // 批量选择状态
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [pendingBatchDelete, setPendingBatchDelete] = useState(false);
  const batchMode = checkedIds.size > 0;

  const COMPACT_LIMIT = 10;
  const [compactVisible, setCompactVisible] = useState(COMPACT_LIMIT);

  const toggleChecked = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCheckedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setCheckedIds(new Set(workflows.map(w => w.id)));
  }, [workflows]);

  const clearSelection = useCallback(() => {
    setCheckedIds(new Set());
  }, []);

  // When workflows change (e.g. after delete), prune stale checked IDs
  useEffect(() => {
    setCheckedIds(prev => {
      const validIds = new Set(workflows.map(w => w.id));
      const pruned = new Set([...prev].filter(id => validIds.has(id)));
      if (pruned.size !== prev.size) return pruned;
      return prev;
    });
  }, [workflows]);

  useEffect(() => {
    if (!compact || !onBatchActionsChange) return;
    if (!batchMode) { onBatchActionsChange(null); return; }
    onBatchActionsChange(
      <>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-bold text-blue-600">{checkedIds.size} selected</span>
          <button
            onClick={checkedIds.size === workflows.length ? clearSelection : selectAll}
            className="text-[10px] text-black/40 hover:text-black/70 transition-colors"
          >
            {checkedIds.size === workflows.length ? 'Deselect' : 'All'}
          </button>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setPendingBatchDelete(true)}
            disabled={batchDeleting}
            className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
            title="Delete selected"
          >
            {batchDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
          </button>
          <button onClick={clearSelection} className="p-1 text-black/30 hover:text-black/60 rounded transition-colors" title="Cancel">
            <X className="w-3 h-3" />
          </button>
        </div>
      </>
    );
  }, [compact, batchMode, checkedIds.size, workflows.length, batchDeleting, onBatchActionsChange, clearSelection, selectAll]);
  
  // Focus input when editing starts
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const handleDragStart = useCallback((e: React.DragEvent, workflow: WorkflowListItem) => {
    e.dataTransfer.setData('application/x-workflow-id', workflow.id);
    e.dataTransfer.setData('application/x-workflow-name', workflow.name);
    e.dataTransfer.effectAllowed = 'copy';
  }, []);

  const handleCreate = async () => {
    try {
      // 生成精确到秒的时间戳名称，避免重名
      const now = new Date();
      const timestamp = now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).replace(/\//g, '-');
      
      const newWorkflow = await create({
        name: `New Workflow ${timestamp}`,
        description: '',
      });
      
      // 刷新列表
      // await refresh(); // refresh handled by event listener
      
      // 选中新创建的工作流
      setInternalSelectedId(newWorkflow.id);
      
      onCreate?.({ id: newWorkflow.id, name: newWorkflow.name });
    } catch (err) {
      console.error('Failed to create workflow:', err);
    }
  };

  const handleDeleteClick = (workflow: WorkflowListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setPendingDelete(workflow);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    
    const idToDelete = pendingDelete.id;
    setDeletingId(idToDelete);
    setPendingDelete(null); // Close modal immediately

    try {
      await remove(idToDelete);
      
      // 如果删除的是当前选中的，清除选中状态
      if (selectedId === idToDelete) {
        setInternalSelectedId(null);
      }

      // 通知外部已删除
      onDelete?.(idToDelete);
      
      // refresh(); // refresh handled by event listener
    } catch (err) {
      console.error('Failed to delete workflow:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const startEditing = (workflow: WorkflowListItem) => {
    setEditingId(workflow.id);
    setEditName(workflow.name);
  };

  const submitRename = async () => {
    if (!editingId) return;
    
    const finalName = editName.trim();
    if (!finalName) {
      setEditingId(null);
      return;
    }

    try {
      // Only update if name changed
      const original = workflows.find(w => w.id === editingId);
      if (original && original.name !== finalName) {
        await update(editingId, { name: finalName });
        // refresh(); // refresh handled by event listener
      }
    } catch (err) {
      console.error('Failed to rename workflow:', err);
    } finally {
      setEditingId(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      submitRename();
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  };

  const handlePublishClick = async (workflow: WorkflowListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setLoadingPublish(workflow.id);
    try {
      const full = await workflowApi.get(workflow.id);
      setPublishWorkflow(full);
    } catch (err) {
      console.error('Failed to load workflow for publish:', err);
    } finally {
      setLoadingPublish(null);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className={clsx("flex flex-col relative", !compact && "h-full")}>
        {!compact && renderHeader()}
        <div className={clsx("flex items-center justify-center text-black/40", compact ? "py-4" : "flex-1")}>
          <Loader2 className="w-4 h-4 animate-spin" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={clsx("flex flex-col relative", !compact && "h-full")}>
        {!compact && renderHeader()}
        <div className={clsx("flex flex-col items-center justify-center gap-2 p-4", !compact && "flex-1")}>
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-[11px] text-black/60 text-center">{error.message}</span>
          <button
            onClick={refresh}
            className="flex items-center gap-1 text-[10px] text-orange-600 hover:text-orange-700"
          >
            <RefreshCw className="w-3 h-3" />
            Retry
          </button>
        </div>
      </div>
    );
  }
  
  const confirmBatchDelete = async () => {
    setPendingBatchDelete(false);
    setBatchDeleting(true);
    const idsToDelete = [...checkedIds];

    try {
      for (const id of idsToDelete) {
        setDeletingId(id);
        await remove(id);
        if (selectedId === id) {
          setInternalSelectedId(null);
        }
        onDelete?.(id);
      }
    } catch (err) {
      console.error('Failed to batch delete workflows:', err);
    } finally {
      setDeletingId(null);
      setBatchDeleting(false);
      setCheckedIds(new Set());
    }
  };

  function renderHeader() {
    if (batchMode) {
      return (
        <div className="flex items-center justify-between px-3 h-[36px] border-b border-divider bg-canvas flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-blue-600">
              {checkedIds.size} selected
            </span>
            <button
              onClick={checkedIds.size === workflows.length ? clearSelection : selectAll}
              className="text-[10px] text-black/50 hover:text-black/80 transition-colors"
            >
              {checkedIds.size === workflows.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPendingBatchDelete(true)}
              disabled={batchDeleting}
              className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
              title="Delete selected"
            >
              {batchDeleting ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Trash2 className="w-3 h-3" />
              )}
              Delete
            </button>
            <button
              onClick={clearSelection}
              className="p-1 hover:bg-black/5 rounded text-black/40 hover:text-black/80 transition-colors"
              title="Cancel selection"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="flex items-center justify-between px-4 h-[36px] border-b border-divider bg-canvas flex-shrink-0">
        <div className="flex items-center gap-2">
          <h3 className="text-[10px] font-bold text-black/40 uppercase tracking-wider">
            My Workflows
          </h3>
          <span className="text-[9px] font-mono text-black/30 bg-black/5 px-1 rounded-sm">
            {workflows.length}
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          <button 
            onClick={handleCreate}
            disabled={creating}
            className="p-1 hover:bg-black/5 rounded text-black/40 hover:text-black/80 transition-colors disabled:opacity-50"
            title="New Workflow"
          >
            {creating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Plus className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>
    );
  }


  const renderCompactItem = (workflow: WorkflowListItem) => {
    const isSelected = workflow.id === selectedId;
    const isDeleting = deletingId === workflow.id;
    const isEditing = editingId === workflow.id;
    const isChecked = checkedIds.has(workflow.id);

    return (
      <div
        key={workflow.id}
        className="px-2 py-[1px]"
      >
        <div
          draggable={!isEditing && !isDeleting && !batchMode}
          onDragStart={(e) => handleDragStart(e, workflow)}
          onClick={isDeleting ? undefined : () => {
            if (batchMode) {
              setCheckedIds(prev => {
                const next = new Set(prev);
                if (next.has(workflow.id)) next.delete(workflow.id);
                else next.add(workflow.id);
                return next;
              });
              return;
            }
            setInternalSelectedId(workflow.id);
            onSelect?.(workflow);
          }}
          onDoubleClick={isDeleting || batchMode ? undefined : () => startEditing(workflow)}
          className={clsx(
            'group relative flex items-center gap-2 pl-[10px] pr-[6px] py-[7px] text-[12px] rounded-lg transition-colors cursor-pointer select-none',
            isDeleting && 'opacity-40 cursor-not-allowed',
            isSelected ? 'bg-black/[0.08] text-black font-medium' : 'text-black/70 hover:bg-black/[0.04]',
          )}
        >
          <div
            onClick={(e) => { e.stopPropagation(); toggleChecked(workflow.id, e); }}
            className={clsx(
              'w-3.5 h-3.5 flex-shrink-0 flex items-center justify-center rounded-[3px] border transition-all cursor-pointer',
              isChecked
                ? 'bg-blue-500 border-blue-500 text-white'
                : batchMode
                  ? 'border-black/20 bg-transparent hover:border-black/40'
                  : 'border-transparent opacity-0 group-hover:opacity-100 group-hover:border-black/20 hover:border-black/40',
            )}
          >
            {isChecked && <Check className="w-2.5 h-2.5" strokeWidth={3} />}
          </div>

          {isEditing ? (
            <div className="flex-1 min-w-0" onClick={e => e.stopPropagation()}>
              <input
                ref={editInputRef}
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onBlur={submitRename}
                onKeyDown={handleKeyDown}
                className="w-full bg-white border border-blue-500 rounded px-1.5 py-0.5 text-[11px] text-black/90 focus:outline-none focus:ring-1 focus:ring-blue-500/20"
              />
            </div>
          ) : (
            <div className="flex-1 min-w-0">
              <div className="truncate text-[12px] leading-normal">{workflow.name}</div>
            </div>
          )}

          {!isEditing && !batchMode && (
            <div className="absolute right-[6px] top-1/2 -translate-y-1/2 flex items-center gap-0 opacity-0 group-hover:opacity-100 transition-opacity bg-white/90 backdrop-blur-sm shadow-sm rounded-md px-0.5">
              {onOpenCanvas && (
                <button onClick={(e) => { e.stopPropagation(); onOpenCanvas(workflow); }} className="p-0.5 text-black/25 hover:text-black/60 rounded transition-colors" title="Open Canvas">
                  <PanelRight className="w-3 h-3" />
                </button>
              )}
              <button onClick={(e) => { e.stopPropagation(); startEditing(workflow); }} className="p-0.5 text-black/25 hover:text-black/60 rounded transition-colors" title="Rename">
                <Edit2 className="w-3 h-3" />
              </button>
              <button onClick={(e) => handleDeleteClick(workflow, e)} className="p-0.5 text-black/25 hover:text-red-500 rounded transition-colors" title="Delete">
                {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className={clsx("flex flex-col relative", !compact && "h-full")}>
      {!compact && renderHeader()}

      {/* List */}
      <div className={clsx(!compact && "flex-1 overflow-y-auto")}>
        {workflows.length === 0 ? (
          <div className={clsx("flex flex-col items-center justify-center gap-2 py-4 px-3", !compact && "h-full gap-3 p-4")}>
            <GitBranch className={clsx(compact ? "w-5 h-5 text-black/10" : "w-8 h-8 text-black/10")} />
            <span className="text-[11px] text-black/40">No workflows yet</span>
            <button
              onClick={handleCreate}
              disabled={creating}
              className={clsx(
                "flex items-center gap-1.5 text-[11px] font-medium rounded transition-colors disabled:opacity-50",
                compact
                  ? "px-2.5 py-1 bg-black/80 hover:bg-black text-white"
                  : "px-3 py-1.5 bg-black hover:bg-black/80 text-white",
              )}
            >
              {creating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
              New Workflow
            </button>
          </div>
        ) : compact ? (
          <>
            {workflows.slice(0, compactVisible).map(renderCompactItem)}
            {(compactVisible < workflows.length || compactVisible > COMPACT_LIMIT) && (
              <div className="flex items-center justify-center gap-3 px-2 py-1">
                {compactVisible < workflows.length && (
                  <button
                    onClick={() => setCompactVisible(v => Math.min(v + COMPACT_LIMIT, workflows.length))}
                    className="text-[11px] text-black/40 hover:text-black/70 py-1 px-2 rounded-lg hover:bg-black/[0.04] transition-colors"
                  >
                    More ({workflows.length - compactVisible})
                  </button>
                )}
                {compactVisible > COMPACT_LIMIT && (
                  <button
                    onClick={() => setCompactVisible(COMPACT_LIMIT)}
                    className="text-[11px] text-black/40 hover:text-black/70 py-1 px-2 rounded-lg hover:bg-black/[0.04] transition-colors"
                  >
                    Less
                  </button>
                )}
              </div>
            )}
          </>
        ) : (
          workflows.map((workflow) => {
            const isSelected = workflow.id === selectedId;
            const isDeleting = deletingId === workflow.id;
            const isEditing = editingId === workflow.id;
            const isChecked = checkedIds.has(workflow.id);

            return (
              <ListItem
                key={workflow.id}
                selected={isSelected}
                disabled={isDeleting}
                draggable={!isEditing && !isDeleting && !batchMode}
                onDragStart={(e: React.DragEvent) => handleDragStart(e, workflow)}
                onClick={() => {
                  if (batchMode) {
                    setCheckedIds(prev => {
                      const next = new Set(prev);
                      if (next.has(workflow.id)) next.delete(workflow.id);
                      else next.add(workflow.id);
                      return next;
                    });
                    return;
                  }
                  setInternalSelectedId(workflow.id);
                  onSelect?.(workflow);
                }}
                onDoubleClick={batchMode ? undefined : () => startEditing(workflow)}
              >
                <div
                  onClick={(e) => toggleChecked(workflow.id, e)}
                  className={`
                    w-4 h-4 flex-shrink-0 flex items-center justify-center rounded-[3px] border transition-all cursor-pointer
                    ${isChecked
                      ? 'bg-blue-500 border-blue-500 text-white'
                      : batchMode
                        ? 'border-black/20 bg-transparent hover:border-black/40'
                        : 'border-transparent opacity-0 group-hover:opacity-100 group-hover:border-black/20 hover:border-black/40'
                    }
                  `}
                >
                  {isChecked && <Check className="w-3 h-3" strokeWidth={2.5} />}
                </div>
                {isEditing ? (
                  <div className="flex-1 min-w-0 mr-2" onClick={e => e.stopPropagation()}>
                    <input
                      ref={editInputRef}
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onBlur={submitRename}
                      onKeyDown={handleKeyDown}
                      className="w-full bg-white border border-blue-500 rounded px-1.5 py-0.5 text-[11px] text-black/90 focus:outline-none focus:ring-1 focus:ring-blue-500/20"
                    />
                  </div>
                ) : (
                  <ListItemText primary={workflow.name} secondary={formatDate(workflow.updated_at)} selected={isSelected} />
                )}
                {!isEditing && !batchMode && (
                  <ListItemActions>
                    <ListItemActionButton onClick={(e) => handlePublishClick(workflow, e)} title="Publish">
                      {loadingPublish === workflow.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                    </ListItemActionButton>
                    <ListItemActionButton onClick={(e) => { e.stopPropagation(); startEditing(workflow); }} title="Rename">
                      <Edit2 className="w-3.5 h-3.5" />
                    </ListItemActionButton>
                    <ListItemActionButton variant="danger" onClick={(e) => handleDeleteClick(workflow, e)} title="Delete">
                      {deletingId === workflow.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </ListItemActionButton>
                  </ListItemActions>
                )}
              </ListItem>
            );
          })
        )}
      </div>

      <AlertDialog
        open={!!pendingDelete}
        title="Delete Workflow?"
        description={`Are you sure you want to delete "${pendingDelete?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        isDestructive={true}
      />

      <AlertDialog
        open={pendingBatchDelete}
        title="Delete Selected Workflows?"
        description={`Are you sure you want to delete ${checkedIds.size} workflow${checkedIds.size > 1 ? 's' : ''}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={confirmBatchDelete}
        onCancel={() => setPendingBatchDelete(false)}
        isDestructive={true}
      />

      {publishWorkflow && (
        <PublishDialog
          open={!!publishWorkflow}
          workflow={publishWorkflow}
          onClose={() => setPublishWorkflow(null)}
          onUpdated={(updated) => {
            setPublishWorkflow(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

export default WorkflowList;
