import React, { useState } from 'react';
import { ChevronRight, Lock, Unlock } from 'lucide-react';
import type { TreeItem, TreeItemRenderContext } from 'react-complex-tree';
import type { FileItemData } from '../types';
import clsx from 'clsx';
import { UnlockConfirmationDialog } from './UnlockConfirmationDialog';
import { getFileIcon } from '../utils/fileIcon';

interface FileTreeNodeRendererProps {
  item: TreeItem<FileItemData>;
  title: React.ReactNode;
  arrow: React.ReactNode;
  depth: number;
  context: TreeItemRenderContext;
  children: React.ReactNode;
  onContextMenu?: (e: React.MouseEvent, nodeId: string) => void;
  onDoubleClick?: (item: TreeItem<FileItemData>) => void;
  onUnlock?: (nodeId: string) => void;
  onLock?: (nodeId: string) => void;
  canNativeDrag?: boolean;
  onNativeDragStart?: (e: React.DragEvent, item: TreeItem<FileItemData>) => void;
  onNativeDragOver?: (e: React.DragEvent, item: TreeItem<FileItemData>) => void;
  onNativeDrop?: (e: React.DragEvent, item: TreeItem<FileItemData>) => void;
  onPointerDownNode?: (e: React.PointerEvent, item: TreeItem<FileItemData>) => void;
  onPointerUpNode?: (e: React.PointerEvent, item: TreeItem<FileItemData>) => void;
  onPointerEnterNode?: (e: React.PointerEvent, item: TreeItem<FileItemData>) => void;
  onPointerLeaveNode?: (e: React.PointerEvent, item: TreeItem<FileItemData>) => void;
  isPointerDragOver?: boolean;
  isPointerDragInFolder?: boolean;
  isCutPending?: boolean;
  isModifiedBranch?: boolean;
}

export function FileTreeNodeRenderer({
  item,
  title,
  depth,
  context,
  children,
  onContextMenu,
  onDoubleClick,
  onUnlock,
  onLock,
  canNativeDrag,
  onNativeDragStart,
  onNativeDragOver,
  onNativeDrop,
  onPointerDownNode,
  onPointerUpNode,
  onPointerEnterNode,
  onPointerLeaveNode,
  isPointerDragOver,
  isPointerDragInFolder,
  isCutPending,
  isModifiedBranch,
}: FileTreeNodeRendererProps) {
  const isFolder = item.isFolder ?? false;
  const isSelected = context.isSelected;
  const isRenaming = context.isRenaming;
  const isLocked = item.data.isLocked;
  const canLock = item.data.canLock;
  const isDraggingOver = context.isDraggingOver;
  const [showUnlockDialog, setShowUnlockDialog] = useState(false);

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onContextMenu?.(e, item.index as string);
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDoubleClick?.(item);
  };

  const handleLockClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isLocked) {
      setShowUnlockDialog(true);
    } else if (canLock && onLock) {
      onLock(item.index as string);
    }
  };

  const itemProps = context.itemContainerWithoutChildrenProps;
  const interactiveProps = context.interactiveElementProps;

  const nodeClasses = clsx(
    'flex items-center w-full cursor-pointer select-none text-[12px] font-sans group outline-none transition-colors',
    'border-none bg-transparent text-left',
    'text-black/75 hover:bg-black/[0.04]',
    isSelected && '!bg-black/[0.10] !text-black font-medium',
    isPointerDragInFolder && 'bg-orange-100/20',
    isPointerDragOver && '!bg-black/[0.16]',
    isDraggingOver && 'bg-orange-50 ring-1 ring-orange-300',
    isCutPending && 'bg-black/[0.06] text-black/45',
    item.data.isNew && 'opacity-80',
    isRenaming && 'cursor-text',
    isLocked && 'opacity-90'
  );

  const childrenContainerProps = context.itemContainerWithChildrenProps;
  const mergedInteractive = isRenaming ? {} : interactiveProps;
  const mergedInteractiveAny = mergedInteractive as any;
  const isFolderDropGroupHighlighted = Boolean(isPointerDragOver && isFolder);

  return (
    <li
      {...childrenContainerProps}
      className={clsx(
        'list-none relative',
        childrenContainerProps.className,
        isFolderDropGroupHighlighted && 'bg-orange-100/25'
      )}
    >
      <div
        {...itemProps}
        {...mergedInteractive}
        role="treeitem"
        tabIndex={0}
        draggable={!isRenaming && (canNativeDrag ?? !!mergedInteractiveAny?.draggable)}
        onDragStart={e => {
          onNativeDragStart?.(e, item);
          mergedInteractiveAny?.onDragStart?.(e);
        }}
        onDragOver={e => {
          onNativeDragOver?.(e, item);
          mergedInteractiveAny?.onDragOver?.(e);
        }}
        onDrop={e => {
          onNativeDrop?.(e, item);
          mergedInteractiveAny?.onDrop?.(e);
        }}
        onPointerDown={e => onPointerDownNode?.(e, item)}
        onPointerUp={e => onPointerUpNode?.(e, item)}
        onPointerEnter={e => onPointerEnterNode?.(e, item)}
        onPointerLeave={e => onPointerLeaveNode?.(e, item)}
        onContextMenu={handleContextMenu}
        onDoubleClick={isRenaming ? undefined : handleDoubleClick}
        className={clsx(
          nodeClasses,
          itemProps.className,
          (mergedInteractive as any).className,
        )}
        style={{
          ...(itemProps.style || {}),
          ...((mergedInteractive as any).style || {}),
          paddingLeft: `${depth * 10 + 18}px`,
        }}
      >
        <div className="flex items-center w-full py-1 min-h-[22px]">
          <span
            className="w-4 h-4 flex items-center justify-center flex-shrink-0 transition-transform duration-200"
            onClick={e => {
              e.stopPropagation();
              if (isFolder) {
                if (context.isExpanded) {
                  context.collapseItem();
                } else {
                  context.expandItem();
                }
              }
            }}
          >
            {isFolder ? (
              <ChevronRight
                className={clsx(
                  'w-3.5 h-3.5 text-black/35 group-hover:text-black/50 transition-all duration-150',
                  context.isExpanded && 'rotate-90',
                  isSelected && 'text-black/70'
                )}
              />
            ) : (
              getFileIcon(item.data.name, false)
            )}
          </span>

          {isRenaming ? (
            <span className="ml-1.5 flex-1 min-w-0">{title}</span>
          ) : (
            <>
              <span
                className={clsx(
                  'truncate leading-tight ml-1.5 flex-1',
                  isFolder && 'font-medium text-black/85',
                  !isFolder && 'text-black/70',
                  isSelected && 'text-black font-medium',
                  isCutPending && '!text-black/45',
                  isModifiedBranch && '!text-blue-600 font-medium'
                )}
                title={item.data.path || item.data.name}
              >
                {item.data.name}
              </span>
              {canLock && (
                <span
                  role="button"
                  tabIndex={-1}
                  onClick={handleLockClick}
                  onMouseDown={e => e.stopPropagation()}
                  className={clsx(
                    'ml-1.5 mr-[14px] w-4 h-4 flex items-center justify-center flex-shrink-0 transition-opacity cursor-pointer group-hover:opacity-100',
                    isLocked
                      ? 'opacity-60 hover:opacity-100'
                      : 'opacity-40 hover:opacity-80'
                  )}
                  title={isLocked ? '点击解锁（将显示警告）' : '点击上锁'}
                >
                  {isLocked ? (
                    <Lock className="w-3 h-3 text-orange-600" strokeWidth={2} />
                  ) : (
                    <Unlock className="w-3 h-3 text-gray-400 hover:text-orange-600" strokeWidth={2} />
                  )}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {children}

      <UnlockConfirmationDialog
        open={showUnlockDialog}
        fileName={item.data.name}
        isFolder={isFolder}
        onConfirm={() => {
          onUnlock?.(item.index as string);
          setShowUnlockDialog(false);
        }}
        onCancel={() => setShowUnlockDialog(false)}
      />
    </li>
  );
}
