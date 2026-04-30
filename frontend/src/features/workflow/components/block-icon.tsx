import React from 'react';
import {
  Split,
  Globe,
  PanelTop,
  Infinity,
  Monitor,
  MousePointer2,
  MousePointerClick,
  Search,
  Sparkles,
  UserCheck,
  Code,
  Zap,
  ZapOff,
  Orbit,
} from 'lucide-react';

import type { NodeType, ComputerUseActionType } from '../types';

// SVG icon component using mask for currentColor support (for custom SVGs like MCP)
function SvgMaskIcon({ name, className }: { name: string; className?: string }) {
  return (
    <span
      className={className}
      style={{
        display: 'inline-block',
        backgroundColor: 'currentColor',
        WebkitMaskImage: `url(${import.meta.env.BASE_URL}node/${name}.svg)`,
        WebkitMaskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        WebkitMaskSize: 'contain',
        maskImage: `url(${import.meta.env.BASE_URL}node/${name}.svg)`,
        maskRepeat: 'no-repeat',
        maskPosition: 'center',
        maskSize: 'contain',
      }}
    />
  );
}

// Software logo icon component (colored)
function SoftwareLogo({ name, className }: { name: string; className?: string }) {
  const src = `${import.meta.env.BASE_URL}node/${name}.svg`;
  return <img src={src} alt={name} className={className} style={{ objectFit: 'contain' }} />;
}

export interface BlockIconProps {
  type: NodeType;
  className?: string;
  /** For computer-use nodes, specify the action type to show different icons */
  actionType?: ComputerUseActionType;
}

/** Get icon for computer-use based on action type */
function getComputerUseIcon(actionType: ComputerUseActionType | undefined, className: string): React.ReactNode {
  switch (actionType) {
    case 'autocad':
      return <SoftwareLogo name="autocad" className={className} />;
    case 'excel':
      return <SoftwareLogo name="excel" className={className} />;
    case 'word':
      return <SoftwareLogo name="word" className={className} />;
    case 'ppt':
      return <SoftwareLogo name="ppt" className={className} />;
    case 'gui':
    default:
      return <MousePointer2 className={className} />;
  }
}

export function getIcon(type: NodeType, className = 'w-4 h-4', actionType?: ComputerUseActionType): React.ReactNode {
  switch (type) {
    case 'start':
      return <Zap className={className} />;
    case 'end':
      return <ZapOff className={className} />;
    case 'tool-use':
      return <Sparkles className={className} />;
    case 'computer-use':
      return getComputerUseIcon(actionType, className);
    case 'browser-use':
      return <PanelTop className={className} />;
    case 'human-in-the-loop':
      return <UserCheck className={className} />;
    case 'code-use':
      return <Code className={className} />;
    case 'mcp-use':
      return <SvgMaskIcon name="mcp" className={className} />;
    case 'agent':
      return <Orbit className={className} />;
    case 'loop':
      return <Infinity className={className} />;
    case 'loop-start':
      return <Zap className={className} />;
    case 'loop-end':
      return <ZapOff className={className} />;
    case 'if-else':
      return <Split className={className} />;
    default:
      // fallback，避免 UI 崩溃
      return <Monitor className={className} />;
  }
}

export function BlockIcon({ type, className = 'w-4 h-4', actionType }: BlockIconProps) {
  return <>{getIcon(type, className, actionType)}</>;
}


