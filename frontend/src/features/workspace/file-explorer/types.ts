import type { TreeItem, TreeItemIndex } from 'react-complex-tree';

export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'folder';
  children?: FileNode[];
  path?: string;
  modified?: boolean;
  isNew?: boolean;
  isLocked?: boolean;
  canLock?: boolean;
}

export interface FileItemData {
  name: string;
  type: 'file' | 'folder';
  path: string;
  isLocked: boolean;
  canLock: boolean;
  isNew?: boolean;
  modified?: boolean;
}

export type FileTreeItem = TreeItem<FileItemData>;
export type FileTreeItems = Record<TreeItemIndex, FileTreeItem>;

export interface FileExplorerProps {
  projectId?: string;
  rootPath?: string;
  enableLocking?: boolean;
  storageKeyPrefix?: string;
  onFileSelect?: (filePath: string) => void;
  onFileOpen?: (filePath: string, fileName: string) => void;
  onFileTreeChange?: (tree: FileNode[]) => void;
  onAddToChat?: (filePath: string, fileName: string, type: 'file' | 'folder') => void;
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  nodeId: string | null;
}

/** Convert nested FileNode[] to flat record for react-complex-tree */
export function flattenFileTree(nodes: FileNode[]): FileTreeItems {
  const items: FileTreeItems = {
    root: {
      index: 'root',
      data: { name: 'root', type: 'folder', path: '', isLocked: false, canLock: false },
      children: nodes.map(n => n.id),
      isFolder: true,
      canMove: false,
      canRename: false,
    },
  };

  const traverse = (nodeList: FileNode[]) => {
    for (const node of nodeList) {
      items[node.id] = {
        index: node.id,
        data: {
          name: node.name,
          type: node.type,
          path: node.path || '',
          isLocked: node.isLocked ?? false,
          canLock: node.canLock ?? false,
          isNew: node.isNew,
          modified: node.modified,
        },
        children: node.children?.map(c => c.id) ?? [],
        isFolder: node.type === 'folder',
        canMove: !(node.isLocked ?? false),
        canRename: !(node.isLocked ?? false),
      };
      if (node.children) {
        traverse(node.children);
      }
    }
  };
  traverse(nodes);
  return items;
}















