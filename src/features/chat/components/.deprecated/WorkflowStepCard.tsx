/**
 * @deprecated This component is for legacy message format compatibility.
 * New implementations should use CardRenderer with NodeCard instead.
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { 
  CheckCircle, 
  Loader2, 
  ChevronDown, 
  ChevronUp, 
  Search, 
  FileText, 
  ListTree, 
  AlertCircle,
  Database,
  FileOutput
} from 'lucide-react';

export interface WorkflowStepProps {
  type: 'plan' | 'retrieval' | 'export' | 'error' | 'default' | 'report';
  title: string;
  content?: string;
  details?: any; // JSON object or string for expanded view
  status: 'running' | 'completed' | 'failed';
  timestamp?: number;
  markdown?: string; // Markdown content for report type
}

// Markdown renderer component
const MarkdownRenderer = ({ content }: { content: string }) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{
      code({node, inline, className, children, ...props}: any) {
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
          <code className={`${className} bg-gray-100 text-pink-600 px-1 py-0.5 rounded text-xs font-mono`} {...props}>
            {children}
          </code>
        );
      },
      ul: ({node, ...props}) => <ul className="list-disc list-outside ml-4 my-2 space-y-1" {...props} />,
      ol: ({node, ...props}) => <ol className="list-decimal list-outside ml-4 my-2 space-y-1" {...props} />,
      li: ({node, ...props}) => <li className="pl-1" {...props} />,
      h1: ({node, ...props}) => <h1 className="text-lg font-bold mt-4 mb-2 border-b border-gray-200 pb-1 first:mt-0" {...props} />,
      h2: ({node, ...props}) => <h2 className="text-base font-bold mt-3 mb-2 first:mt-0" {...props} />,
      h3: ({node, ...props}) => <h3 className="text-sm font-bold mt-2 mb-1 first:mt-0" {...props} />,
      p: ({node, ...props}) => <p className="leading-6 mb-2 last:mb-0" {...props} />,
      a: ({node, ...props}) => <a className="text-blue-600 hover:text-blue-700 underline underline-offset-2" target="_blank" rel="noopener noreferrer" {...props} />,
      table: ({node, ...props}) => <div className="overflow-x-auto my-3 rounded border border-gray-200"><table className="min-w-full text-xs text-left" {...props} /></div>,
      thead: ({node, ...props}) => <thead className="bg-gray-50 text-gray-700 font-medium" {...props} />,
      th: ({node, ...props}) => <th className="px-3 py-2 border-b border-gray-200" {...props} />,
      td: ({node, ...props}) => <td className="px-3 py-2 border-b border-gray-100" {...props} />,
      blockquote: ({node, ...props}) => <blockquote className="border-l-3 border-gray-300 pl-3 my-2 italic text-gray-600" {...props} />,
      hr: ({node, ...props}) => <hr className="my-4 border-t border-gray-200" {...props} />,
    }}
  >
    {content}
  </ReactMarkdown>
);

export const WorkflowStepCard: React.FC<WorkflowStepProps> = ({
  type,
  title,
  content,
  details,
  status,
  markdown
}) => {
  // 报告类型的卡片默认展开（当有 markdown 内容时）
  const shouldAutoExpand = type === 'report' || (!!markdown);
  const [isExpanded, setIsExpanded] = useState(shouldAutoExpand);
  
  // 当 markdown 内容出现时自动展开
  React.useEffect(() => {
    if (markdown && !isExpanded) {
      setIsExpanded(true);
    }
  }, [markdown]);

  // Get icon based on type - 统一使用灰色系
  const getIcon = () => {
    const className = `w-4 h-4 text-gray-400 ${status === 'running' ? 'animate-pulse' : ''}`;
    switch (type) {
      case 'plan': return <ListTree className={className} />;
      case 'retrieval': return <Search className={className} />;
      case 'export': return <FileText className={className} />;
      case 'report': return <FileOutput className={className} />;
      case 'error': return <AlertCircle className={`${className} text-gray-500`} />;
      default: return <Database className={className} />;
    }
  };

  // Get status icon - 状态图标保留颜色以区分状态
  const getStatusIcon = () => {
    if (status === 'running') return <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />;
    if (status === 'completed') return <CheckCircle className="w-3.5 h-3.5 text-green-500" />;
    if (status === 'failed') return <AlertCircle className="w-3.5 h-3.5 text-red-500" />;
    return null;
  };

  // 只有 markdown 或 content 时才显示展开按钮，不显示 JSON details
  const hasDetails = !!content || !!markdown;

  return (
    <div className="group border border-gray-100 rounded-lg bg-white hover:shadow-sm transition-all duration-200 overflow-hidden mb-2">
      {/* Header - 标题栏 */}
      <div 
        className={`flex items-center gap-3 px-3 py-2.5 ${hasDetails ? 'cursor-pointer hover:bg-gray-50/50' : ''} transition-colors`}
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
      >
        {/* Left Icon & Title */}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          {getIcon()}
          <span className={`text-sm truncate ${status === 'running' ? 'text-amber-600/80 animate-pulse' : 'text-gray-700'}`}>
            {title}
          </span>
        </div>

        {/* Right Status & Expand Icon */}
        <div className="flex items-center gap-2">
          <div className="opacity-60">
            {getStatusIcon()}
          </div>

          {hasDetails && (
            isExpanded ? 
            <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : 
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          )}
        </div>
      </div>

      {/* Expanded Details - 上下结构，用细线隔开 */}
      {isExpanded && (markdown || content) && (
        <>
          {/* 分隔线 */}
          <div className="border-t border-gray-100" />
          
          {/* 内容区域 - 只显示 markdown 和 content，不显示 JSON details */}
          <div className="px-4 py-3 animate-in slide-in-from-top-1 duration-200">
            {/* Markdown content (for report type) */}
            {markdown && (
              <div className="text-sm text-gray-700 max-h-[500px] overflow-y-auto">
                <MarkdownRenderer content={markdown} />
              </div>
            )}
            
            {/* Plain text content */}
            {content && !markdown && (
              <div className="text-sm text-gray-600 whitespace-pre-wrap">
                {content}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};


