/**
 * Chat 组件统一导出
 */

// 核心组件 (V2 格式)
export { Header } from './Header';
export { ChatInput } from './ChatInput';
export { MessageList } from './MessageList';
export { CardRenderer } from './CardRenderer';
export { CUACard } from './CUACard';
export { NodeCard } from './NodeCard';
export { ChatHistory } from './ChatHistory';
export { ComputerSelector } from './ComputerSelector';
export { ComputerConflictDialog } from './ComputerConflictDialog';
export { AgentDropdown } from './AgentDropdown';

// 统一的状态图标组件
export { 
  StatusIcon, 
  ActionIcon, 
  LoadingSpinner,
  type TaskStatus,
  type ActionType,
  type IconSize,
} from './StatusIcons';

// 同步状态卡片
export {
  SyncProgressCard,
  DeleteConfirmationCard,
  type SyncProgressInfo,
  type DeletedFileInfo,
} from './SyncStatusCard';

// ==================== Deprecated ====================
// 以下组件已废弃，仅用于旧格式消息的向后兼容
// 新代码应使用 CardRenderer 和对应的 V2 卡片组件
export { AgentSelector } from './.deprecated/AgentSelector';
export { ComputerUseStep } from './.deprecated/ComputerUseStep';
export { ToolStepCard } from './.deprecated/ToolStepCard';
export { WorkflowStepCard } from './.deprecated/WorkflowStepCard';

