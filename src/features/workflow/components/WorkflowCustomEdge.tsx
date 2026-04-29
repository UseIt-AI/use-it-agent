import React, { useState } from 'react';
import { EdgeProps, getBezierPath, MarkerType } from 'reactflow';

/**
 * 自定义 Edge 组件 - 在连线与 Handle 之间留出间隙，使用贝塞尔曲线
 * 支持 hover 和 selected 状态的视觉反馈
 */
export default function WorkflowCustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  selected,
}: EdgeProps) {
  const [isHovered, setIsHovered] = useState(false);

  // Handle 半径 + 间隙
  const sourceOffset = 10; // 源端偏移（Handle 半径 6px + 间隙 4px）
  const targetOffset = 10; // 目标端偏移

  // 根据 position 方向调整坐标
  let adjustedSourceX = sourceX;
  let adjustedSourceY = sourceY;
  let adjustedTargetX = targetX;
  let adjustedTargetY = targetY;

  // 源端偏移
  switch (sourcePosition) {
    case 'right':
      adjustedSourceX = sourceX + sourceOffset;
      break;
    case 'left':
      adjustedSourceX = sourceX - sourceOffset;
      break;
    case 'top':
      adjustedSourceY = sourceY - sourceOffset;
      break;
    case 'bottom':
      adjustedSourceY = sourceY + sourceOffset;
      break;
  }

  // 目标端偏移
  switch (targetPosition) {
    case 'right':
      adjustedTargetX = targetX + targetOffset;
      break;
    case 'left':
      adjustedTargetX = targetX - targetOffset;
      break;
    case 'top':
      adjustedTargetY = targetY - targetOffset;
      break;
    case 'bottom':
      adjustedTargetY = targetY + targetOffset;
      break;
  }

  const [edgePath] = getBezierPath({
    sourceX: adjustedSourceX,
    sourceY: adjustedSourceY,
    sourcePosition,
    targetX: adjustedTargetX,
    targetY: adjustedTargetY,
    targetPosition,
  });

  // 动态样式
  const isActive = selected || isHovered;
  const strokeColor = '#94a3b8'; // 保持一致的灰色
  const strokeWidth = isActive ? 2.5 : 1.5;

  // 生成唯一的 marker ID
  const markerId = `arrow-${id}`;

  return (
    <>
      {/* 定义箭头 marker */}
      <defs>
        <marker
          id={markerId}
          markerWidth="12"
          markerHeight="12"
          refX="10"
          refY="6"
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <path
            d="M2,2 L10,6 L2,10 L4,6 Z"
            fill={strokeColor}
          />
        </marker>
      </defs>

      {/* 透明的宽路径用于更容易的鼠标交互 */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className="react-flow__edge-interaction"
      />
      
      {/* 实际可见的边 */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        markerEnd={`url(#${markerId})`}
        style={{
          transition: 'stroke-width 0.2s ease',
        }}
        className="react-flow__edge-path"
      />
    </>
  );
}
