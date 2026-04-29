/**
 * @deprecated This component is for legacy message format compatibility.
 * New implementations should use CardRenderer with tool card type instead.
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { 
  Pencil, 
  PenTool,
  Calculator,
  Settings,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle,
  Loader2,
  XCircle,
  Wrench,
  Code,
  FileJson
} from 'lucide-react';

// Markdown 渲染组件
const MarkdownContent = ({ content }: { content: string }) => (
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
      h1: ({node, ...props}) => <h1 className="text-base font-bold mt-3 mb-2 first:mt-0" {...props} />,
      h2: ({node, ...props}) => <h2 className="text-sm font-bold mt-2 mb-1 first:mt-0" {...props} />,
      h3: ({node, ...props}) => <h3 className="text-sm font-semibold mt-2 mb-1 first:mt-0" {...props} />,
      p: ({node, ...props}) => <p className="leading-relaxed mb-2 last:mb-0" {...props} />,
      a: ({node, ...props}) => <a className="text-blue-600 hover:text-blue-700 underline underline-offset-2" target="_blank" rel="noopener noreferrer" {...props} />,
      table: ({node, ...props}) => <div className="overflow-x-auto my-2 rounded border border-gray-200"><table className="min-w-full text-xs text-left" {...props} /></div>,
      thead: ({node, ...props}) => <thead className="bg-gray-50 text-gray-700 font-medium" {...props} />,
      th: ({node, ...props}) => <th className="px-2 py-1.5 border-b border-gray-200" {...props} />,
      td: ({node, ...props}) => <td className="px-2 py-1.5 border-b border-gray-100" {...props} />,
      blockquote: ({node, ...props}) => <blockquote className="border-l-2 border-gray-300 pl-3 my-2 italic text-gray-600" {...props} />,
      strong: ({node, ...props}) => <strong className="font-semibold" {...props} />,
      hr: ({node, ...props}) => <hr className="my-3 border-t border-gray-200" {...props} />,
    }}
  >
    {content}
  </ReactMarkdown>
);

export interface ToolStepProps {
  toolName: string;
  toolDisplayName?: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  input?: Record<string, any>;
  output?: string;
  error?: string;
  duration?: number;
  timestamp?: number;
  reasoning?: string; // LLM 调用工具前的思考内容
}

// 工具名称到显示名称的映射
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  'modify_design': '修改设计参数',
  'autocad_draw': 'AutoCAD 绘图',
  'preliminary_calculation': '初步工程计算',
};

// 工具名称到图标的映射
const getToolIcon = (toolName: string, status: string) => {
  const isRunning = status === 'running';
  const baseClass = `w-4 h-4 ${isRunning ? 'animate-pulse' : ''}`;
  
  const iconMap: Record<string, React.ReactNode> = {
    'modify_design': <Pencil className={`${baseClass} text-blue-500`} />,
    'autocad_draw': <PenTool className={`${baseClass} text-emerald-500`} />,
    'preliminary_calculation': <Calculator className={`${baseClass} text-amber-500`} />,
  };
  
  return iconMap[toolName] || <Wrench className={`${baseClass} text-gray-400`} />;
};

// 格式化输入参数显示
const formatInput = (input: Record<string, any>): string => {
  if (!input) return '';
  
  const entries = Object.entries(input);
  if (entries.length === 0) return '';
  
  // 特殊处理某些参数
  return entries.map(([key, value]) => {
    // 隐藏 config 参数
    if (key === 'config') return null;
    
    // 截断过长的值
    let displayValue = typeof value === 'string' ? value : JSON.stringify(value);
    if (displayValue.length > 100) {
      displayValue = displayValue.substring(0, 100) + '...';
    }
    
    // 友好的参数名称
    const friendlyNames: Record<string, string> = {
      'user_requirements': '用户需求',
      'template_name': '模板名称',
    };
    
    const displayKey = friendlyNames[key] || key;
    return `${displayKey}: ${displayValue}`;
  }).filter(Boolean).join('\n');
};

export const ToolStepCard: React.FC<ToolStepProps> = ({
  toolName,
  toolDisplayName,
  status,
  input,
  output,
  error,
  duration,
  reasoning,
}) => {
  // 默认收起，点击展开
  const [isExpanded, setIsExpanded] = useState(false);
  
  // 执行中时显示 "Thinking..."，完成后显示工具名称
  const baseDisplayName = toolDisplayName || TOOL_DISPLAY_NAMES[toolName] || toolName;
  const displayName = status === 'running' ? 'Thinking...' : baseDisplayName;
  const hasDetails = input || output || error || reasoning;
  
  // 如果没有有效的工具名称，不渲染这个卡片
  if (!toolName && !toolDisplayName) {
    return null;
  }
  
  // 状态图标
  const getStatusIcon = () => {
    switch (status) {
      case 'pending':
        return <Clock className="w-3.5 h-3.5 text-gray-400" />;
      case 'running':
        return <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />;
      case 'completed':
        return <CheckCircle className="w-3.5 h-3.5 text-green-500" />;
      case 'error':
        return <XCircle className="w-3.5 h-3.5 text-red-500" />;
      default:
        return null;
    }
  };
  
  // 状态文本和样式
  const getStatusStyle = () => {
    switch (status) {
      case 'pending':
        return 'text-gray-500';
      case 'running':
        return 'text-blue-600 animate-pulse';
      case 'completed':
        return 'text-gray-700';
      case 'error':
        return 'text-red-600';
      default:
        return 'text-gray-700';
    }
  };
  
  return (
    <div className={`group border rounded-lg bg-white transition-all duration-200 overflow-hidden ${
      status === 'error' ? 'border-red-200 bg-red-50/30' : 'border-gray-100 hover:shadow-sm'
    }`}>
      {/* 头部 */}
      <div 
        className={`flex items-center gap-3 px-3 py-2.5 ${hasDetails ? 'cursor-pointer hover:bg-gray-50/50' : ''} transition-colors`}
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
      >
        {/* 左侧：工具图标和名称 */}
        <div className="flex-1 flex items-center gap-2.5 min-w-0">
          <div className={`flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center border ${status === 'running' ? 'bg-blue-50 border-blue-100 animate-pulse' : 'bg-gray-50 border-gray-100'}`}>
            {getToolIcon(toolName, status)}
          </div>
          <span className={`text-sm font-medium truncate ${status === 'running' ? 'text-blue-600 animate-pulse' : getStatusStyle()}`}>
            {displayName}
          </span>
        </div>

        {/* 右侧：状态和展开按钮 */}
        <div className="flex items-center gap-2">
          {duration !== undefined && status === 'completed' && (
            <div className="hidden group-hover:flex items-center gap-1 text-[10px] text-gray-400">
              <Clock className="w-3 h-3" />
              <span>{duration.toFixed(1)}s</span>
            </div>
          )}
          
          <div className="opacity-70">
            {getStatusIcon()}
          </div>

          {hasDetails && (
            isExpanded ? 
            <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : 
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          )}
        </div>
      </div>

      {/* 展开详情 */}
      {isExpanded && hasDetails && (
        <>
          <div className="border-t border-gray-100" />
          
          <div className="px-4 py-3 animate-in slide-in-from-top-1 duration-200 space-y-3">
            {/* 思考过程 / Reasoning - 支持 Markdown */}
            {reasoning && (
              <div className="text-sm text-gray-600 leading-relaxed">
                <MarkdownContent content={reasoning} />
              </div>
            )}
            
            {/* 输入参数 */}
            {input && Object.keys(input).length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <Code className="w-3 h-3 text-gray-400" />
                  <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">输入参数</span>
                </div>
                <div className="bg-gray-50 rounded-md px-3 py-2 text-xs text-gray-600 font-mono whitespace-pre-wrap border border-gray-100">
                  {formatInput(input)}
                </div>
              </div>
            )}
            
            {/* 输出结果 */}
            {output && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <FileJson className="w-3 h-3 text-gray-400" />
                  <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">执行结果</span>
                </div>
                <div className={`rounded-md px-3 py-2 text-xs font-mono whitespace-pre-wrap border ${
                  status === 'completed' 
                    ? 'bg-green-50/50 text-green-700 border-green-100' 
                    : 'bg-gray-50 text-gray-600 border-gray-100'
                }`}>
                  {output.length > 500 ? output.substring(0, 500) + '...' : output}
                </div>
              </div>
            )}
            
            {/* 错误信息 */}
            {error && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <XCircle className="w-3 h-3 text-red-400" />
                  <span className="text-[10px] font-medium text-red-500 uppercase tracking-wide">错误信息</span>
                </div>
                <div className="bg-red-50 rounded-md px-3 py-2 text-xs text-red-600 font-mono whitespace-pre-wrap border border-red-100">
                  {error}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};


