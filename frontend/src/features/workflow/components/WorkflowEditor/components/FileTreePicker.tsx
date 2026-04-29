import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Check, Minus } from 'lucide-react';
import { getFileIcon } from '@/features/workspace/file-explorer/utils/fileIcon';

export interface TreeNode {
  name: string;
  type: 'file' | 'folder';
  path: string;
  children?: TreeNode[];
  size?: number;
}

interface FileTreePickerProps {
  nodes: TreeNode[];
  selected: Set<string>;
  onToggle: (path: string, node: TreeNode) => void;
  mode: 'flat' | 'tree';
}

function isOfficeTempFile(name: string): boolean {
  if (name.startsWith('~$')) return true;
  if (name.startsWith('~') && name.endsWith('.tmp')) return true;
  if (name.startsWith('.~lock.')) return true;
  return false;
}

function filterTree(nodes: TreeNode[]): TreeNode[] {
  return nodes
    .filter(node => !isOfficeTempFile(node.name))
    .map(node => {
      if (node.type === 'folder' && node.children) {
        const filtered = filterTree(node.children);
        return { ...node, children: filtered };
      }
      return node;
    })
    .filter(node => node.type === 'file' || (node.children && node.children.length > 0));
}

function getAllFilePaths(node: TreeNode): string[] {
  if (node.type === 'file') return isOfficeTempFile(node.name) ? [] : [node.path];
  if (!node.children) return [];
  return node.children.flatMap(getAllFilePaths);
}

function getFolderCheckState(node: TreeNode, selected: Set<string>): 'none' | 'some' | 'all' {
  const allPaths = getAllFilePaths(node);
  if (allPaths.length === 0) return 'none';
  const count = allPaths.filter(p => selected.has(p)).length;
  if (count === 0) return 'none';
  if (count === allPaths.length) return 'all';
  return 'some';
}

function TreeItem({
  node,
  selected,
  onToggle,
  depth,
}: {
  node: TreeNode;
  selected: Set<string>;
  onToggle: (path: string, node: TreeNode) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < 1);
  const isFolder = node.type === 'folder';
  const isChecked = isFolder
    ? getFolderCheckState(node, selected) === 'all'
    : selected.has(node.path);
  const isPartial = isFolder && getFolderCheckState(node, selected) === 'some';

  return (
    <div>
      <div
        className="flex items-center gap-1 py-0.5 px-1 hover:bg-black/5 rounded cursor-pointer select-none"
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
        onClick={() => {
          if (isFolder) {
            onToggle(node.path, node);
          } else {
            onToggle(node.path, node);
          }
        }}
      >
        {isFolder ? (
          <button
            type="button"
            className="w-4 h-4 flex items-center justify-center flex-shrink-0 text-black/40"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
          >
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        ) : (
          <span className="w-4" />
        )}

        <div
          className={`w-3.5 h-3.5 flex items-center justify-center flex-shrink-0 rounded border transition-colors ${
            isChecked
              ? 'bg-gray-900 border-gray-900 text-white'
              : isPartial
                ? 'bg-gray-400 border-gray-400 text-white'
                : 'border-gray-300 bg-white'
          }`}
        >
          {isChecked && <Check className="w-2.5 h-2.5" />}
          {isPartial && !isChecked && <Minus className="w-2.5 h-2.5" />}
        </div>

        {getFileIcon(node.name, isFolder, 14)}

        <span className="text-xs text-gray-700 truncate">{node.name}</span>
      </div>

      {isFolder && expanded && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              selected={selected}
              onToggle={onToggle}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FlatItem({
  node,
  selected,
  onToggle,
}: {
  node: TreeNode;
  selected: Set<string>;
  onToggle: (path: string, node: TreeNode) => void;
}) {
  const checkState = getFolderCheckState(node, selected);
  const isChecked = checkState === 'all';
  const isPartial = checkState === 'some';
  const fileCount = getAllFilePaths(node).length;

  return (
    <div
      className="flex items-center gap-2 py-1.5 px-2 hover:bg-black/5 rounded cursor-pointer select-none"
      onClick={() => onToggle(node.path, node)}
    >
      <div
        className={`w-4 h-4 flex items-center justify-center flex-shrink-0 rounded border transition-colors ${
          isChecked
            ? 'bg-gray-900 border-gray-900 text-white'
            : isPartial
              ? 'bg-gray-400 border-gray-400 text-white'
              : 'border-gray-300 bg-white'
        }`}
      >
        {isChecked && <Check className="w-3 h-3" />}
        {isPartial && !isChecked && <Minus className="w-3 h-3" />}
      </div>
      {getFileIcon(node.name, true, 16)}
      <span className="text-sm text-gray-700 flex-1 truncate">{node.name}</span>
      <span className="text-[10px] text-gray-400 flex-shrink-0">{fileCount} file{fileCount !== 1 ? 's' : ''}</span>
    </div>
  );
}

export function FileTreePicker({ nodes, selected, onToggle, mode }: FileTreePickerProps) {
  const filtered = filterTree(nodes);

  if (filtered.length === 0) {
    return (
      <div className="py-3 text-center text-xs text-gray-400 italic">
        No files found
      </div>
    );
  }

  if (mode === 'flat') {
    const folders = filtered.filter(n => n.type === 'folder');
    if (folders.length === 0) {
      return (
        <div className="py-3 text-center text-xs text-gray-400 italic">
          No skill folders found
        </div>
      );
    }
    return (
      <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-50">
        {folders.map((node) => (
          <FlatItem key={node.path} node={node} selected={selected} onToggle={onToggle} />
        ))}
      </div>
    );
  }

  return (
    <div className="py-1">
      {filtered.map((node) => (
        <TreeItem key={node.path} node={node} selected={selected} onToggle={onToggle} depth={0} />
      ))}
    </div>
  );
}

export { getAllFilePaths };
export default FileTreePicker;
