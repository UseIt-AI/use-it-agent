/**
 * 共享 Hooks
 * Desktop 和 Web 都可以使用
 */


// Project 相关
export { useProject } from '../../contexts/ProjectContext';
export { useAuth } from '../../contexts/AuthContext';

// Chat 相关（暂时不导出，因为有 Local Engine 依赖）
// export { useChat } from '../../features/chat/hooks/useChat';
