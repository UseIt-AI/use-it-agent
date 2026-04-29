'use client';

import React, { useImperativeHandle, forwardRef, useRef, useCallback } from 'react';
import FileExplorer from './file-explorer/FileExplorer';

export interface SkillsExplorerRef {
  expandFolder: (folderName: string) => void;
}

export const SkillsExplorer = forwardRef<SkillsExplorerRef, {
  rootPath?: string | null;
  onFileOpen?: (filePath: string, fileName: string) => void;
  onFileTreeChange?: (tree: any[]) => void;
}>(function SkillsExplorer({
  rootPath,
  onFileOpen,
  onFileTreeChange,
}, ref) {
  const fileTreeRef = useRef<any[]>([]);
  const pendingExpandRef = useRef<string | null>(null);

  const findFolderById = useCallback((nodes: any[], folderName: string): string | null => {
    for (const node of nodes) {
      if (node.type === 'folder' && node.name === folderName) {
        return node.id;
      }
      if (node.children) {
        const found = findFolderById(node.children, folderName);
        if (found) return found;
      }
    }
    return null;
  }, []);

  const expandFolderByName = useCallback((folderName: string) => {
    const tree = fileTreeRef.current;
    if (!tree || tree.length === 0) return;

    const folderId = findFolderById(tree, folderName);
    if (folderId) {
      const expandFn = (window as any).__skillsExplorerExpand;
      if (expandFn) expandFn(folderId);
    }
  }, [findFolderById]);

  const handleFileTreeChange = useCallback((tree: any[]) => {
    fileTreeRef.current = tree;
    onFileTreeChange?.(tree);

    if (pendingExpandRef.current) {
      const folderName = pendingExpandRef.current;
      pendingExpandRef.current = null;
      setTimeout(() => expandFolderByName(folderName), 100);
    }
  }, [onFileTreeChange, expandFolderByName]);

  useImperativeHandle(ref, () => ({
    expandFolder: (folderName: string) => {
      if (fileTreeRef.current.length > 0) {
        expandFolderByName(folderName);
      } else {
        pendingExpandRef.current = folderName;
      }
    },
  }), [expandFolderByName]);

  if (!rootPath) {
    return (
      <div className="h-full w-full flex items-center justify-center text-xs text-black/40">
        Skills folder unavailable
      </div>
    );
  }

  return (
    <FileExplorer
      rootPath={rootPath}
      enableLocking={false}
      storageKeyPrefix="skillsExplorer"
      onFileOpen={onFileOpen}
      onFileTreeChange={handleFileTreeChange}
    />
  );
});
