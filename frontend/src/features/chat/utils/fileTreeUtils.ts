import type { FileNode } from '@/features/workspace/file-explorer/types';

export interface FlatFileItem {
  path: string;
  name: string;
  type: 'file' | 'folder';
  relativePath: string;
  depth: number;
  childCount: number;
}

export function flattenAllFiles(nodes: FileNode[], rootPrefix?: string): FlatFileItem[] {
  const result: FlatFileItem[] = [];
  const traverse = (nodeList: FileNode[], depth: number) => {
    for (const node of nodeList) {
      const absPath = node.path || node.id;
      let relativePath = node.name;
      if (rootPrefix && absPath.startsWith(rootPrefix)) {
        relativePath = absPath.slice(rootPrefix.length).replace(/^[/\\]/, '');
      }
      if (depth > 0) {
        result.push({
          path: absPath,
          name: node.name,
          type: node.type,
          relativePath,
          depth: depth - 1,
          childCount: node.children?.length ?? 0,
        });
      }
      if (node.children) {
        traverse(node.children, depth + 1);
      }
    }
  };
  traverse(nodes, 0);
  return result;
}

export function getVisibleTreeItems(
  nodes: FileNode[],
  rootPrefix: string,
  expandedFolders: Set<string>
): FlatFileItem[] {
  const result: FlatFileItem[] = [];
  const traverse = (nodeList: FileNode[], depth: number) => {
    for (const node of nodeList) {
      const absPath = node.path || node.id;
      let relativePath = node.name;
      if (rootPrefix && absPath.startsWith(rootPrefix)) {
        relativePath = absPath.slice(rootPrefix.length).replace(/^[/\\]/, '');
      }
      if (depth > 0) {
        result.push({
          path: absPath,
          name: node.name,
          type: node.type,
          relativePath,
          depth: depth - 1,
          childCount: node.children?.length ?? 0,
        });
      }
      if (node.children && (depth === 0 || expandedFolders.has(absPath))) {
        traverse(node.children, depth + 1);
      }
    }
  };
  traverse(nodes, 0);
  return result;
}
