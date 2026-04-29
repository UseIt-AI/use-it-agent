/**
 * CardRenderer - 统一卡片渲染组件
 * 支持 tool, cua, node 三种卡片类型
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import {
  ChevronDown,
  ChevronUp,
  Clock,
  Wrench,
  Pencil,
  PenTool,
  Calculator,
  Code,
  FileJson,
} from 'lucide-react';
import type { Card } from '../handlers/types';
import { CUACard } from './CUACard';
import { NodeCard } from './NodeCard';
import { StatusIcon, LoadingSpinner, type TaskStatus } from './StatusIcons';

// ==================== 通用组件 ====================

/**
 * Markdown 渲染组件
 */
const MarkdownContent = ({ content }: { content: string }) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{
      code({ node, inline, className, children, ...props }: any) {
        const match = /language-(\w+)/.exec(className || '');
        return !inline && match ? (
          <div className="rounded-md overflow-hidden my-2 border border-gray-200 shadow-sm">
            <SyntaxHighlighter
              style={oneDark}
              language={match[1]}
              PreTag="div"
              customStyle={{ margin: 0, borderRadius: 0, fontSize: '12px' }}
              {...props}
            >
              {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
          </div>
        ) : (
          <code
            className={`${className} bg-gray-100 text-pink-600 px-1 py-0.5 rounded text-xs font-mono break-all`}
            {...props}
          >
            {children}
          </code>
        );
      },
      ul: ({ node, ...props }) => (
        <ul className="list-disc list-outside ml-4 my-2 space-y-1" {...props} />
      ),
      ol: ({ node, ...props }) => (
        <ol className="list-decimal list-outside ml-4 my-2 space-y-1" {...props} />
      ),
      li: ({ node, ...props }) => <li className="pl-1" {...props} />,
      h1: ({ node, ...props }) => (
        <h1 className="text-base font-bold mt-3 mb-2 first:mt-0" {...props} />
      ),
      h2: ({ node, ...props }) => (
        <h2 className="text-sm font-bold mt-2 mb-1 first:mt-0" {...props} />
      ),
      h3: ({ node, ...props }) => (
        <h3 className="text-sm font-semibold mt-2 mb-1 first:mt-0" {...props} />
      ),
      p: ({ node, ...props }) => (
        <p className="leading-relaxed mb-2 last:mb-0" {...props} />
      ),
      a: ({ node, ...props }) => (
        <a
          className="text-blue-600 hover:text-blue-700 underline underline-offset-2"
          target="_blank"
          rel="noopener noreferrer"
          {...props}
        />
      ),
      table: ({ node, ...props }) => (
        <div className="overflow-x-auto my-2 rounded border border-gray-200">
          <table className="min-w-full text-xs text-left" {...props} />
        </div>
      ),
      thead: ({ node, ...props }) => (
        <thead className="bg-gray-50 text-gray-700 font-medium" {...props} />
      ),
      th: ({ node, ...props }) => (
        <th className="px-2 py-1.5 border-b border-gray-200" {...props} />
      ),
      td: ({ node, ...props }) => (
        <td className="px-2 py-1.5 border-b border-gray-100" {...props} />
      ),
      blockquote: ({ node, ...props }) => (
        <blockquote
          className="border-l-2 border-gray-300 pl-3 my-2 italic text-gray-600"
          {...props}
        />
      ),
      hr: ({ node, ...props }) => (
        <hr className="my-3 border-t border-gray-200" {...props} />
      ),
    }}
  >
    {content}
  </ReactMarkdown>
);

// ==================== Tool 卡片 ====================

// 工具名称到显示名称的映射
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  modify_design: '修改设计参数',
  autocad_draw: 'AutoCAD 绘图',
  preliminary_calculation: '初步工程计算',
};

// 工具名称到图标的映射
const getToolIcon = (toolName: string | undefined, isRunning: boolean) => {
  const baseClass = `w-4 h-4 ${isRunning ? 'animate-pulse' : ''}`;

  const iconMap: Record<string, React.ReactNode> = {
    modify_design: <Pencil className={`${baseClass} text-blue-500`} />,
    autocad_draw: <PenTool className={`${baseClass} text-emerald-500`} />,
    preliminary_calculation: <Calculator className={`${baseClass} text-amber-500`} />,
  };

  return iconMap[toolName || ''] || <Wrench className={`${baseClass} text-gray-400`} />;
};

// 格式化输入参数显示
const formatInput = (input: Record<string, any>): string => {
  if (!input) return '';

  const entries = Object.entries(input);
  if (entries.length === 0) return '';

  return entries
    .map(([key, value]) => {
      if (key === 'config') return null;

      let displayValue = typeof value === 'string' ? value : JSON.stringify(value);
      if (displayValue.length > 100) {
        displayValue = displayValue.substring(0, 100) + '...';
      }

      const friendlyNames: Record<string, string> = {
        user_requirements: '用户需求',
        template_name: '模板名称',
      };

      const displayKey = friendlyNames[key] || key;
      return `${displayKey}: ${displayValue}`;
    })
    .filter(Boolean)
    .join('\n');
};

const ToolCard: React.FC<{ card: Card }> = ({ card }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isRunning = card.status === 'running';

  const displayName = isRunning
    ? 'Thinking...'
    : card.title || TOOL_DISPLAY_NAMES[card.toolName || ''] || card.toolName || '工具调用';

  const hasDetails = card.input || card.output || card.reasoning;

  return (
    <div
      className={`group border rounded-md bg-white transition-all duration-200 overflow-hidden animate-card-in ${
        card.status === 'failed'
          ? 'border-red-200 bg-red-50/30'
          : isRunning
          ? 'border-slate-300 ring-1 ring-slate-300/30'
          : 'border-slate-200 shadow-sm'
      }`}
    >
      {/* 头部 */}
      <div
        className={`flex items-center gap-2.5 px-3 py-2 ${
          hasDetails ? 'cursor-pointer hover:bg-slate-50' : ''
        } transition-colors`}
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
      >
        {/* 左侧：工具图标和名称 */}
        <div className="flex-1 flex items-start gap-2 min-w-0">
          <div
            className={`flex-shrink-0 w-6 h-6 rounded flex items-center justify-center border ${
              isRunning
                ? 'bg-amber-50 border-amber-100'
                : 'bg-slate-50 border-slate-200'
            }`}
          >
            {isRunning ? (
              <LoadingSpinner size="sm" />
            ) : (
              getToolIcon(card.toolName, isRunning)
            )}
          </div>
          <span
            className={`text-xs font-medium font-mono break-all ${
              isRunning ? 'text-slate-600 animate-pulse' : 'text-slate-700'
            }`}
          >
            {displayName}
          </span>
        </div>

        {/* 右侧：状态和展开按钮 */}
        <div className="flex items-center gap-1.5">
          {card.duration !== undefined && card.status === 'completed' && (
            <div className="hidden group-hover:flex items-center gap-1 text-[10px] text-slate-400 font-mono">
              <Clock className="w-2.5 h-2.5" />
              <span>{card.duration.toFixed(1)}s</span>
            </div>
          )}

          <div className="opacity-70">
            <StatusIcon status={card.status as TaskStatus} size="sm" />
          </div>

          {hasDetails &&
            (isExpanded ? (
              <ChevronUp className="w-3 h-3 text-slate-400" />
            ) : (
              <ChevronDown className="w-3 h-3 text-slate-400" />
            ))}
        </div>
      </div>

      {/* 展开详情 */}
      {isExpanded && hasDetails && (
        <>
          <div className="border-t border-slate-100" />

          <div className="animate-in slide-in-from-top-1 duration-200 bg-white">
            {/* 思考过程 */}
            {card.reasoning && (
              <div className="text-sm text-slate-600 leading-relaxed font-sans px-4 py-3 border-b border-slate-50 last:border-0">
                <MarkdownContent content={card.reasoning} />
              </div>
            )}

            {/* 输入参数和输出结果容器 */}
            {(card.input || card.output) && (
              <div className="px-4 py-3 space-y-3">
                {/* 输入参数 */}
                {card.input && Object.keys(card.input).length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <Code className="w-3 h-3 text-slate-400" />
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
                        Input Parameters
                      </span>
                    </div>
                    <div className="bg-slate-50 rounded border border-slate-200 px-3 py-2 text-xs text-slate-600 font-mono whitespace-pre-wrap shadow-sm">
                      {formatInput(card.input)}
                    </div>
                  </div>
                )}

                {/* 输出结果 */}
                {card.output && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <FileJson className="w-3 h-3 text-slate-400" />
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
                        Execution Result
                      </span>
                    </div>
                    <div
                      className={`rounded border px-3 py-2 text-xs font-mono whitespace-pre-wrap shadow-sm ${
                        card.status === 'completed'
                          ? 'bg-slate-50 text-slate-600 border-slate-200'
                          : 'bg-slate-50 text-slate-600 border-slate-200'
                      }`}
                    >
                      {card.output.length > 500 ? card.output.substring(0, 500) + '...' : card.output}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

// ==================== 主组件 ====================

interface CardRendererProps {
  card: Card;
  screenshots?: string[];
}

/**
 * 统一卡片渲染组件
 */
export const CardRenderer: React.FC<CardRendererProps> = ({
  card,
  screenshots = [],
}) => {
  // Node 卡片：渲染为分隔标题
  if (card.type === 'node') {
    return <NodeCard card={card} />;
  }

  // Tool/CUA 卡片：不再缩进，保持左右边距一致
  return (
    <div>
      {card.type === 'tool' && <ToolCard card={card} />}
      {card.type === 'cua' && (
        <CUACard
          card={card}
          screenshot={
            card.screenshotIndex !== undefined ? screenshots[card.screenshotIndex] : undefined
          }
        />
      )}
    </div>
  );
};

export default CardRenderer;
