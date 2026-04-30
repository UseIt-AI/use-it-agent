import React from 'react';
import type { WorkflowNode } from '@/features/workflow';
import type { ControlPanelMode } from '../ControlPanel';
import { NodeDescriptionInput } from './node-details/NodeDescriptionInput';
import { StartNodeDetails } from './node-details/StartNodeDetails';
import { ToolUseNodeDetails } from './node-details/ToolUseNodeDetails';
import { IfElseNodeDetails } from './node-details/IfElseNodeDetails';
import { McpUseNodeDetails } from './node-details/McpUseNodeDetails';
import { ComputerUseNodeDetails } from './node-details/ComputerUseNodeDetails';
import { AgentNodeDetails } from './node-details/AgentNodeDetails';

export function WorkflowNodeDetails({
  node,
  onUpdate,
  panelMode = 'normal',
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
  panelMode?: ControlPanelMode;
}) {
  const renderContent = () => {
    switch (node.data.type) {
      case 'start':
        return <StartNodeDetails />;
      case 'tool-use':
        return <ToolUseNodeDetails node={node} onUpdate={onUpdate} />;
      case 'mcp-use':
        return <McpUseNodeDetails node={node} onUpdate={onUpdate} />;
      case 'computer-use':
        return <ComputerUseNodeDetails node={node} onUpdate={onUpdate} panelMode={panelMode} />;
      case 'agent':
        return <AgentNodeDetails node={node} onUpdate={onUpdate} />;
      case 'if-else':
        return <IfElseNodeDetails node={node} onUpdate={onUpdate} />;
      default:
        return <NodeDescriptionInput node={node} onUpdate={onUpdate} />;
    }
  };

  const isMaximized = panelMode === 'maximized';

  return (
    <div className={`h-full flex flex-col bg-transparent${isMaximized ? ' overflow-hidden' : ' overflow-y-auto'}`}>
      <div className="flex-1 flex flex-col min-h-0 px-3 pt-2 pb-3 gap-3">
        {renderContent()}
      </div>
    </div>
  );
}


