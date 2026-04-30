import React, { useRef, useState, useCallback, useEffect, useMemo } from 'react';
import { observer } from 'mobx-react-lite';
import {
  ControlledTreeEnvironment,
  Tree,
  type TreeRef,
  type TreeItemIndex,
  type TreeItem,
  type DraggingPosition,
} from 'react-complex-tree';
import 'react-complex-tree/lib/style-modern.css';
import { useTranslation } from 'react-i18next';
import type { FileExplorerProps, FileItemData, FileTreeItems } from './types';
import { flattenFileTree } from './types';
import { useFileExplorerTree } from './hooks/useFileExplorerTree';
import { FileTreeNodeRenderer } from './components/FileTreeNode';
import { ContextMenu, MenuIcons, type ContextMenuAction } from './components/ContextMenu';
import { AlertDialog } from '@/components/AlertDialog';
import { Spin } from '@douyinfe/semi-ui';
import { useProject } from '@/shared';

const USE_POINTER_DND_FALLBACK = true;

export default observer(function FileExplorer({
  projectId,
  rootPath,
  enableLocking = true,
  storageKeyPrefix = 'fileExplorer',
  onFileSelect,
  onFileOpen,
  onFileTreeChange,
  onAddToChat,
}: FileExplorerProps) {
  const { t } = useTranslation();
  const { isSwitching } = useProject()
  const [noticeDialog, setNoticeDialog] = useState<{ title: string; description?: string } | null>(null);
  const handleExplorerError = useCallback((message: string) => {
    const normalized = String(message || '').toLowerCase();
    if (/already exists|destination already exists|eexist|重名|已存在/.test(normalized)) {
      setNoticeDialog({
        title: t('workspace.fileExplorer.error.duplicateTitle'),
        description: t('workspace.fileExplorer.error.duplicateDescription'),
      });
      return;
    }
    setNoticeDialog({
      title: t('workspace.fileExplorer.error.operationFailed'),
      description: message,
    });
  }, [t]);
  const treeRef = useRef<TreeRef<FileItemData> | null>(null);
  const treeId = useMemo(() => `${storageKeyPrefix}-tree`, [storageKeyPrefix]);
  const pointerDragIdsRef = useRef<string[]>([]);
  const pointerExpandTimerRef = useRef<number | null>(null);
  const pointerExpandTargetRef = useRef<string | null>(null);
  const pointerDragStartRef = useRef<{ x: number; y: number } | null>(null);
  const pointerDragActiveRef = useRef(false);
  const selectionAnchorRef = useRef<string | null>(null);

  const {
    data,
    isLoading,
    error,
    refresh,
    handleMove,
    handleRename,
    handleDelete,
    handleNewFile,
    handleNewFolder,
    handleCopy,
    handleCut,
    handlePaste,
    handleUnlock,
    handleLock,
    clipboard,
  } = useFileExplorerTree({ projectId, rootPath, enableLocking, onError: handleExplorerError });

  const refreshGlobalKey = `__${storageKeyPrefix}Refresh`;
  useEffect(() => {
    (window as any)[refreshGlobalKey] = refresh;
    return () => {
      delete (window as any)[refreshGlobalKey];
    };
  }, [refresh, refreshGlobalKey]);

  const [expandedItems, setExpandedItems] = useState<TreeItemIndex[]>([]);
  const [selectedItems, setSelectedItems] = useState<TreeItemIndex[]>([]);
  const [focusedItem, setFocusedItem] = useState<TreeItemIndex | undefined>();
  const [pointerHoverItemId, setPointerHoverItemId] = useState<string | null>(null);
  const [pointerDragLabel, setPointerDragLabel] = useState<string | null>(null);
  const [pointerDragPos, setPointerDragPos] = useState<{ x: number; y: number } | null>(null);
  const [isPointerDragging, setIsPointerDragging] = useState(false);
  const [externalHoverFolderId, setExternalHoverFolderId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    nodeId: string | null;
  } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{
    ids: string[];
    name: string;
    type: 'file' | 'folder' | 'mixed';
  } | null>(null);

  const expandGlobalKey = `__${storageKeyPrefix}Expand`;
  useEffect(() => {
    (window as any)[expandGlobalKey] = (itemId: string) => {
      setExpandedItems(prev => (prev.includes(itemId) ? prev : [...prev, itemId]));
      setSelectedItems([itemId]);
      setFocusedItem(itemId);
    };
    return () => {
      delete (window as any)[expandGlobalKey];
    };
  }, [expandGlobalKey]);

  useEffect(() => {
    if (onFileTreeChange && data.length > 0) {
      onFileTreeChange(data);
    }
  }, [data, onFileTreeChange]);

  const items: FileTreeItems = useMemo(() => flattenFileTree(data), [data]);
  const rootNodeId = data[0]?.id;
  const cutPendingIdSet = useMemo(
    () => new Set((clipboard?.type === 'cut' ? clipboard.nodes.map(node => node.id) : [])),
    [clipboard]
  );
  const modifiedBranchIdSet = useMemo(() => {
    const memo = new Map<string, boolean>();
    const visit = (id: string): boolean => {
      if (memo.has(id)) return memo.get(id) ?? false;
      const treeItem = items[id];
      if (!treeItem) {
        memo.set(id, false);
        return false;
      }
      const selfModified = Boolean(treeItem.data?.modified);
      const childModified = (treeItem.children ?? []).some(childId => visit(String(childId)));
      const result = selfModified || childModified;
      memo.set(id, result);
      return result;
    };
    Object.keys(items).forEach(id => visit(id));
    return new Set(Array.from(memo.entries()).filter(([, val]) => val).map(([id]) => id));
  }, [items]);

  const parentById = useMemo(() => {
    const mapping: Record<string, string> = {};
    Object.entries(items).forEach(([id, treeItem]) => {
      (treeItem.children ?? []).forEach(childId => {
        mapping[String(childId)] = id;
      });
    });
    return mapping;
  }, [items]);

  const resolveDropParentId = useCallback(
    (targetId: string): string | null => {
      const targetItem = items[targetId];
      if (!targetItem) return rootNodeId ?? null;
      if (targetItem.isFolder) return targetId;
      return parentById[targetId] ?? rootNodeId ?? null;
    },
    [items, parentById, rootNodeId]
  );

  const resolveHoverFolderId = useCallback(
    (hoveredId: string | null, dragIds: string[]): string | null => {
      if (!hoveredId) return null;
      const hoveredItem = items[hoveredId];
      if (!hoveredItem) return null;
      const folderId = hoveredItem.isFolder
        ? hoveredId
        : (parentById[hoveredId] ?? rootNodeId ?? null);
      if (!folderId || dragIds.includes(folderId)) return null;
      return folderId;
    },
    [items, parentById, rootNodeId]
  );

  const getDropFolderFromItemId = useCallback((itemId: string | null): string | null => {
    if (!itemId) return rootNodeId ?? null;
    const targetItem = items[itemId];
    if (!targetItem) return rootNodeId ?? null;
    if (targetItem.isFolder) return itemId;
    return parentById[itemId] ?? rootNodeId ?? null;
  }, [items, parentById, rootNodeId]);

  const scheduleAutoExpandForFolder = useCallback(
    (folderId: string | null) => {
      if (pointerExpandTimerRef.current !== null) {
        window.clearTimeout(pointerExpandTimerRef.current);
        pointerExpandTimerRef.current = null;
      }
      pointerExpandTargetRef.current = folderId;
      if (!folderId) return;
      const folderItem = items[folderId];
      if (!folderItem?.isFolder) return;
      if (expandedItems.includes(folderItem.index)) return;

      pointerExpandTimerRef.current = window.setTimeout(() => {
        setExpandedItems(prev => (prev.includes(folderItem.index) ? prev : [...prev, folderItem.index]));
        pointerExpandTimerRef.current = null;
      }, 320);
    },
    [items, expandedItems]
  );

  const getStorageKey = useCallback(
    () => `${storageKeyPrefix}_viewState_${projectId || rootPath || 'default'}`,
    [projectId, rootPath, storageKeyPrefix]
  );

  useEffect(() => {
    try {
      const saved = localStorage.getItem(getStorageKey());
      if (saved) setExpandedItems(JSON.parse(saved));
    } catch {
      // ignore
    }
  }, [getStorageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(getStorageKey(), JSON.stringify(expandedItems));
    } catch {
      // ignore
    }
  }, [expandedItems, getStorageKey]);

  useEffect(() => {
    const validSet = new Set(Object.keys(items));
    setExpandedItems(prev => prev.filter(id => validSet.has(String(id))));
    setSelectedItems(prev => prev.filter(id => validSet.has(String(id))));
    setFocusedItem(prev => (prev && validSet.has(String(prev)) ? prev : undefined));
  }, [items]);

  useEffect(() => {
    if (!rootNodeId) return;
    setExpandedItems(prev => (prev.includes(rootNodeId) ? prev : [...prev, rootNodeId]));
  }, [rootNodeId]);

  useEffect(() => {
    const clearPointerDrag = () => {
      pointerDragIdsRef.current = [];
      pointerDragStartRef.current = null;
      pointerDragActiveRef.current = false;
      setPointerHoverItemId(null);
      setExternalHoverFolderId(null);
      setPointerDragLabel(null);
      setPointerDragPos(null);
      setIsPointerDragging(false);
      pointerExpandTargetRef.current = null;
      if (pointerExpandTimerRef.current !== null) {
        window.clearTimeout(pointerExpandTimerRef.current);
        pointerExpandTimerRef.current = null;
      }
    };
    window.addEventListener('pointerup', clearPointerDrag);
    window.addEventListener('pointercancel', clearPointerDrag);
    return () => {
      window.removeEventListener('pointerup', clearPointerDrag);
      window.removeEventListener('pointercancel', clearPointerDrag);
    };
  }, []);

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (pointerDragIdsRef.current.length === 0) return;
      setPointerDragPos({ x: e.clientX, y: e.clientY });
      const start = pointerDragStartRef.current;
      if (!start || pointerDragActiveRef.current) return;
      const distance = Math.hypot(e.clientX - start.x, e.clientY - start.y);
      if (distance >= 4) {
        pointerDragActiveRef.current = true;
        setIsPointerDragging(true);
      }

      const hoveredElement = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
      const hoveredItemId = hoveredElement?.closest('[data-rct-item-id]')?.getAttribute('data-rct-item-id') ?? null;
      const dragIds = pointerDragIdsRef.current;
      const validHoverId = resolveHoverFolderId(hoveredItemId, dragIds);

      setPointerHoverItemId(prev => (prev === validHoverId ? prev : validHoverId));

    };

    window.addEventListener('pointermove', handlePointerMove);
    return () => window.removeEventListener('pointermove', handlePointerMove);
  }, [items, resolveHoverFolderId]);

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  const handleContextMenuEvent = useCallback((e: React.MouseEvent, nodeId: string | null) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId });
  }, []);

  const handleContainerContextMenu = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest('[data-rct-item-id]')) return;
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId: null });
  }, []);

  const getItemData = useCallback((id: TreeItemIndex): FileItemData | null => {
    return items[id]?.data ?? null;
  }, [items]);

  const getVisibleItemOrder = useCallback((): string[] => {
    const order: string[] = [];
    const expandedSet = new Set(expandedItems.map(id => String(id)));
    const visit = (id: string) => {
      const treeItem = items[id];
      if (!treeItem) return;
      if (id !== 'root') order.push(id);
      if (!treeItem.isFolder) return;
      if (id !== 'root' && !expandedSet.has(id)) return;
      (treeItem.children ?? []).forEach(childId => visit(String(childId)));
    };
    visit('root');
    return order;
  }, [items, expandedItems]);

  const writeTextToClipboard = useCallback(async (text: string) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for environments where Clipboard API is unavailable.
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-99999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
    }
  }, []);

  const toRelativePath = useCallback((absolutePath: string): string => {
    const rootPath = String(rootNodeId ?? '');
    if (!rootPath) return absolutePath;
    const normalizedAbs = absolutePath.replace(/\\/g, '/');
    const normalizedRoot = rootPath.replace(/\\/g, '/').replace(/\/+$/, '');
    if (normalizedAbs === normalizedRoot) return '.';
    if (normalizedAbs.startsWith(`${normalizedRoot}/`)) {
      return normalizedAbs.slice(normalizedRoot.length + 1);
    }
    return absolutePath;
  }, [rootNodeId]);

  const getContextTargetIds = useCallback((nodeId: string | null): string[] => {
    if (!nodeId) return [];
    const normalizedSelected = selectedItems
      .map(id => String(id))
      .filter(id => !!items[id]);
    if (normalizedSelected.length > 1 && normalizedSelected.includes(nodeId)) {
      return normalizedSelected;
    }
    return [nodeId];
  }, [selectedItems, items]);

  const importFilesToTarget = useCallback(async (targetNodeId: string | null) => {
    const electron = window.electron as any;
    if (!electron?.showAddFilesToWorkspaceDialog || !electron?.fsCopy) return;

    const targetFolderId = getDropFolderFromItemId(targetNodeId) ?? rootNodeId ?? null;
    if (!targetFolderId) return;
    const targetFolderPath = String(targetFolderId);

    const { canceled, filePaths } = await electron.showAddFilesToWorkspaceDialog();
    if (canceled || !filePaths?.length) return;

    const uniquePaths = Array.from(new Set(filePaths as string[]));
    const basenameFromPath = (filePath: string) => {
      const normalized = filePath.replace(/[/\\]+$/, '');
      const parts = normalized.split(/[/\\]/);
      return parts[parts.length - 1] || '';
    };
    const joinPath = (parentPath: string, fileName: string) => {
      const sep = parentPath.includes('\\') ? '\\' : '/';
      return `${parentPath.replace(/[/\\]+$/, '')}${sep}${fileName}`;
    };
    const withSuffix = (name: string, suffix: number) => {
      const lastDot = name.lastIndexOf('.');
      if (lastDot <= 0) return `${name}_${suffix}`;
      return `${name.slice(0, lastDot)}_${suffix}${name.slice(lastDot)}`;
    };

    let copiedCount = 0;
    for (const sourcePath of uniquePaths) {
      const baseName = basenameFromPath(sourcePath);
      if (!baseName) continue;
      let candidateName = baseName;
      let candidateDest = joinPath(targetFolderPath, candidateName);
      for (let attempt = 0; attempt <= 50; attempt += 1) {
        try {
          await electron.fsCopy(sourcePath, candidateDest);
          copiedCount += 1;
          break;
        } catch (err: any) {
          const message = String(err?.message || err);
          const existsConflict = /already exists|Destination already exists|EEXIST|exist/i.test(message);
          if (!existsConflict) break;
          candidateName = withSuffix(baseName, attempt + 1);
          candidateDest = joinPath(targetFolderPath, candidateName);
        }
      }
    }

    if (copiedCount > 0) {
      setExpandedItems(prev => (prev.includes(targetFolderId) ? prev : [...prev, targetFolderId]));
      refresh();
    }
  }, [getDropFolderFromItemId, rootNodeId, refresh]);

  const getContextMenuActions = useCallback((): ContextMenuAction[] => {
    if (!contextMenu) return [];
    const nodeId = contextMenu.nodeId;
    const isEmptyArea = nodeId === null;
    const isRoot = nodeId === 'root' || (nodeId && data.length > 0 && nodeId === data[0]?.id);
    const hasClipboard = clipboard !== null || !!(window.electron as any)?.fsGetClipboardFilePaths;
    const itemData = nodeId ? getItemData(nodeId) : null;
    const isLocked = itemData?.isLocked ?? false;
    const targetIds = getContextTargetIds(nodeId);
    const targetItemsData = targetIds
      .map(id => getItemData(id))
      .filter((d): d is FileItemData => !!d);
    const hasLockedTarget = targetItemsData.some(d => d.isLocked);
    const isSingleTarget = targetIds.length === 1;

    const actions: ContextMenuAction[] = [];
    const createTargetId = isEmptyArea ? (rootNodeId ?? null) : nodeId;
    actions.push({
      id: 'new-file',
      label: t('workspace.fileExplorer.contextMenu.newFile'),
      icon: MenuIcons.newFile,
      onClick: () => handleNewFile(createTargetId),
    });
    actions.push({
      id: 'new-folder',
      label: t('workspace.fileExplorer.contextMenu.newFolder'),
      icon: MenuIcons.newFolder,
      onClick: () => handleNewFolder(createTargetId),
    });
    actions.push({
      id: 'import-files',
      label: t('workspace.fileExplorer.contextMenu.importFiles'),
      icon: MenuIcons.importFiles,
      onClick: () => void importFilesToTarget(createTargetId),
    });

    if (hasClipboard) {
      actions.push({ id: 'sep-paste', separator: true, label: '', onClick: () => {} });
      actions.push({
        id: 'paste',
        label: t('workspace.fileExplorer.contextMenu.paste'),
        icon: clipboard?.type === 'cut' ? MenuIcons.cut : MenuIcons.copy,
        shortcut: 'Ctrl+V',
        onClick: () => handlePaste(isEmptyArea ? null : nodeId),
      });
    }

    if (isEmptyArea) return actions;

    if (!isRoot && nodeId) {
      actions.push({ id: 'sep-1', separator: true, label: '', onClick: () => {} });
      actions.push({
        id: 'rename',
        label: t('workspace.fileExplorer.contextMenu.rename'),
        icon: MenuIcons.rename,
        shortcut: 'F2',
        disabled: !isSingleTarget || isLocked,
        onClick: () => {
          if (isSingleTarget && !isLocked) treeRef.current?.startRenamingItem(nodeId);
        },
      });

      actions.push({ id: 'sep-2', separator: true, label: '', onClick: () => {} });

      actions.push({
        id: 'copy',
        label: t('workspace.fileExplorer.contextMenu.copy'),
        icon: MenuIcons.copy,
        shortcut: 'Ctrl+C',
        onClick: () => handleCopy(targetIds),
      });
      actions.push({
        id: 'cut',
        label: t('workspace.fileExplorer.contextMenu.cut'),
        icon: MenuIcons.cut,
        shortcut: 'Ctrl+X',
        disabled: hasLockedTarget,
        onClick: () => {
          if (!hasLockedTarget) handleCut(targetIds);
        },
      });

      actions.push({ id: 'sep-3', separator: true, label: '', onClick: () => {} });

      const chatTargets = targetItemsData.filter(d => !!d.path);
      if (chatTargets.length > 0 && onAddToChat) {
        actions.push({
          id: 'add-to-chat',
          label: targetIds.length > 1
            ? t('workspace.fileExplorer.contextMenu.addSelectedToChat')
            : t('workspace.fileExplorer.contextMenu.addToChat'),
          icon: MenuIcons.addToChat,
          onClick: () => {
            chatTargets.forEach(target => {
              if (target.path) onAddToChat(target.path, target.name, target.type);
            });
          },
        });
      }

      const pathTargets = targetItemsData.filter(d => !!d.path);
      if (pathTargets.length > 0) {
        actions.push({
          id: 'copy-path',
          label: t('workspace.fileExplorer.contextMenu.copyPath'),
          icon: MenuIcons.copyPath,
          onClick: () => {
            const copiedText = pathTargets.map(d => d.path as string).join('\n');
            void writeTextToClipboard(copiedText);
          },
        });
        actions.push({
          id: 'copy-relative-path',
          label: t('workspace.fileExplorer.contextMenu.copyRelativePath'),
          icon: MenuIcons.copyPath,
          onClick: () => {
            const copiedText = pathTargets
              .map(d => toRelativePath(d.path as string))
              .join('\n');
            void writeTextToClipboard(copiedText);
          },
        });
      }

      actions.push({ id: 'sep-4', separator: true, label: '', onClick: () => {} });
      actions.push({
        id: 'delete',
        label: t('workspace.fileExplorer.contextMenu.delete'),
        icon: MenuIcons.delete,
        shortcut: 'Del',
        disabled: hasLockedTarget,
        onClick: () => {
          if (!hasLockedTarget && targetItemsData.length > 0) {
            const first = targetItemsData[0];
            const hasFile = targetItemsData.some(d => d.type === 'file');
            const hasFolder = targetItemsData.some(d => d.type === 'folder');
            const deleteType = hasFile && hasFolder ? 'mixed' : (hasFolder ? 'folder' : 'file');
            closeContextMenu();
            setPendingDelete({
              ids: targetIds,
              name: targetItemsData.length > 1 ? `${first.name} +${targetItemsData.length - 1}` : first.name,
              type: deleteType,
            });
          }
        },
      });
    }

    return actions;
  }, [contextMenu, clipboard, data, items, getItemData, getContextTargetIds, handleNewFile, handleNewFolder, handleCopy, handleCut, handlePaste, onAddToChat, closeContextMenu, rootNodeId, importFilesToTarget, t, writeTextToClipboard, toRelativePath]);

  const remapTreeItemIndex = useCallback(
    (index: TreeItemIndex, oldPath: string, newPath: string): TreeItemIndex => {
      if (typeof index !== 'string') return index;
      if (index === oldPath) return newPath;
      if (index.startsWith(`${oldPath}/`) || index.startsWith(`${oldPath}\\`)) {
        return `${newPath}${index.slice(oldPath.length)}`;
      }
      return index;
    },
    []
  );

  const handleDrop = useCallback(
    (dragItems: TreeItem<FileItemData>[], target: DraggingPosition) => {
      let parentId: string | null = null;
      if (target.targetType === 'item') parentId = target.targetItem as string;
      else if (target.targetType === 'between-items') parentId = target.parentItem as string;
      else if (target.targetType === 'root') parentId = rootNodeId ?? null;

      if (parentId !== null) {
        const dragIds = dragItems.map(i => i.index as string);
        handleMove({ dragIds, parentId, index: 0 });
      }
    },
    [handleMove, rootNodeId]
  );

  const handleItemDoubleClick = useCallback(
    (item: TreeItem<FileItemData>) => {
      if (item.data.type === 'file' && item.data.path && onFileOpen) {
        onFileOpen(item.data.path, item.data.name);
      }
    },
    [onFileOpen]
  );

  const handleRenameItem = useCallback(
    async (item: TreeItem<FileItemData>, newName: string) => {
      const renameResult = await handleRename({ id: item.index as string, name: newName });
      if (!renameResult) return;
      const { oldPath, newPath } = renameResult;
      setExpandedItems(prev => prev.map(id => remapTreeItemIndex(id, oldPath, newPath)));
      setSelectedItems(prev => prev.map(id => remapTreeItemIndex(id, oldPath, newPath)));
      setFocusedItem(prev => (prev ? remapTreeItemIndex(prev, oldPath, newPath) : prev));
    },
    [handleRename, remapTreeItemIndex]
  );

  const handlePointerDownNode = useCallback((e: React.PointerEvent, item: TreeItem<FileItemData>) => {
    if (!USE_POINTER_DND_FALLBACK) return;
    if (e.button !== 0) return;
    const itemId = String(item.index);
    if (e.shiftKey) {
      const anchorId = selectionAnchorRef.current ?? (selectedItems[0] ? String(selectedItems[0]) : null);
      const visibleOrder = getVisibleItemOrder();
      const anchorIndex = anchorId ? visibleOrder.indexOf(anchorId) : -1;
      const targetIndex = visibleOrder.indexOf(itemId);
      if (anchorIndex >= 0 && targetIndex >= 0) {
        e.preventDefault();
        e.stopPropagation();
        const [start, end] = anchorIndex <= targetIndex
          ? [anchorIndex, targetIndex]
          : [targetIndex, anchorIndex];
        const rangeSelection = visibleOrder.slice(start, end + 1);
        setSelectedItems(rangeSelection);
        setFocusedItem(itemId);
      }
      pointerDragIdsRef.current = [];
      pointerDragStartRef.current = null;
      pointerDragActiveRef.current = false;
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) {
      pointerDragIdsRef.current = [];
      pointerDragStartRef.current = null;
      pointerDragActiveRef.current = false;
      return;
    }
    if (itemId === String(rootNodeId)) return;
    const normalizedSelectedIds = selectedItems
      .map(id => String(id))
      .filter(id => id !== String(rootNodeId) && !!items[id]);
    const shouldUseSelection = normalizedSelectedIds.length > 1 && normalizedSelectedIds.includes(itemId);
    let dragIds = shouldUseSelection ? normalizedSelectedIds : [itemId];
    if (enableLocking) {
      dragIds = dragIds.filter(id => !items[id]?.data?.isLocked);
    }
    if (dragIds.length === 0) return;

    pointerDragIdsRef.current = dragIds;
    pointerDragStartRef.current = { x: e.clientX, y: e.clientY };
    pointerDragActiveRef.current = false;
    setIsPointerDragging(false);
    const primaryName = item.data.name;
    setPointerDragLabel(dragIds.length > 1 ? `${primaryName} +${dragIds.length - 1}` : primaryName);
    setPointerDragPos({ x: e.clientX, y: e.clientY });
  }, [rootNodeId, selectedItems, items, enableLocking, getVisibleItemOrder]);

  const handlePointerUpNode = useCallback((e: React.PointerEvent, targetItem: TreeItem<FileItemData>) => {
    if (!USE_POINTER_DND_FALLBACK) return;
    if (e.button !== 0) return;
    const wasDragging = pointerDragActiveRef.current;
    const dragIds = pointerDragIdsRef.current;
    pointerDragIdsRef.current = [];
    pointerDragStartRef.current = null;
    pointerDragActiveRef.current = false;
    pointerExpandTargetRef.current = null;
    setPointerHoverItemId(null);
    setPointerDragLabel(null);
    setPointerDragPos(null);
    setIsPointerDragging(false);
    if (pointerExpandTimerRef.current !== null) {
      window.clearTimeout(pointerExpandTimerRef.current);
      pointerExpandTimerRef.current = null;
    }
    if (!wasDragging) return;
    if (dragIds.length === 0) return;

    const targetId = pointerHoverItemId ?? String(targetItem.index);
    if (dragIds.includes(targetId)) return;
    // Pointer fallback path for Electron when HTML5 drag events are unreliable.
    const parentId = resolveDropParentId(targetId);
    if (!parentId || dragIds.includes(parentId)) return;
    handleMove({ dragIds, parentId, index: 0 });
  }, [pointerHoverItemId, resolveDropParentId, handleMove]);

  const handleContainerPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!USE_POINTER_DND_FALLBACK) return;
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('[data-rct-item-id]')) return;
    const wasDragging = pointerDragActiveRef.current;

    const dragIds = pointerDragIdsRef.current;
    pointerDragIdsRef.current = [];
    pointerDragStartRef.current = null;
    pointerDragActiveRef.current = false;
    pointerExpandTargetRef.current = null;
    setPointerHoverItemId(null);
    setPointerDragLabel(null);
    setPointerDragPos(null);
    setIsPointerDragging(false);
    if (pointerExpandTimerRef.current !== null) {
      window.clearTimeout(pointerExpandTimerRef.current);
      pointerExpandTimerRef.current = null;
    }
    if (!wasDragging) return;
    if (dragIds.length === 0) return;

    const parentId = rootNodeId ?? null;
    if (!parentId || dragIds.includes(parentId)) return;
    handleMove({ dragIds, parentId, index: 0 });
  }, [rootNodeId, handleMove]);

  const handlePointerEnterNode = useCallback((e: React.PointerEvent, item: TreeItem<FileItemData>) => {
    if (!USE_POINTER_DND_FALLBACK) return;
    const dragIds = pointerDragIdsRef.current;
    if (dragIds.length === 0) return;
    const folderId = resolveHoverFolderId(String(item.index), dragIds);
    setPointerHoverItemId(folderId);
    scheduleAutoExpandForFolder(folderId);
  }, [resolveHoverFolderId, scheduleAutoExpandForFolder]);

  const handlePointerLeaveNode = useCallback((e: React.PointerEvent, item: TreeItem<FileItemData>) => {
    if (!USE_POINTER_DND_FALLBACK) return;
    const dragIds = pointerDragIdsRef.current;
    if (dragIds.length === 0) return;
    const currentFolderId = resolveHoverFolderId(String(item.index), dragIds);
    if (pointerExpandTargetRef.current === currentFolderId) {
      scheduleAutoExpandForFolder(null);
    }
  }, [resolveHoverFolderId, scheduleAutoExpandForFolder]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (
      e.target instanceof HTMLInputElement ||
      e.target instanceof HTMLTextAreaElement ||
      (e.target as HTMLElement)?.isContentEditable
    ) return;

    const normalizedSelected = selectedItems
      .map(id => String(id))
      .filter(id => !!items[id] && id !== 'root' && id !== String(rootNodeId));
    const primaryId = normalizedSelected[0] as string | undefined;
    const primaryData = primaryId ? getItemData(primaryId) : null;
    const hasLockedTarget = normalizedSelected.some(id => getItemData(id)?.isLocked);
    const lowerKey = e.key.toLowerCase();
    const isMod = e.ctrlKey || e.metaKey;

    if (e.key === 'F2' && primaryId && normalizedSelected.length === 1) {
      e.preventDefault();
      if (!(primaryData?.isLocked ?? false)) {
        treeRef.current?.startRenamingItem(primaryId);
      }
      return;
    }

    if (isMod && lowerKey === 'c') {
      if (!primaryId) return;
      e.preventDefault();
      handleCopy(normalizedSelected);
      return;
    }

    if (isMod && lowerKey === 'x') {
      if (!primaryId) return;
      e.preventDefault();
      if (!hasLockedTarget) {
        handleCut(normalizedSelected);
      }
      return;
    }

    if (isMod && lowerKey === 'v') {
      e.preventDefault();
      void handlePaste(primaryId ?? null);
      return;
    }

    if (!primaryId) return;

    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      if (hasLockedTarget) return;
      const targetItemsData = normalizedSelected
        .map(id => getItemData(id))
        .filter((d): d is FileItemData => !!d);
      if (targetItemsData.length === 0) return;
      const first = targetItemsData[0];
      const hasFile = targetItemsData.some(d => d.type === 'file');
      const hasFolder = targetItemsData.some(d => d.type === 'folder');
      const deleteType = hasFile && hasFolder ? 'mixed' : (hasFolder ? 'folder' : 'file');
      setPendingDelete({
        ids: normalizedSelected,
        name: targetItemsData.length > 1 ? `${first.name} +${targetItemsData.length - 1}` : first.name,
        type: deleteType,
      });
    }
  }, [selectedItems, items, rootNodeId, getItemData, handleCopy, handleCut, handlePaste]);

  const isInPointerHoverFolder = useCallback((itemId: string) => {
    const activeHoverFolderId = pointerHoverItemId ?? externalHoverFolderId;
    if (!activeHoverFolderId) return false;
    if (itemId === activeHoverFolderId) return true;
    return (
      itemId.startsWith(`${activeHoverFolderId}/`) ||
      itemId.startsWith(`${activeHoverFolderId}\\`)
    );
  }, [pointerHoverItemId, externalHoverFolderId]);

  const withSuffix = useCallback((name: string, suffix: number) => {
    const lastDot = name.lastIndexOf('.');
    if (lastDot <= 0) return `${name}_${suffix}`;
    return `${name.slice(0, lastDot)}_${suffix}${name.slice(lastDot)}`;
  }, []);

  const basenameFromPath = useCallback((filePath: string) => {
    const normalized = filePath.replace(/[/\\]+$/, '');
    const parts = normalized.split(/[/\\]/);
    return parts[parts.length - 1] || '';
  }, []);

  const joinPath = useCallback((parentPath: string, fileName: string) => {
    if (!parentPath) return fileName;
    const sep = parentPath.includes('\\') ? '\\' : '/';
    return `${parentPath.replace(/[/\\]+$/, '')}${sep}${fileName}`;
  }, []);

  const copyExternalPathsToFolder = useCallback(async (sourcePaths: string[], folderId: string | null) => {
    const electron = window.electron as any;
    if (!electron?.fsCopy) return;
    const targetFolderId = folderId ?? rootNodeId ?? null;
    if (!targetFolderId) return;

    const targetFolderPath = String(targetFolderId);
    let copiedCount = 0;
    const failures: string[] = [];

    for (const sourcePath of sourcePaths) {
      const baseName = basenameFromPath(sourcePath);
      if (!baseName) continue;
      let candidateName = baseName;
      let candidateDest = joinPath(targetFolderPath, candidateName);
      let copied = false;

      for (let attempt = 0; attempt <= 50; attempt += 1) {
        try {
          await electron.fsCopy(sourcePath, candidateDest);
          copied = true;
          copiedCount += 1;
          break;
        } catch (err: any) {
          const message = String(err?.message || err);
          const existsConflict = /already exists|Destination already exists|EEXIST|exist/i.test(message);
          if (!existsConflict) {
            failures.push(`${baseName}: ${message}`);
            break;
          }
          candidateName = withSuffix(baseName, attempt + 1);
          candidateDest = joinPath(targetFolderPath, candidateName);
        }
      }

      if (!copied) {
        failures.push(`${baseName}: copy failed`);
      }
    }

    if (copiedCount > 0) {
      setExpandedItems(prev => (targetFolderId && prev.includes(targetFolderId) ? prev : [...prev, targetFolderId]));
      refresh();
    }
    if (failures.length > 0) {
      console.warn('[FileExplorer] External drop copy failed:', failures.slice(0, 5));
    }
  }, [rootNodeId, basenameFromPath, joinPath, withSuffix, refresh]);

  const handleExternalDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    const hoveredElement = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
    const hoveredItemId = hoveredElement?.closest('[data-rct-item-id]')?.getAttribute('data-rct-item-id') ?? null;
    const folderId = getDropFolderFromItemId(hoveredItemId);
    setExternalHoverFolderId(folderId);
    scheduleAutoExpandForFolder(folderId);
  }, [getDropFolderFromItemId, scheduleAutoExpandForFolder]);

  const handleExternalDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setExternalHoverFolderId(null);
      scheduleAutoExpandForFolder(null);
    }
  }, [scheduleAutoExpandForFolder]);

  const handleExternalDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    const sourcePaths = files
      .map(file => (file as any).path as string | undefined)
      .filter((p): p is string => !!p);
    const uniquePaths = Array.from(new Set(sourcePaths));

    const hoveredElement = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
    const hoveredItemId = hoveredElement?.closest('[data-rct-item-id]')?.getAttribute('data-rct-item-id') ?? null;
    const folderId = getDropFolderFromItemId(hoveredItemId) ?? externalHoverFolderId ?? rootNodeId ?? null;

    setExternalHoverFolderId(null);
    scheduleAutoExpandForFolder(null);
    if (uniquePaths.length === 0) return;
    await copyExternalPathsToFolder(uniquePaths, folderId);
  }, [getDropFolderFromItemId, externalHoverFolderId, rootNodeId, scheduleAutoExpandForFolder, copyExternalPathsToFolder]);

  return <Spin spinning={isSwitching}>
    <div
      className="w-full bg-[#F2F1EE] relative outline-none rct-dark-theme no-drag pointer-events-auto"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onPointerUp={handleContainerPointerUp}
      onContextMenu={handleContainerContextMenu}
      onDragOver={handleExternalDragOver}
      onDragLeave={handleExternalDragLeave}
      onDrop={handleExternalDrop}
    >
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-sm text-gray-500">加载中...</div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-sm text-red-500">错误: {error}</div>
        </div>
      )}
      {!isLoading && !error && Object.keys(items).length > 1 && (
        <>
          <div className="overflow-x-hidden">
            <ControlledTreeEnvironment<FileItemData>
              items={items}
              getItemTitle={item => item.data.name}
              viewState={{
                [treeId]: {
                  expandedItems,
                  selectedItems,
                  focusedItem,
                },
              }}
              onExpandItem={item =>
                setExpandedItems(prev =>
                  prev.includes(item.index) ? prev : [...prev, item.index]
                )
              }
              onCollapseItem={item =>
                setExpandedItems(prev => prev.filter(i => i !== item.index))
              }
              onSelectItems={nextSelected => {
                const normalized = nextSelected.filter(id => !!items[id]);
                const next = normalized;
                setSelectedItems(next);
                if (next.length === 1) {
                  selectionAnchorRef.current = String(next[0]);
                  const d = getItemData(next[0]);
                  if (d?.path && onFileSelect) onFileSelect(d.path);
                }
              }}
              onFocusItem={item => setFocusedItem(item.index)}
              canDragAndDrop
              canDropOnFolder
              canReorderItems
              canDrag={dragItems =>
                !enableLocking || dragItems.every(item => !(item.data as FileItemData).isLocked)
              }
              canDropAt={(dragItems, target) => {
                if (!enableLocking) return true;
                if (target.targetType === 'item') {
                  const targetData = items[target.targetItem]?.data;
                  if (targetData?.isLocked && String(target.targetItem) !== String(rootNodeId)) return false;
                }
                if (target.targetType === 'between-items') {
                  const parentData = items[target.parentItem]?.data;
                  if (parentData?.isLocked && String(target.parentItem) !== String(rootNodeId)) return false;
                }
                return true;
              }}
              onDrop={handleDrop}
              canRename
              onRenameItem={handleRenameItem}
              renderRenameInput={({ inputProps, inputRef, submitButtonProps, formProps }) => (
                <form {...formProps} className="flex-1 min-w-0">
                  <input
                    {...inputProps}
                    ref={inputRef}
                    className="bg-white border border-orange-400 rounded px-1.5 py-0.5 text-black outline-none w-full select-text text-xs"
                  />
                  <button {...submitButtonProps} type="submit" className="hidden" />
                </form>
              )}
              renderItem={props => (
                <FileTreeNodeRenderer
                  {...props}
                  onContextMenu={handleContextMenuEvent}
                  onDoubleClick={handleItemDoubleClick}
                  onUnlock={handleUnlock}
                  onLock={handleLock}
                  canNativeDrag={String(props.item.index) !== String(rootNodeId)}
                  onNativeDragStart={(e, item) => {
                    const d = item.data;
                    if (d) {
                      e.dataTransfer.setData('application/x-file-path', d.path);
                      e.dataTransfer.setData('application/x-file-name', d.name);
                      e.dataTransfer.setData('application/x-file-type', d.type);
                      e.dataTransfer.effectAllowed = 'copyMove';
                    }
                  }}
                  onPointerDownNode={handlePointerDownNode}
                  onPointerUpNode={handlePointerUpNode}
                  onPointerEnterNode={handlePointerEnterNode}
                  onPointerLeaveNode={handlePointerLeaveNode}
                  isPointerDragOver={(pointerHoverItemId ?? externalHoverFolderId) === String(props.item.index)}
                  isPointerDragInFolder={isInPointerHoverFolder(String(props.item.index))}
                  isCutPending={cutPendingIdSet.has(String(props.item.index))}
                  isModifiedBranch={modifiedBranchIdSet.has(String(props.item.index))}
                />
              )}
            >
              <Tree
                ref={treeRef}
                treeId={treeId}
                rootItem="root"
                treeLabel="File Explorer"
              />
            </ControlledTreeEnvironment>
          </div>

          {contextMenu && (
            <ContextMenu
              x={contextMenu.x}
              y={contextMenu.y}
              actions={getContextMenuActions()}
              onClose={closeContextMenu}
            />
          )}
        </>
      )}

      <AlertDialog
        open={!!pendingDelete}
        title={
          pendingDelete && pendingDelete.ids.length > 1
            ? t('workspace.fileExplorer.recycleBinMultiTitle', { count: pendingDelete.ids.length })
            : t('workspace.fileExplorer.recycleBinTitle', { name: pendingDelete?.name ?? '' })
        }
        description={
          pendingDelete
            ? (pendingDelete.ids.length > 1
              ? t('workspace.fileExplorer.recycleBinMultiDescription')
              : t('workspace.fileExplorer.recycleBinDescription'))
            : undefined
        }
        confirmLabel={t('workspace.fileExplorer.moveToRecycleBin')}
        cancelLabel={t('workspace.fileExplorer.deleteCancel')}
        onConfirm={async () => {
          if (pendingDelete) {
            for (const id of pendingDelete.ids) {
              await handleDelete(id);
            }
          }
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
        isDestructive={false}
      />

      <AlertDialog
        open={!!noticeDialog}
        title={noticeDialog?.title ?? ''}
        description={noticeDialog?.description}
        confirmLabel={t('workspace.fileExplorer.error.ok')}
        cancelLabel={t('workspace.fileExplorer.deleteCancel')}
        onConfirm={() => setNoticeDialog(null)}
        onCancel={() => setNoticeDialog(null)}
        isDestructive={false}
      />

      {isPointerDragging && pointerDragLabel && pointerDragPos && (
        <div
          className="fixed z-[80] pointer-events-none border border-orange-300 bg-orange-50/95 px-2.5 py-1 text-xs text-orange-900 shadow-[0_1px_0_rgba(0,0,0,0.08)]"
          style={{
            left: pointerDragPos.x + 14,
            top: pointerDragPos.y + 16,
          }}
        >
          {pointerDragLabel}
        </div>
      )}
    </div>
  </Spin>;
});
