'use client';

import React, { useState, useRef, useCallback } from 'react';
import { FolderOpen, Search, X, GitBranch, Plus, MessageSquare } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { ApiPanel } from '../api-panel';

export type ActivityId = 'project' | 'explore' | 'explorer' | 'environment' | 'search' | 'skills' | 'workflow' | 'api' | 'remote' | 'team';

interface ActivityBarProps {
  activeActivity: ActivityId | null;
  onActivityChange: (activity: ActivityId | null) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  fileExplorerSlot?: React.ReactNode;
  searchResultsSlot?: React.ReactNode;
  workflowSlot?: React.ReactNode;
  workflowActions?: React.ReactNode;
  workflowTitleOverride?: React.ReactNode;
  projectActions?: React.ReactNode;
  projectSwitcher?: React.ReactNode;
  onSearchQueryChange?: (query: string) => void;
  width?: number;
}


export function ActivityBar({ activeActivity, onActivityChange, collapsed = false, onToggleCollapse, fileExplorerSlot, searchResultsSlot, workflowSlot, workflowActions, workflowTitleOverride, recentSlot, projectActions, projectSwitcher, onSearchQueryChange, width = 260 }: ActivityBarProps) {
  const { t } = useTranslation();
  const [fileExplorerOpen, setFileExplorerOpen] = useState(true);
  const [workflowOpen, setWorkflowOpen] = useState(true);
  const [recentOpen, setRecentOpen] = useState(true);
  const [searchActive, setSearchActive] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  const openSearch = useCallback(() => {
    setSearchActive(true);
    setSearchQuery('');
    onSearchQueryChange?.('');
    setTimeout(() => searchInputRef.current?.focus(), 0);
  }, [onSearchQueryChange]);

  const closeSearch = useCallback(() => {
    setSearchActive(false);
    setSearchQuery('');
    onSearchQueryChange?.('');
  }, [onSearchQueryChange]);

  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    onSearchQueryChange?.(value);
  }, [onSearchQueryChange]);

  const isExploreActive = activeActivity === 'explore';

  const handleFileExplore = () => {
    if (collapsed) {
      onToggleCollapse?.();
      return;
    }
    setFileExplorerOpen(o => !o)
  }

  const handleWorkflowOpen = () => {
    if (collapsed) {
      onToggleCollapse?.();
      return;
    }
    setWorkflowOpen(o => !o)
  }

  const handleRecentOpen = () => {
    if (collapsed) {
      onToggleCollapse?.();
      return;
    }
    setRecentOpen(o => !o)
  }

  return (
    <div
      className="h-full bg-[#F2F1EE] flex flex-col pt-3 pb-0 border-r border-divider overflow-hidden"
      style={{ width: collapsed ? 52 : width, transition: 'width 200ms ease' }}
    >
      {/* Use It */}
      <div className="mb-2 px-2">
        <button
          onClick={() => onActivityChange('explore')}
          className={clsx(
            "h-[40px] flex items-center gap-2.5 px-2.5 rounded-xl border whitespace-nowrap overflow-hidden transition-[width] duration-200 ease-in-out",
            collapsed ? "w-[40px]" : "w-full",
            isExploreActive
              ? "bg-white border-black/[0.06] text-black/85 shadow-[0_1px_3px_rgba(0,0,0,0.06)]"
              : "bg-white/80 border-black/[0.04] text-black/65 hover:bg-white hover:border-black/[0.06] hover:shadow-[0_1px_3px_rgba(0,0,0,0.06)]"
          )}
          title={t('workspace.explore.title')}
        >
          <Plus className="w-[17px] h-[17px] stroke-[2.5px] shrink-0" />
          <span
            className="text-[13px] font-semibold"
            style={{ opacity: collapsed ? 0 : 1, transition: 'opacity 150ms ease' }}
          >{t('workspace.explore.title')}</span>
        </button>
      </div>

      {/* Main content: Project + File tree + nav items packed together — scrollable */}
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden flex flex-col">
        {/* Project row: click label to toggle file tree, search icon, action buttons + project switcher */}
        <div className="flex items-center h-[38px] flex-shrink-0 px-2">
          <div className="flex items-center w-full h-full rounded-lg relative whitespace-nowrap overflow-hidden">
            {searchActive ? (
              <div className="flex items-center w-full h-full gap-1.5 px-2">
                <Search className="w-[15px] h-[15px] shrink-0 text-black/35" />
                <input
                  ref={searchInputRef}
                  value={searchQuery}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Escape') closeSearch(); }}
                  className="flex-1 min-w-0 bg-transparent text-[12px] text-black/80 placeholder:text-black/30 outline-none"
                  placeholder={t('workspace.search.placeholder', 'Search files...')}
                />
                <button
                  onClick={closeSearch}
                  className="p-0.5 text-black/30 hover:text-black/60 rounded transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <div className="group/project flex items-center w-full h-full rounded-lg text-black/70 hover:bg-black/[0.04] hover:text-black/85 transition-colors">
                <button
                  onClick={handleFileExplore}
                  className="flex-1 min-w-0 h-full flex items-center gap-2.5 px-2.5"
                  title={t('workspace.project.title')}
                >
                  <FolderOpen className="w-[18px] h-[18px] shrink-0" />
                  <span
                    className="text-[12px] font-medium truncate"
                    style={{ opacity: collapsed ? 0 : 1, transition: 'opacity 150ms ease' }}
                  >{t('workspace.project.title')}</span>
                </button>
                {!collapsed && (
                  <div className="flex items-center gap-0 flex-shrink-0 mr-1">
                    <button
                      onClick={openSearch}
                      className="p-1 text-black/30 hover:text-black/60 hover:bg-black/5 rounded transition-colors"
                      title={t('workspace.search.title')}
                    >
                      <Search className="w-3 h-3" />
                    </button>
                    {projectActions}
                    {projectSwitcher}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        {/* File Explorer tree / Search results — keeps natural height, never squeezed */}
        {!collapsed && fileExplorerOpen && (
          <div className="flex-shrink-0 min-w-0 overflow-x-hidden">
            {searchActive && searchQuery.trim() ? searchResultsSlot : fileExplorerSlot}
          </div>
        )}
      </div>
    </div>
  );
}
