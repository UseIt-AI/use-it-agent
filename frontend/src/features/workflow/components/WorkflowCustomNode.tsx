import React, { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, useEffect } from 'react';
import { Handle, Position, NodeProps, NodeResizer, useUpdateNodeInternals } from 'reactflow';
import clsx from 'clsx';
import { FileText, FolderOpen, Globe, Search } from 'lucide-react';
import { BlockIcon } from './block-icon';
import { NODE_CONFIGS, type NodeData, type NodeType } from '../types';

function WorkflowCustomNode({ id, data, selected, dragging }: NodeProps<NodeData>) {
  const updateNodeInternals = useUpdateNodeInternals();
  const { type, title } = data;
  const config = NODE_CONFIGS[type];
  const [isHovered, setIsHovered] = useState(false);
  
  // 是否是拖拽的目标 Loop（高亮状态）
  const isDropTarget = (data as any)?.isDropTarget === true;

  if (!config) {
    return (
      <div className="min-w-[150px] p-4 bg-red-50 border border-red-200 rounded-md shadow-sm">
        <div className="text-sm font-medium text-red-800">Unknown Node Type</div>
        <div className="text-xs text-red-600 mt-1">Type "{type}" not found in config</div>
      </div>
    );
  }
  
  // 简易判断：是否只显示 Header（类似 Start / End 这种小节点）
  // 后续如果 End 节点要显示 outputs，可以把 end 移出
  const isMinimal = type === 'start' || type === 'end' || type === 'loop-start' || type === 'loop-end';
  const isLoop = type === 'loop';
  // loop-start 和 loop-end 节点不可拖拽，位置固定
  const isLoopChild = type === 'loop-start' || type === 'loop-end';
  const isIfElse = type === 'if-else';
  
  // 节点主色调（用于 Header 左侧指示条或图标颜色）
  // 截图里是深色背景，所以这里可以用 color 来做图标色
  const accentColor = config.color;
  const llmTools: string[] = type === 'tool-use' ? ((data as any)?.tools || []) : [];
  const nodeSkills: string[] = Array.isArray((data as any)?.skills) ? (data as any).skills : [];
  const mcpSrc = `${import.meta.env.BASE_URL}node/mcp.svg`;
  const nanoBananaSrc = `${import.meta.env.BASE_URL}node/nano-banana.svg`;

  const renderReadOnlyToolChip = (toolValue: string) => {
    const label =
      toolValue === 'web_search' ? 'Web Search' : 
      toolValue === 'file_search' ? 'RAG' : 
      toolValue === 'mcp' ? 'MCP' : 
      toolValue === 'nano_banana' ? 'Nano Banana' : 
      toolValue === 'file_system' ? 'File System' :
      toolValue === 'doc_extract' ? 'Docling' :
      toolValue;
    const icon =
      toolValue === 'web_search' ? (
        <Globe className="w-3.5 h-3.5" />
      ) : toolValue === 'file_search' ? (
        <Search className="w-3.5 h-3.5" />
      ) : toolValue === 'mcp' ? (
        <img src={mcpSrc} alt="MCP" className="w-3.5 h-3.5 object-contain" />
      ) : toolValue === 'nano_banana' ? (
        <img src={nanoBananaSrc} alt="Nano Banana" className="w-3.5 h-3.5 object-contain" />
      ) : toolValue === 'file_system' ? (
        <FolderOpen className="w-3.5 h-3.5" />
      ) : toolValue === 'doc_extract' ? (
        <FileText className="w-3.5 h-3.5" />
      ) : null;

    return (
      <div
        key={toolValue}
        className="inline-flex items-center gap-1 bg-black/5 border border-divider/50 rounded-full px-2 py-1 text-[11px] text-black/70"
        title={label}
      >
        <span className="w-3.5 h-3.5 flex items-center justify-center text-black/60 flex-shrink-0">{icon}</span>
        <span className="truncate max-w-[140px]">{label}</span>
      </div>
    );
  };

  const renderMcpChip = () => {
    const mcpServer = ((data as any)?.mcp_server_name || '').trim();
    if (!mcpServer) return null;
    return (
      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold text-black/40 uppercase tracking-wider">MCP</span>
        <div className="flex flex-wrap gap-1">
          <div
            className="inline-flex items-center gap-1 bg-black/5 border border-divider/50 rounded-full px-2 py-1 text-[11px] text-black/70"
            title={mcpServer}
          >
            <span className="w-3.5 h-3.5 flex items-center justify-center text-black/60 flex-shrink-0">
              <img src={mcpSrc} alt="MCP" className="w-3.5 h-3.5 object-contain" />
            </span>
            <span className="truncate max-w-[180px]">{mcpServer}</span>
          </div>
        </div>
      </div>
    );
  };

  /**
   * 从 S3 key 中提取 skill 名称
   * S3 key 格式: skills/{user_id}/{skill_name}
   */
  const extractSkillNameFromS3Key = (s3Key: string): string => {
    const parts = s3Key.split('/');
    // 返回最后一部分作为 skill 名称
    return parts[parts.length - 1] || s3Key;
  };

  const renderSkillChip = (skillS3Key: string) => {
    const displayName = extractSkillNameFromS3Key(skillS3Key);
    return (
      <div
        key={skillS3Key}
        className="inline-flex items-center gap-1 bg-black/5 border border-divider/50 rounded-full px-2 py-1 text-[11px] text-black/70"
        title={skillS3Key}
      >
        <span className="truncate max-w-[140px]">{displayName}</span>
      </div>
    );
  };

  // If/Else: 用于获取节点和 body 的高度，计算 handle 位置
  const nodeWrapperRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [bodyHeight, setBodyHeight] = useState(0);

  const conditions = useMemo(() => {
    const c = (data as any)?.conditions;
    if (Array.isArray(c) && c.length) return c as Array<{ label?: string; expression?: string }>;
    // fallback: at least one If
    return [{ label: 'if', expression: '' }];
  }, [data]);

  // handle 总数 = conditions 数量 + 1 (else)
  const handleCount = conditions.length + 1;

  // 监听 body 高度变化
  useLayoutEffect(() => {
    if (!isIfElse || !bodyRef.current) return;

    const updateHeight = () => {
      if (bodyRef.current) {
        setBodyHeight(bodyRef.current.offsetHeight);
      }
    };

    updateHeight();

    const ro = new ResizeObserver(updateHeight);
    ro.observe(bodyRef.current);

    return () => ro.disconnect();
  }, [isIfElse, conditions.length]);

  // 当 body 高度变化后，通知 ReactFlow 更新内部状态
  useEffect(() => {
    if (!isIfElse || bodyHeight === 0) return;
    updateNodeInternals(id);
  }, [isIfElse, id, bodyHeight, updateNodeInternals]);

  return (
    <>
      {/* NodeResizer - 只对 Loop 节点启用 */}
      {isLoop && (
        <NodeResizer 
          minWidth={400} 
          minHeight={200} 
          isVisible={selected || isHovered}
          lineClassName="!border-orange-500/50" 
          handleClassName="!h-5 !w-5 !bg-white !border-2 !border-orange-500 !rounded-sm"
        />
      )}
      
      <div
        ref={nodeWrapperRef}
        className={clsx(
          'group flex flex-col bg-canvas border rounded-lg transition-all duration-200',
          isLoopChild && 'w-fit', // Loop Start/End 宽度自适应
          isLoopChild && 'cursor-default', // Loop Start/End 不可拖拽，显示默认光标
          !isLoop && !isLoopChild && 'min-w-[240px]', // 其他节点保持最小宽度
          // Loop 节点拖拽高亮（柔和的橙色调）
          isLoop && isDropTarget && 'border-orange-400/50 border-2',
          // 普通选中状态
          !isDropTarget && selected 
            ? 'border-orange-500/50 shadow-[0_0_0_1px_rgba(249,115,22,0.5)]' 
            : !isDropTarget && 'border-divider shadow-sm hover:border-divider/80'
        )}
        style={
          isLoop
            ? {
                width: '100%',
                height: '100%',
                background: isDropTarget ? 'rgba(251, 146, 60, 0.05)' : 'rgba(0, 0, 0, 0.1)',
                backdropFilter: 'blur(4px)',
                transition: 'background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
              }
            : !isLoopChild
              ? { width: config.defaultWidth }
              : undefined
        }
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >

      {/* Header */}
      <div className={clsx(
        "flex items-center gap-2 px-3 py-2 bg-canvas-sub border-b border-divider/50",
        isMinimal ? "rounded-lg border-none" : "rounded-t-lg",
        isLoop && "bg-transparent border-none"
      )}>
        <div className="flex items-center justify-center w-6 h-6 rounded-md bg-canvas border border-divider flex-shrink-0">
          <BlockIcon 
            type={type} 
            className="w-3.5 h-3.5" 
            actionType={type === 'computer-use' ? (data as any).action_type : undefined}
          />
        </div>
        <span className="text-xs font-bold text-black/90 uppercase tracking-wide whitespace-nowrap truncate">
          {title || config.defaultTitle}
        </span>
      </div>

      {/* Body Content */}
      {!isMinimal && !isLoop && !isIfElse && (
        <div className="p-3 flex flex-col gap-3">
          {/* 这里根据不同节点类型渲染不同内容 */}
          {/* 暂时以 Computer Use 为例，展示占位内容 */}
          
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold text-black/40 uppercase tracking-wider">
              Instruction
            </span>
            <div className="text-xs text-black/70 line-clamp-2">
              {(data as any).instruction || 'No instruction provided'}
            </div>
          </div>

          {/* 模拟截图区域 (Computer Use) */}
        {type === 'computer-use' && (data as any).cover_img && (
            <div className="w-full bg-black/5 rounded border border-divider overflow-hidden">
              <img
                src={(data as any).cover_img}
                alt="Preview"
                className="block w-full h-auto"
                loading="lazy"
                decoding="async"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  e.currentTarget.parentElement?.classList.add('image-load-error');
                }}
              />
            </div>
        )}

        {/* Skills (read-only): show when skills exist, placed above Tools */}
        {nodeSkills.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold text-black/40 uppercase tracking-wider">Skills</span>
            <div className="flex flex-wrap gap-1">{nodeSkills.map((skill) => renderSkillChip(skill))}</div>
          </div>
        )}

        {/* LLM Tools (read-only): only show when tools exist */}
        {type === 'tool-use' && llmTools.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold text-black/40 uppercase tracking-wider">Tools</span>
            <div className="flex flex-wrap gap-1">{llmTools.map((t) => renderReadOnlyToolChip(t))}</div>
          </div>
        )}

        {/* MCP selection (read-only): only show when server exists */}
        {type === 'mcp-use' && renderMcpChip()}
        </div>
    )}

      {/* If/Else custom body (structure only, keep global style) */}
      {isIfElse && (
        <div ref={bodyRef} className="p-3 flex flex-col gap-3">
          {conditions.map((cnd, idx) => {
            // 使用稳定的 key：基于 idx 和 expression 的组合，避免重复
            const stableKey = `condition-${idx}`;
            return (
              <div key={stableKey} className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold text-black/40 uppercase tracking-wider">
                  {idx === 0 ? 'If condition' : 'Else if condition'}
                </span>
                <div className="h-9 rounded-md bg-black/5 border border-divider/50 flex items-center px-2">
                  <span className="text-[11px] text-black/50 truncate">
                    {(cnd?.expression || '').trim() || '—'}
                  </span>
                </div>
              </div>
            );
          })}

          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold text-black/40 uppercase tracking-wider">
              Else condition
            </span>
            <div className="h-9 rounded-md bg-black/5 border border-divider/50 flex items-center justify-center">
              <span className="text-[12px] font-medium text-black/40">Else</span>
            </div>
          </div>
        </div>
      )}

      </div>

      {/* Handles - 必须放在容器 div 外部，与其同级 */}
      {/* 
        Handle 位置策略：
        - if-else 节点：handle 位置动态计算，与对应条件框对齐
        - 其他节点：handle 固定在 title 区域的垂直中心（约 20px，即 header 高度 40px 的一半）
        这样可以避免连接线过于混乱
      */}
      {/* Left Input */}
      {type !== 'start' && type !== 'loop-start' && (
        <Handle
          type="target"
          position={Position.Left}
          style={!isIfElse ? { top: 20 } : undefined}
        />
      )}
    
      {/* Right Output - 非 if-else 节点 */}
      {type !== 'end' && type !== 'loop-end' && !isIfElse && (
        <Handle
          type="source"
          position={Position.Right}
          style={{ top: 20 }}
        />
      )}

      {/* If/Else Right Outputs - 在 body 区域均匀分布 */}
      {/* 
        Handle ID 命名规则：
        - 第一个条件 (idx=0): 'if'
        - 后续条件 (idx=1,2,...): 'elseif-1', 'elseif-2', ...
        - Else 分支: 'else'
        
        简化布局：所有 handle 在 body 区域（header 下方）均匀垂直分布
        - Header 高度: 40px
        - Body 高度: bodyHeight (动态获取)
        - 每个 handle 位置: header + body 中的均匀分布位置
      */}
      {isIfElse && conditions.map((_, idx) => {
        const handleId = idx === 0 ? 'if' : `elseif-${idx}`;
        // 在 body 区域均匀分布：header(40) + body 内的位置
        // 将 body 分成 handleCount+1 份，每个 handle 在第 (idx+1) 份的位置
        const headerHeight = 40;
        const spacing = bodyHeight / (handleCount + 1);
        const top = headerHeight + spacing * (idx + 1);
        return (
          <Handle
            key={handleId}
            id={handleId}
            type="source"
            position={Position.Right}
            style={{ top }}
          />
        );
      })}
      {isIfElse && (
        <Handle
          id="else"
          type="source"
          position={Position.Right}
          style={{
            // else 是最后一个 handle
            top: 40 + (bodyHeight / (handleCount + 1)) * handleCount,
          }}
        />
      )}
    </>
  );
}

export default memo(WorkflowCustomNode);

