/**
 * MessageList - 消息列表渲染组件
 * 基于 message-schema-v2.md 文档设计
 * 
 * 核心设计：
 * - 按 blocks 数组顺序渲染 TextBlock 和 CardBlock
 * - 支持 V2 新格式（blocks 数组）和旧格式（content + details）
 */

import React, { useRef, useEffect, useState } from 'react';
import { Terminal, Copy, Check, File, Folder } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { useTranslation } from 'react-i18next';
import type { Message, ContentBlock, Card, CompletionBlock } from '../handlers/types';
import type { AskUserResponse } from '../handlers/localEngine/types';
import { CardRenderer } from './CardRenderer';
import { NodeCard } from './NodeCard';
import { CompletionCard } from './CompletionCard';
import { AskUserCard } from './AskUserCard';
import { LoadingSpinner } from './StatusIcons';
import { SyncProgressCard, DeleteConfirmationCard, type SyncProgressInfo, type DeletedFileInfo } from './SyncStatusCard';
import { ImagePreviewModal } from './ImagePreviewModal';


interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  /** 文件同步进度信息（显示在 loading 区域） */
  syncProgress?: SyncProgressInfo | null;
  /** 取消同步 */
  onCancelSync?: () => void;
  /** 文件删除确认信息 */
  deleteConfirmation?: {
    deletedFiles: DeletedFileInfo[];
  } | null;
  /** 确认删除并继续上传 */
  onConfirmDelete?: (shouldDelete: boolean) => void;
  /** 取消删除确认 */
  onCancelDeleteConfirm?: () => void;
  /**
   * Called by inline `AskUserCard` when the user answers / dismisses an
   * `ask_user` block. The parent (useChat via ChatPanel) is responsible
   * for updating the block status in `messages` AND resolving the
   * orchestrator-side promise (see `useAskUserStore.settle`).
   */
  onAskUserSettle?: (toolCallId: string, reply: AskUserResponse) => void;
}

// ==================== Markdown 渲染组件 ====================

const MarkdownContent = ({ content, isUser }: { content: string; isUser: boolean }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ node, inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || '');
          return !inline && match ? (
            <div className="rounded-md overflow-hidden my-2 bg-[#282c34]">
              <SyntaxHighlighter
                style={oneDark}
                language={match[1]}
                PreTag="div"
                customStyle={{ margin: 0, borderRadius: 0, fontSize: 'var(--font-size-sm)', background: 'transparent' }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            </div>
          ) : (
            <code
              className={`${className} ${
                isUser ? 'bg-white text-pink-600' : 'bg-gray-100 text-pink-600'
              } px-1.5 py-0.5 rounded text-app-sm font-medium font-mono break-all`}
              {...props}
            >
              {children}
            </code>
          );
        },
        ul: ({ node, ...props }) => (
          <ul className="list-disc list-outside ml-5 my-1.5" {...props} />
        ),
        ol: ({ node, ...props }) => (
          <ol className="list-decimal list-outside ml-5 my-1.5" {...props} />
        ),
        li: ({ node, ...props }) => (
          <li className="pl-1 mb-1 last:mb-0 [&>p]:inline [&>p]:mb-0 [&>ul]:block [&>ol]:block [&>ul]:mt-1 [&>ol]:mt-1" {...props} />
        ),
        h1: ({ node, ...props }) => (
          <h1
            className="text-app-xl font-bold mt-4 mb-2 pb-1 first:mt-0"
            {...props}
          />
        ),
        h2: ({ node, ...props }) => (
          <h2 className="text-app-lg font-bold mt-3 mb-1.5 first:mt-0" {...props} />
        ),
        h3: ({ node, ...props }) => (
          <h3 className="text-app-base font-bold mt-2 mb-1 first:mt-0" {...props} />
        ),
        p: ({ node, ...props }) => <p className="leading-7 mb-2 last:mb-0" {...props} />,
        a: ({ node, ...props }) => (
          <a
            className="underline underline-offset-2 text-blue-600 hover:text-blue-700 decoration-blue-300"
            target="_blank"
            rel="noopener noreferrer"
            {...props}
          />
        ),
        table: ({ node, ...props }) => (
          <div className="overflow-x-auto my-4 bg-white">
            <table className="min-w-full text-app-sm text-left" {...props} />
          </div>
        ),
        thead: ({ node, ...props }) => (
          <thead className="bg-gray-50 text-gray-700 font-medium" {...props} />
        ),
        th: ({ node, ...props }) => (
          <th className="px-4 py-3 border-b border-gray-100" {...props} />
        ),
        td: ({ node, ...props }) => (
          <td className="px-4 py-3 border-b border-gray-50" {...props} />
        ),
        blockquote: ({ node, ...props }) => (
          <blockquote
            className="border-l-4 pl-4 my-3 italic border-gray-400 text-gray-600 bg-white/50 py-1"
            {...props}
          />
        ),
        hr: ({ node, ...props }) => (
          <hr
            className="my-6 border-t border-gray-300"
            {...props}
          />
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

// ==================== V2 格式渲染 ====================

/**
 * 渲染单个内容块
 */
/**
 * 检测文本是否为 tool action JSON（不需要在 UI 中显示）
 * 这类 JSON 由后端 AI 输出，包含 Action/Args 等字段，
 * 实际操作已通过 tool_call 事件处理，文本形式只是噪音。
 */
function isToolActionJson(text: string): boolean {
  const trimmed = text.trim();
  // 快速排除：必须以 { 开头
  if (!trimmed.startsWith('{')) return false;
  try {
    const parsed = JSON.parse(trimmed);
    // 检测典型的 tool action JSON 结构
    return (
      parsed &&
      typeof parsed === 'object' &&
      typeof parsed.Action === 'string' &&
      'Args' in parsed
    );
  } catch {
    return false;
  }
}

const BlockRenderer: React.FC<{
  block: ContentBlock;
  isUser: boolean;
  screenshots?: string[];
  onAskUserSettle?: (toolCallId: string, reply: AskUserResponse) => void;
}> = ({ block, isUser, screenshots, onAskUserSettle }) => {
  if (block.type === 'text') {
    if (!block.content.trim()) return null;
    // 过滤掉 tool action JSON（如 draw_from_json 的参数体），这些内容不需要显示
    if (isToolActionJson(block.content)) return null;
    return (
      <div className="animate-fade-in-up text-[#1A1A1A]">
        <MarkdownContent content={block.content} isUser={isUser} />
      </div>
    );
  }

  if (block.type === 'card') {
    return <CardRenderer card={block.card} screenshots={screenshots} />;
  }

  if (block.type === 'completion') {
    return <CompletionCard block={block} />;
  }

  if (block.type === 'ask_user') {
    return (
      <AskUserCard
        block={block}
        onSettle={(id, reply) => onAskUserSettle?.(id, reply)}
      />
    );
  }

  return null;
};

/**
 * V2 格式消息渲染器
 * 支持 Node 折叠功能
 */
const V2MessageRenderer: React.FC<{
  message: Message;
  isUser: boolean;
  onAskUserSettle?: (toolCallId: string, reply: AskUserResponse) => void;
}> = ({ message, isUser, onAskUserSettle }) => {
  const screenshots = message.screenshots || [];
  // 追踪每个 Node 的折叠状态（默认展开）
  const [collapsedNodes, setCollapsedNodes] = React.useState<Set<string>>(new Set());


  const toggleNode = (nodeId: string) => {
    setCollapsedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  // 渲染 blocks，处理 Node 折叠逻辑
  const renderBlocks = () => {
    const elements: React.ReactNode[] = [];
    let currentNodeId: string | null = null;

    for (let i = 0; i < message.blocks.length; i++) {
      const block = message.blocks[i];

      if (block.type === 'card' && block.card.type === 'node') {
        // Node 卡片
        const nodeId = block.card.id; // 使用 const 捕获当前值，避免闭包问题
        currentNodeId = nodeId;
        const isCollapsed = collapsedNodes.has(nodeId);
        
        elements.push(
          <NodeCard 
            key={`node-${nodeId}`}
            card={block.card} 
            isCollapsed={isCollapsed}
            onToggleCollapse={() => toggleNode(nodeId)}
          />
        );
      } else if (block.type === 'card' && block.card.nodeId) {
        // 属于某个 Node 的卡片（如 CUA）
        const nodeId = block.card.nodeId;
        const isCollapsed = collapsedNodes.has(nodeId);
        
        if (!isCollapsed) {
          elements.push(
            <CardRenderer key={`block-${i}`} card={block.card} screenshots={screenshots} />
          );
        }
      } else {
        // 其他 blocks（文本、独立卡片等）
        elements.push(
          <BlockRenderer
            key={`block-${i}`}
            block={block}
            isUser={isUser}
            screenshots={screenshots}
            onAskUserSettle={onAskUserSettle}
          />
        );
      }
    }

    return elements;
  };

  return <div className="flex flex-col gap-3">{renderBlocks()}</div>;
};

// ==================== 旧格式兼容渲染 ====================

/**
 * 解析旧格式消息内容为多个区块（兼容旧版本）
 */
const parseMessageSections = (content: string, details: any): any[] => {
  const sections: any[] = [];
  const workflowSteps = details?.workflow_steps || [];
  const sectionPattern = /\n*---\n(?=### 子任务:|🎉)/g;
  const parts = content.split(sectionPattern);
  let cardIndex = 0;

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i].trim();
    if (!part) continue;

    if (part.startsWith('🎉')) {
      sections.push({ id: `complete_${i}`, type: 'complete', text: part });
      continue;
    }

    const isCuaPart = part.includes('--- 第');
    if (isCuaPart) {
      const cuaEndMarkers = ['--- CUA 任务结束 ---', 'CUA 任务已完成', 'CUA 数据收集完成'];
      const isCuaCompleted = cuaEndMarkers.some((marker) => part.includes(marker));
      const cuaParts = part.split(/--- 第 (\d+) 步 ---/);
      const cuaSteps: any[] = [];

      if (cuaParts.length > 1) {
        for (let j = 1; j < cuaParts.length; j += 2) {
          const stepNum = parseInt(cuaParts[j]);
          const stepContent = cuaParts[j + 1] || '';
          const reasoningMatch = stepContent.match(
            /^([\s\S]*?)(?=\n.*执行:|--- CUA|CUA 任务|CUA 数据|$)/
          );
          const reasoning = reasoningMatch ? reasoningMatch[1].trim() : '';
          const actionMatch = stepContent.match(/执行: (.*?)(\n|$)/);
          const action = actionMatch
            ? actionMatch[1].trim()
            : isCuaCompleted
            ? '已完成'
            : 'Thinking...';
          const screenshot = details?.screenshots?.[stepNum - 1];
          const actionDetails = details?.cua_actions?.[stepNum - 1];
          const isLastStep = j === cuaParts.length - 2;
          const status = isCuaCompleted ? 'completed' : isLastStep ? 'running' : 'completed';
          cuaSteps.push({ stepNumber: stepNum, action, reasoning, screenshot, actionDetails, status });
        }
      }
      sections.push({ id: `cua_${i}`, type: 'cua', text: cuaParts[0], cuaSteps });
    } else if (part.startsWith('### 子任务:')) {
      const lines = part.split('\n');
      const description = lines.slice(1).join('\n').trim();
      const sectionCards: any[] = [];
      const isRagTask =
        description.includes('检索') || description.includes('RAG') || description.includes('报告');
      const isExportTask =
        description.includes('导出') ||
        description.includes('Word') ||
        description.includes('文档');

      while (cardIndex < workflowSteps.length) {
        const card = workflowSteps[cardIndex];
        const cardTitle = card.title || '';
        const cardType = card.type || '';
        const isRagCard =
          cardTitle.includes('检索') ||
          cardTitle.includes('查询') ||
          cardType === 'retrieval' ||
          cardType === 'report' ||
          cardTitle.includes('报告');
        const isExportCard =
          cardTitle.includes('文档') || cardTitle.includes('导出') || cardType === 'export';

        if (isRagTask && isRagCard) {
          sectionCards.push(card);
          cardIndex++;
        } else if (isExportTask && isExportCard) {
          sectionCards.push(card);
          cardIndex++;
        } else if (!isRagTask && !isExportTask) {
          sectionCards.push(card);
          cardIndex++;
        } else {
          break;
        }
      }
      sections.push({ id: `subtask_${i}`, type: 'subtask', text: part, workflowCards: sectionCards });
    } else {
      sections.push({ id: `intro_${i}`, type: 'intro', text: part });
    }
  }

  if (cardIndex < workflowSteps.length) {
    const remainingCards = workflowSteps.slice(cardIndex);
    const lastSubtask = sections.filter((s) => s.type === 'subtask').pop();
    if (lastSubtask) {
      lastSubtask.workflowCards = [...(lastSubtask.workflowCards || []), ...remainingCards];
    } else {
      sections.push({ id: 'cards_only', type: 'subtask', text: '', workflowCards: remainingCards });
    }
  }
  return sections;
};

/**
 * 旧格式消息渲染器（兼容旧版本）
 */
const LegacyMessageRenderer: React.FC<{
  message: Message;
  isUser: boolean;
}> = ({ message, isUser }) => {
  const sections = parseMessageSections(message.content || '', message.details);

  return (
    <>
      {sections.map((section, idx) => (
        <div
          key={section.id}
          className={idx > 0 && section.type !== 'complete' ? 'mt-6 pt-4 border-t border-gray-100' : ''}
        >
          {section.text && (
            <div className="text-[#1A1A1A]">
              <MarkdownContent content={section.text} isUser={isUser} />
            </div>
          )}

        </div>
      ))}


      {message.details?.excel_steps && message.details.excel_steps.length > 0 && (
        <div className="flex flex-col gap-2 mt-4 bg-blue-50/30 border border-blue-100 rounded-md p-3">
          {message.details.excel_steps.map((step: any, idx: number) => (
            <div key={idx} className="flex flex-col gap-1">
              <div
                className={`flex items-center gap-2 text-sm transition-all duration-300 ${
                  step.status === 'running'
                    ? 'text-blue-600'
                    : step.status === 'completed'
                    ? 'text-green-600'
                    : 'text-red-600'
                }`}
              >
                <span className="font-medium">{step.message}</span>
              </div>
              {step.status === 'running' && step.thinking && (
                <div className="ml-6 mt-1 text-xs text-gray-600 font-mono bg-gray-50 p-2 border border-gray-200 max-h-32 overflow-y-auto">
                  {step.thinking}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

    </>
  );
};

// ==================== 主组件 ====================

/**
 * 判断消息是否使用 V2 格式
 */
function isV2Message(message: Message): boolean {
  return Array.isArray(message.blocks) && message.blocks.length > 0;
}

/** 最后一条 assistant 是否含有待用户作答的 ask_user 块（与底部 loading 文案联动） */
function hasPendingAskUserBlock(message: Message | undefined): boolean {
  if (!message || message.role !== 'assistant' || !message.blocks?.length) return false;
  return message.blocks.some(
    (b) => b.type === 'ask_user' && b.status === 'pending'
  );
}

/**
 * 检查是否应该隐藏底部 loading
 */
function shouldHideLoader(message: Message): boolean {
  // V2 格式：检查是否有正在运行的卡片（Node 或 CUA）
  // 只要有任何 running 状态的卡片，就隐藏底部 loading
  if (isV2Message(message)) {
    return message.blocks.some(
      (block) => block.type === 'card' && block.card.status === 'running'
    );
  }

  // 旧格式
  const content = message.content || '';
  return (
    content.includes('--- 第') &&
    !['--- CUA 任务结束 ---', 'CUA 任务已完成', 'CUA 数据收集完成'].some((marker) =>
      content.includes(marker)
    )
  );
}

// 文字波浪动画组件
const WaveText: React.FC<{ text: string }> = ({ text }) => {
  return (
    <span className="animate-wave">
      {text}
    </span>
  );
};

// Loading 阶段提示 Hook
// 阶段: 0 -> "Loading Workflow" (1s) -> 1 -> "Thinking" (1s) -> 2 -> "Planning Next Move" (持续)
const useLoadingPhase = (isLoading: boolean): number => {
  const [phase, setPhase] = React.useState(0);
  const timerRef = React.useRef<NodeJS.Timeout | null>(null);

  React.useEffect(() => {
    // 当 loading 开始时，重置阶段并启动计时器
    if (isLoading) {
      setPhase(0);
      
      // 1秒后进入阶段1
      timerRef.current = setTimeout(() => {
        setPhase(1);
        
        // 再1秒后进入阶段2
        timerRef.current = setTimeout(() => {
          setPhase(2);
        }, 1000);
      }, 1000);
    } else {
      // loading 结束，清理计时器
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setPhase(0);
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isLoading]);

  return phase;
};

const getMessageText = (message: Message): string => {
  if (message.content) return message.content;
  if (message.blocks) {
    return message.blocks
      .filter(b => b.type === 'text')
      .map(b => (b as any).content)
      .join('\n');
  }
  return '';
};

const CopyButton = ({ text }: { text: string }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="mt-1 p-1 rounded-md hover:bg-white text-gray-400 hover:text-gray-600 border border-gray-200 transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
      title="复制内容"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
};

export const MessageList: React.FC<MessageListProps> = ({ 
  messages, 
  isLoading,
  syncProgress,
  onCancelSync,
  deleteConfirmation,
  onConfirmDelete,
  onCancelDeleteConfirm,
  onAskUserSettle,
}) => {
  const { t } = useTranslation();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const loadingPhase = useLoadingPhase(isLoading);
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null);

  const lastMessage = messages[messages.length - 1];
  const waitingForUserChoice = hasPendingAskUserBlock(lastMessage);

  // 根据阶段获取提示文案（ask_user 待答时固定为「等待用户选择」，避免误显示「规划下一步」）
  const getLoadingText = () => {
    if (waitingForUserChoice) {
      return t('workspace.chat.waitingForUserChoice');
    }
    switch (loadingPhase) {
      case 0:
        return t('workspace.chat.loadingWorkflow');
      case 1:
        return t('workspace.chat.thinking');
      case 2:
      default:
        return t('workspace.chat.planningNextMove');
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const hideBottomLoader =
    lastMessage?.role === 'assistant' && shouldHideLoader(lastMessage);
  const isLoaderVisible = isLoading && !hideBottomLoader;

  return (
    <div className="flex flex-col gap-2 px-4 py-4 pb-2 max-w-5xl mx-auto w-full">
      {messages.map((message) => {
        const isUser = message.role === 'user';
        const useV2 = isV2Message(message);
        
        // 跳过空的 assistant 消息（blocks 为空且没有旧格式内容）
        // 这样 loading 圈不会因为空消息容器而下移
        const isEmpty = !isUser && 
          (!message.blocks || message.blocks.length === 0) && 
          !message.content?.trim();
        if (isEmpty) return null;

        return (
          <div
            key={message.id}
            className={`group flex flex-col animate-in fade-in slide-in-from-bottom-4 duration-500 min-w-0 ${
              isUser ? 'items-end' : 'items-start'
            }`}
          >
            <div
              className={`text-app-base leading-relaxed break-words overflow-hidden ${
                isUser
                  ? 'relative flex flex-col px-3 py-2 bg-black/[0.04] text-[#1A1A1A] rounded-lg max-w-full selection:bg-gray-300 selection:text-black'
                  : 'px-3 py-0 text-[#1A1A1A] w-full'
              }`}
            >
              {/* 用户消息附加图片显示 */}
              {isUser && message.attachedImages && message.attachedImages.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-1.5">
                  {message.attachedImages.map((img) => {
                    const src = img.url || img.base64 || '';
                    return (
                      <div
                        key={img.id}
                        className="relative w-32 h-32 rounded-md overflow-hidden border border-gray-200 bg-gray-50 cursor-pointer"
                        onDoubleClick={() => setPreviewImage({ src, alt: img.name })}
                      >
                        <img
                          src={src}
                          alt={img.name}
                          className="w-full h-full object-cover"
                          draggable={false}
                        />
                      </div>
                    );
                  })}
                </div>
              )}
              {/* 用户消息附加文件显示 */}
              {isUser && message.attachedFiles && message.attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-1.5">
                  {message.attachedFiles.map((file) => (
                    <div
                      key={file.id}
                      className="inline-flex items-center gap-1.5 px-2 py-1 bg-orange-50/80 border border-orange-200/60 rounded-md text-xs text-orange-900"
                    >
                      {file.type === 'folder' ? (
                        <Folder className="w-3 h-3 flex-shrink-0 text-orange-700" />
                      ) : (
                        <File className="w-3 h-3 flex-shrink-0 text-orange-700" />
                      )}
                      <span className="max-w-[200px] truncate font-medium">{file.name}</span>
                    </div>
                  ))}
                </div>
              )}
              {useV2 ? (
                <V2MessageRenderer
                  message={message}
                  isUser={isUser}
                  onAskUserSettle={onAskUserSettle}
                />
              ) : (
                <LegacyMessageRenderer message={message} isUser={isUser} />
              )}
            </div>

            {isUser && <CopyButton text={getMessageText(message)} />}

            {message.details?.patched_files && (
              <div className="flex items-center gap-1.5 ml-1 text-app-xs font-medium text-orange-700/60 bg-orange-50/50 px-2.5 py-1 border border-orange-100/50">
                <Terminal className="w-3 h-3" />
                <span>已更新 {message.details.patched_files.length} 个文件</span>
              </div>
            )}
          </div>
        );
      })}

      {/* 文件同步进度（在 loading 区域显示） */}
      {syncProgress && (
        <div className="px-3 py-2">
          <SyncProgressCard 
            info={syncProgress} 
            onCancel={onCancelSync}
          />
        </div>
      )}

      {/* 文件删除确认卡片 */}
      {deleteConfirmation && onConfirmDelete && onCancelDeleteConfirm && (
        <div className="px-3 py-2">
          <DeleteConfirmationCard
            deletedFiles={deleteConfirmation.deletedFiles}
            onConfirm={onConfirmDelete}
            onCancel={onCancelDeleteConfirm}
          />
        </div>
      )}

      {/* Loading 占位符 - 仅在没有同步进度且没有删除确认时显示 */}
      {isLoaderVisible && !syncProgress && !deleteConfirmation && (
        <div className="px-3">
          <div className="flex items-center gap-1.5 py-1">
            <div className="flex-shrink-0 w-4 h-4 flex items-center justify-center">
              <LoadingSpinner size="md" />
            </div>
            <span className="text-[13px] font-medium text-gray-700">
              <WaveText
                key={waitingForUserChoice ? 'waiting-user-choice' : loadingPhase}
                text={getLoadingText()}
              />
            </span>
          </div>
        </div>
      )}
      <div ref={messagesEndRef} className="h-4" />

      {/* 图片预览弹窗 */}
      {previewImage && (
        <ImagePreviewModal
          src={previewImage.src}
          alt={previewImage.alt}
          onClose={() => setPreviewImage(null)}
        />
      )}
    </div>
  );
};
