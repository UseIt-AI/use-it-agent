/**
 * CUACard - CUA (Computer Use Agent) Step Card Component
 * 
 * Display structure:
 * - Title: "Thinking..." when running, action title when completed
 * - Screenshot icon: on the right side, click to expand screenshot
 * - Reasoning: collapsible section
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  AlertTriangle,
  X,
  Search,
  Globe,
  FileText,
  File,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Card } from '../handlers/types';
import { StatusIcon, type TaskStatus, type ActionType } from './StatusIcons';

// ==================== Duration Helper ====================

/**
 * 格式化运行时长
 * - < 1s: "0.3s"
 * - < 60s: "12.5s"
 * - >= 60s: "1m 23s"
 */
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

// ==================== Helper Functions ====================

/**
 * Extract coordinates from action supporting multiple formats:
 * - {x: 100, y: 200}
 * - {coordinate: [100, 200]}
 * - {position: [100, 200]}
 */
function getCoordinates(action: any): { x: number; y: number } | null {
  if (!action) return null;
  
  // Try direct x, y fields
  if (typeof action.x === 'number' && typeof action.y === 'number') {
    return { x: action.x, y: action.y };
  }
  
  // Try coordinate array
  if (Array.isArray(action.coordinate) && action.coordinate.length >= 2) {
    return { x: action.coordinate[0], y: action.coordinate[1] };
  }
  
  // Try position array (used by oai_operator_agent)
  if (Array.isArray(action.position) && action.position.length >= 2) {
    return { x: action.position[0], y: action.position[1] };
  }
  
  return null;
}

// ==================== CUA Card Component ====================

export interface CUACardProps {
  card: Card;
  screenshot?: string;
}

// ==================== Markdown Renderer ====================

const MarkdownContent = ({ content }: { content: string }) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{
      code({ node, inline, className, children, ...props }: any) {
        return (
          <code
            className={`${className} bg-slate-100 text-pink-600 px-1 py-0.5 rounded text-[11px] font-mono break-all`}
            {...props}
          >
            {children}
          </code>
        );
      },
      ul: ({ node, ...props }) => (
        <ul className="list-disc list-outside ml-4 my-1 space-y-1" {...props} />
      ),
      ol: ({ node, ...props }) => (
        <ol className="list-decimal list-outside ml-4 my-1 space-y-1" {...props} />
      ),
      li: ({ node, ...props }) => <li className="pl-1" {...props} />,
      p: ({ node, ...props }) => (
        <p className="leading-relaxed mb-1 last:mb-0" {...props} />
      ),
      a: ({ node, ...props }) => (
        <a
          className="underline underline-offset-2 text-blue-600 hover:text-blue-700"
          target="_blank"
          rel="noopener noreferrer"
          {...props}
        />
      ),
      blockquote: ({ node, ...props }) => (
        <blockquote
          className="border-l-2 pl-3 my-2 italic border-slate-300 text-slate-600"
          {...props}
        />
      ),
      hr: ({ node, ...props }) => (
        <hr className="my-3 border-t border-slate-200" {...props} />
      ),
    }}
  >
    {content}
  </ReactMarkdown>
);

export const CUACard: React.FC<CUACardProps> = ({ card, screenshot }) => {
  const [isExpanded, setIsExpanded] = useState(card.status === 'running');
  const [showScreenshot, setShowScreenshot] = useState(card.status === 'running');
  const [showError, setShowError] = useState(false);
  const [imgSize, setImgSize] = useState<{ width: number; height: number } | null>(null);
  const [expandedSearchItems, setExpandedSearchItems] = useState<Set<string>>(new Set());
  const [isSearchExpanded, setIsSearchExpanded] = useState(true);
  const [isReasoningFullyExpanded, setIsReasoningFullyExpanded] = useState(false);
  const [isReasoningOverflowing, setIsReasoningOverflowing] = useState(false);
  const reasoningRef = useRef<HTMLDivElement>(null);
  
  const isRunning = card.status === 'running';
  const hasError = !!card.error;
  const searchProgress = card.searchProgress;
  const searchResult = card.searchResult;
  const extractProgress = card.extractProgress;
  
  // Debug: 打印搜索结果信息
  React.useEffect(() => {
    if (searchResult) {
      console.log('[CUACard] searchResult:', {
        source: searchResult.source,
        hasAnswer: !!searchResult.answer,
        resultsCount: searchResult.results?.length || 0,
        metadata: searchResult.metadata,
      });
    }
  }, [searchResult]);

  // 计算最终时长（仅在完成后显示）
  const finalDuration = card.completedAt && card.startedAt 
    ? card.completedAt - card.startedAt 
    : null;

  // 监听 reasoning 变化，自动滚动到底部
  React.useEffect(() => {
    if (isExpanded && isRunning && reasoningRef.current) {
      const el = reasoningRef.current;
      // 只有当用户没有手动向上滚动查看历史时（或者接近底部时），才自动滚动
      // 这里简单处理：只要是 running 状态且有新内容，就强制滚到底部，这是最符合 terminal/log 体验的
      el.scrollTop = el.scrollHeight;
    }
  }, [card.reasoning, isExpanded, isRunning]);

  // 检测 reasoning 内容是否溢出
  React.useEffect(() => {
    if (isExpanded && reasoningRef.current && !isReasoningFullyExpanded) {
      const el = reasoningRef.current;
      // 检查内容高度是否超过容器高度
      const isOverflowing = el.scrollHeight > el.clientHeight;
      setIsReasoningOverflowing(isOverflowing);
    }
  }, [card.reasoning, isExpanded, isReasoningFullyExpanded]);

  // 监听状态变化：当状态变为 running 时自动展开，否则（如变为 completed）自动收起
  // 注意：我们只在状态变为非 running 时自动收起，但不强制在 running 时每次都重置为展开（虽然初始值已经是了）
  // 这样用户手动折叠后不会被莫名其妙打开，但在任务流转时会有自然的开合效果
  React.useEffect(() => {
    if (card.status === 'running') {
      setIsExpanded(true);
      setShowScreenshot(true);
    } else if (card.status === 'completed') {
      setIsExpanded(false);
      setShowScreenshot(false);
    }
  }, [card.status]);
  const isCompleted = card.status === 'completed';
  const isFailed = card.status === 'failed';
  const isCancelled = card.status === 'cancelled';
  
  // Has reasoning content
  const hasReasoning = !!card.reasoning;
  
  // Display title logic:
  // - If running and has action (cua_update received), show action title
  // - If running and no action yet, show "Thinking..."
  // - If completed/failed, show card.title (which contains action or final status)
  const displayTitle = isRunning 
    ? (card.action ? card.title : 'Thinking...') 
    : card.title;
  
  // Get action type for icon display
  // Handle both direct type and nested action object
  const actionType = (card.action?.type || (card.action as any)?.action?.type) as ActionType | undefined;

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const { naturalWidth, naturalHeight } = e.currentTarget;
    setImgSize({ width: naturalWidth, height: naturalHeight });
  };

  const toggleSearchItem = (key: string) => {
    setExpandedSearchItems((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const getSearchProgressMessage = () => {
    if (!searchProgress) return '';
    const queryCount = searchProgress.queries?.length || 0;
    switch (searchProgress.stage) {
      case 'queries_ready':
        return queryCount > 0
          ? `Split into ${queryCount} sub-queries`
          : 'Sub-queries prepared';
      case 'searching':
        return 'Searching...';
      case 'search_done':
        return searchProgress.current_query
          ? `Completed: ${searchProgress.current_query}`
          : '';
      case 'aggregating':
        return 'Aggregating results...';
      case 'completed':
        return '';
      default:
        return searchProgress.message || 'Search in progress';
    }
  };

  return (
    <div className={`
      group relative overflow-hidden transition-all duration-200
      animate-card-in
    `}>
      {/* Header */}
      <div
        className={`relative flex items-center gap-2 py-1 ${
          hasReasoning ? 'cursor-pointer hover:bg-slate-50/30' : ''
        } ${
          (isExpanded || isSearchExpanded) ? 'bg-gradient-to-r from-transparent via-slate-50 to-blue-50' : ''
        } transition-all`}
        onClick={() => hasReasoning && setIsExpanded(!isExpanded)}
      >
        {/* Status Icon - Single icon based on status and action type */}
        <div className="flex-shrink-0">
          <StatusIcon 
            status={card.status as TaskStatus} 
            actionType={actionType}
            size="sm"
            className={isRunning ? "text-amber-500" : "text-slate-500"}
          />
        </div>

        {/* Title */}
        <div className="flex-1 min-w-0">
          <span
            className={`text-xs font-medium font-mono break-words ${
              isRunning ? 'text-slate-600 animate-pulse' : 
              isFailed ? 'text-amber-700' :
              isCancelled ? 'text-slate-500' :
              'text-slate-700'
            }`}
          >
            {displayTitle}
          </span>
        </div>

        {/* Duration badge - Only show after completion */}
        {!isRunning && finalDuration !== null && finalDuration > 0 && (
          <span className="flex-shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
            {formatDuration(finalDuration)}
          </span>
        )}

        {/* Right side toolbar - Floating and only visible on hover */}
        <div className="absolute right-0 top-0 bottom-0 flex items-center gap-1.5 pl-8 opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-gradient-to-l from-slate-50 via-slate-50 to-transparent">
          {/* Error indicator - Small warning icon, click to view details */}
          {hasError && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowError(!showError);
              }}
              className={`p-1 rounded transition-colors ${
                showError 
                  ? 'bg-amber-100 text-amber-600' 
                  : 'hover:bg-amber-50 text-amber-500 hover:text-amber-600'
              }`}
              title="View error details"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Screenshot icon */}
          {screenshot && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowScreenshot(!showScreenshot);
              }}
              className={`p-1 rounded transition-colors ${
                showScreenshot 
                  ? 'bg-slate-200 text-slate-700' 
                  : 'hover:bg-slate-100 text-slate-400 hover:text-slate-600'
              }`}
              title={showScreenshot ? 'Hide screenshot' : 'View screenshot'}
            >
              <ImageIcon className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Search toggle icon */}
          {(searchProgress || searchResult) && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsSearchExpanded((prev) => !prev);
              }}
              className={`p-1 rounded transition-colors ${
                isSearchExpanded
                  ? 'bg-slate-200 text-slate-700'
                  : 'hover:bg-slate-100 text-slate-400 hover:text-slate-600'
              }`}
              title={isSearchExpanded ? 'Hide search' : 'View search'}
            >
              {isSearchExpanded ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </button>
          )}

          {/* Expand/collapse icon */}
          {hasReasoning && (
            <span className="text-slate-400 p-1">
              {isExpanded ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </span>
          )}
        </div>
      </div>

      {/* Screenshot area (click icon to expand) */}
      {showScreenshot && screenshot && (
        <div className="px-2.5 py-2 animate-content-in">
          <div className="relative rounded border border-slate-200 shadow-sm overflow-hidden bg-slate-50">
            <div className="absolute top-2 right-2 z-10 bg-black/50 text-white text-[10px] px-2 py-0.5 rounded backdrop-blur-sm font-mono">
              SCREENSHOT
            </div>
            <img
              src={`data:image/png;base64,${screenshot}`}
              alt={`Step ${card.step} screenshot`}
              onLoad={handleImageLoad}
              className="w-full object-contain"
            />

            {/* Click position marker - simple red circle */}
            {actionType === 'click' && imgSize && (() => {
              const coords = getCoordinates(card.action);
              if (!coords || (coords.x === 0 && coords.y === 0)) return null;
              return (
                <div
                  className="absolute w-5 h-5 border-2 border-red-500 rounded-full transform -translate-x-1/2 -translate-y-1/2 z-10 pointer-events-none"
                  style={{
                    left: `${(coords.x / imgSize.width) * 100}%`,
                    top: `${(coords.y / imgSize.height) * 100}%`,
                  }}
                />
              );
            })()}
          </div>
        </div>
      )}

      {/* Search progress / results */}
      {(searchProgress || searchResult) && isSearchExpanded && (
        <div className="px-2.5 py-2 space-y-3 animate-content-in">
          {searchProgress && (
            <div className="flex flex-col gap-1">
              {getSearchProgressMessage() && (
                <div className="text-[13px] text-slate-600 mb-1">
                  {getSearchProgressMessage()}
                </div>
              )}
              {(searchProgress.queries || []).map((item, idx) => {
                const statusLabel =
                  item.status === 'searching'
                    ? 'Searching'
                    : item.status === 'pending'
                    ? 'Pending'
                    : item.status === 'done'
                    ? 'Done'
                    : item.status === 'error'
                    ? 'Failed'
                    : item.status;
                const resultSuffix =
                  item.results_count !== undefined ? ` (${item.results_count})` : '';
                return (
                  <div
                    key={`${item.query}-${idx}`}
                    className="flex items-center gap-2 text-[12px] text-slate-700"
                  >
                    <Search className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                    <span className="flex-1 min-w-0 truncate">
                      {item.query}
                    </span>
                    <span className="flex-shrink-0 text-[11px] text-slate-400">
                      {statusLabel}{resultSuffix}
                    </span>
                  </div>
                );
              })}
              {!searchProgress.queries?.length && searchProgress.current_query && (
                <div className="flex items-center gap-2 text-[12px] text-slate-700">
                  <Search className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                  <span className="flex-1 min-w-0 truncate">
                    {searchProgress.current_query}
                  </span>
                  <span className="flex-shrink-0 text-[11px] text-slate-400">Searching</span>
                </div>
              )}
            </div>
          )}

          {searchResult && (
            <div className="flex flex-col gap-1">
              {/* 结果列表 - 仅显示文档列表 */}
              {searchResult.results && searchResult.results.length > 0 && (
                <>
                  {searchResult.results.map((result, idx) => {
                    const key = result.chunkId || result.url || `${result.title}-${idx}`;
                    const isExpandedItem = expandedSearchItems.has(key);
                    const isRAG = searchResult.source === 'rag_search';
                    
                    // 根据文档类型选择图标
                    const getDocIcon = () => {
                      if (!isRAG) {
                        return <Globe className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />;
                      }
                      const contentType = result.contentType?.toLowerCase() || '';
                      if (contentType === 'pdf') {
                        return <FileText className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />;
                      }
                      return <File className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />;
                    };
                    
                    return (
                      <div key={key} className="flex flex-col gap-1">
                        <button
                          onClick={() => toggleSearchItem(key)}
                          className="flex items-center gap-2 text-[12px] text-slate-700 hover:text-blue-600"
                          title="View details"
                        >
                          {getDocIcon()}
                          <span className="min-w-0 flex-1 truncate text-left">
                            {result.title || result.url}
                          </span>
                          {/* RAG: 显示页码 */}
                          {isRAG && result.page !== undefined && (
                            <span className="flex-shrink-0 text-[10px] text-slate-400">
                              p.{result.page}
                              {result.totalPages && `/${result.totalPages}`}
                            </span>
                          )}
                        </button>
                        {isExpandedItem && (
                          <div className="text-[12px] text-slate-500 space-y-1 pl-5">
                            {result.snippet && <MarkdownContent content={result.snippet || ''} />}
                            {result.url && (
                              <a
                                href={result.url.startsWith('s3://') ? '#' : result.url}
                                target={result.url.startsWith('s3://') ? undefined : '_blank'}
                                rel="noopener noreferrer"
                                className={`text-[12px] break-all ${
                                  result.url.startsWith('s3://') 
                                    ? 'text-slate-400 cursor-default' 
                                    : 'text-slate-500 hover:text-blue-600 underline underline-offset-2'
                                }`}
                                onClick={result.url.startsWith('s3://') ? (e) => e.preventDefault() : undefined}
                              >
                                {result.url}
                              </a>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Extract progress (doc_extract) */}
      {extractProgress && (
        <div className="px-2.5 py-2 animate-content-in">
          <div className="flex flex-col gap-1.5">
            {/* Stage message */}
            <div className="flex items-center gap-2 text-[12px] text-slate-600">
              <FileText className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
              <span className="flex-1 min-w-0 truncate">{extractProgress.message}</span>
              <span className="flex-shrink-0 text-[11px] font-mono text-slate-400">
                {extractProgress.percentage.toFixed(0)}%
              </span>
            </div>
            {/* Progress bar */}
            <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ease-out ${
                  extractProgress.stage === 'complete'
                    ? 'bg-green-400'
                    : 'bg-blue-400'
                }`}
                style={{ width: `${Math.min(extractProgress.percentage, 100)}%` }}
              />
            </div>
            {/* Detail info */}
            <div className="flex items-center gap-3 text-[10px] text-slate-400 font-mono">
              {extractProgress.total_pages > 0 && (
                <span>Page {extractProgress.current_page}/{extractProgress.total_pages}</span>
              )}
              {extractProgress.total_figures > 0 && (
                <span>Figure {extractProgress.current_figure}/{extractProgress.total_figures}</span>
              )}
              {extractProgress.stage && (
                <span className="text-slate-300">{extractProgress.stage}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Reasoning (collapsible) */}
      {isExpanded && hasReasoning && (
        <div className="animate-content-in relative">
          <div 
            ref={reasoningRef}
            className={`text-[13px] text-slate-600 leading-normal font-sans px-2.5 py-2 ${
              isReasoningFullyExpanded 
                ? 'max-h-none' 
                : 'max-h-[300px] overflow-y-auto'
            }`}
          >
            <MarkdownContent content={card.reasoning || ''} />
          </div>
          {/* 展开/收起按钮 - 贴着文字块底部边缘 */}
          {(isReasoningOverflowing || isReasoningFullyExpanded) && (
            <div className="absolute bottom-0 left-0 right-0 flex justify-center">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setIsReasoningFullyExpanded(!isReasoningFullyExpanded);
                }}
                className="p-1 rounded-t bg-slate-200/30 text-slate-300 hover:bg-slate-200 hover:text-slate-600 transition-colors"
              >
                {isReasoningFullyExpanded ? (
                  <ChevronUp className="w-3.5 h-3.5" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Action details (only show when completed with extra info) */}
      {isCompleted && card.action && card.action.type === 'type' && card.action.text && (
        <div className="px-2.5 py-2">
          <div className="flex items-start gap-2 text-xs text-slate-500 font-mono min-w-0">
            <span className="font-bold text-slate-400 flex-shrink-0">INPUT &gt;</span>
            <span className="bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200 text-slate-700 break-all">
              {card.action.text}
            </span>
          </div>
        </div>
      )}

      {/* Error details (collapsible) */}
      {showError && hasError && (
        <div className="border-t border-amber-200 bg-amber-50 animate-content-in">
          <div className="px-3 py-2 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-amber-700 mb-1">Error</div>
              <div className="text-xs text-amber-700 font-mono whitespace-pre-wrap break-all max-h-[150px] overflow-y-auto">
                {card.error}
              </div>
            </div>
            <button
              onClick={() => setShowError(false)}
              className="flex-shrink-0 p-0.5 rounded hover:bg-amber-100 text-amber-400 hover:text-amber-600 transition-colors"
              title="Close"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default CUACard;
