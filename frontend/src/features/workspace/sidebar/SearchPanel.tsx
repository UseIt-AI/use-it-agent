'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { Search, X, FileText, Folder } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import type { FileNode } from '../file-explorer/types';

function searchFilesRecursive(nodes: FileNode[], query: string): FileNode[] {
  if (!query.trim()) return [];
  const results: FileNode[] = [];
  const lowerQuery = query.toLowerCase();
  const traverse = (nodeList: FileNode[]) => {
    for (const node of nodeList) {
      if (node.name.toLowerCase().includes(lowerQuery)) results.push(node);
      if (node.children) traverse(node.children);
    }
  };
  traverse(nodes);
  return results;
}

function getRelativePath(node: FileNode): string {
  if (node.path) {
    const parts = node.path.split(/[/\\]/);
    if (parts.length > 1) return parts.slice(-2).join('/');
    return node.name;
  }
  return node.name;
}

interface SearchResultsListProps {
  fileTree: FileNode[];
  query: string;
  onFileOpen?: (filePath: string, fileName: string) => void;
}

export function SearchResultsList({ fileTree, query, onFileOpen }: SearchResultsListProps) {
  const { t } = useTranslation();
  const results = useMemo(() => searchFilesRecursive(fileTree, query), [fileTree, query]);

  if (!query.trim()) return null;

  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center py-6 text-black/30">
        <Search className="w-5 h-5 mb-1.5 opacity-50" />
        <span className="text-[11px]">{t('workspace.search.noResults')}</span>
      </div>
    );
  }

  return (
    <div className="py-0.5">
      <div className="px-4 py-1 text-[9px] font-bold text-black/30 uppercase tracking-wider">
        {results.length} {results.length === 1 ? 'result' : 'results'}
      </div>
      {results.map((node) => (
        <button
          key={node.id}
          onClick={() => {
            if (node.type === 'file' && node.path && onFileOpen) onFileOpen(node.path, node.name);
          }}
          className="w-full px-4 py-1 flex items-center gap-2 text-left text-[11px] text-black/65 hover:bg-black/[0.04] hover:text-black/85 transition-colors"
        >
          {node.type === 'file' ? (
            <FileText className="w-3 h-3 flex-shrink-0 text-black/30" />
          ) : (
            <Folder className="w-3 h-3 flex-shrink-0 text-black/30" />
          )}
          <div className="flex-1 min-w-0">
            <div className="truncate font-medium text-[11px]">{node.name}</div>
            <div className="text-[9px] text-black/30 truncate">{getRelativePath(node)}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

interface SearchPanelProps {
  fileTree: FileNode[];
  onFileSelect?: (filePath: string) => void;
  onFileOpen?: (filePath: string, fileName: string) => void;
}

export function SearchPanel({ fileTree, onFileSelect, onFileOpen }: SearchPanelProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  // 递归搜索文件
  const searchFiles = useCallback((nodes: FileNode[], query: string): FileNode[] => {
    if (!query.trim()) return [];

    const results: FileNode[] = [];
    const lowerQuery = query.toLowerCase();

    const traverse = (nodeList: FileNode[]) => {
      for (const node of nodeList) {
        // 检查文件名是否匹配
        if (node.name.toLowerCase().includes(lowerQuery)) {
          results.push(node);
        }
        // 递归搜索子节点
        if (node.children) {
          traverse(node.children);
        }
      }
    };

    traverse(nodes);
    return results;
  }, []);

  const searchResults = useMemo(() => {
    return searchFiles(fileTree, searchQuery);
  }, [fileTree, searchQuery, searchFiles]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, searchResults.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && searchResults[selectedIndex]) {
        e.preventDefault();
        const node = searchResults[selectedIndex];
        if (node.type === 'file' && node.path && onFileOpen) {
          onFileOpen(node.path, node.name);
        } else if (node.path && onFileSelect) {
          onFileSelect(node.path);
        }
      } else if (e.key === 'Escape') {
        setSearchQuery('');
        setSelectedIndex(0);
      }
    },
    [searchResults, selectedIndex, onFileOpen, onFileSelect]
  );

  const handleResultClick = useCallback(
    (node: FileNode) => {
      if (node.type === 'file' && node.path && onFileOpen) {
        onFileOpen(node.path, node.name);
      } else if (node.path && onFileSelect) {
        onFileSelect(node.path);
      }
    },
    [onFileOpen, onFileSelect]
  );

  // 获取文件路径（用于显示）
  const getFilePath = useCallback((node: FileNode): string => {
    // 从节点路径中提取相对路径
    if (node.path) {
      // 假设路径是绝对路径，提取文件名和父目录
      const parts = node.path.split(/[/\\]/);
      if (parts.length > 1) {
        return parts.slice(-2).join('/');
      }
      return node.name;
    }
    return node.name;
  }, []);

  return (
    <div className="h-full w-full flex flex-col bg-canvas text-black/90">
      {/* 搜索输入框 */}
      <div className="px-3 py-2 border-b border-divider">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-black/40" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder={t('workspace.search.placeholder')}
            className="w-full pl-8 pr-8 py-1.5 bg-white border border-divider text-sm text-black/90 placeholder-black/40 rounded focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20"
            autoFocus
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('');
                setSelectedIndex(0);
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-black/40 hover:text-black/70 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* 搜索结果 */}
      <div className="flex-1 overflow-y-auto">
        {searchQuery.trim() ? (
          searchResults.length > 0 ? (
            <div className="py-1">
              <div className="px-3 py-1.5 text-xs text-black/50 uppercase tracking-wider">
                {t('workspace.search.results')} ({searchResults.length})
              </div>
              {searchResults.map((node, index) => (
                <button
                  key={node.id}
                  onClick={() => handleResultClick(node)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={clsx(
                    'w-full px-3 py-1.5 flex items-center gap-2 text-left text-sm transition-colors',
                    index === selectedIndex
                      ? 'bg-orange-500/10 text-black/90'
                      : 'text-black/70 hover:bg-black/5'
                  )}
                >
                  {node.type === 'file' ? (
                    <FileText className="w-4 h-4 flex-shrink-0 text-black/40" />
                  ) : (
                    <Folder className="w-4 h-4 flex-shrink-0 text-black/40" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="truncate font-medium">{node.name}</div>
                    {node.path && (
                      <div className="text-xs text-black/40 truncate">{getFilePath(node)}</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-black/40">
              <Search className="w-8 h-8 mb-2 opacity-50" />
              <div className="text-sm">{t('workspace.search.noResults')}</div>
            </div>
          )
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-black/40">
            <Search className="w-8 h-8 mb-2 opacity-50" />
            <div className="text-sm">{t('workspace.search.hint')}</div>
          </div>
        )}
      </div>
    </div>
  );
}

