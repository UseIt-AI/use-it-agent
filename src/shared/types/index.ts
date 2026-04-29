/**
 * 共享类型定义
 * Desktop 和 Web 都可以使用
 */

// 项目类型
export type { Project, ProjectFile, FileInfo } from '../../types/project';

// 计算机类型
export type { Computer } from '../../types/computer';

// 消息类型（Chat 相关）
export type { Message, MessageContent } from '../../features/chat/handlers/types';
