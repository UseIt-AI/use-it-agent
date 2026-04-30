/**
 * 电脑状态管理器
 * 管理 Session 绑定、队列等运行时状态
 * 状态持久化到本地文件
 */

import * as fs from 'fs';
import * as path from 'path';
import { app } from 'electron';
import type { ComputerPoolState, SessionBinding } from '../../src/types/computer';

// 状态文件名
const STATE_FILE_NAME = 'state.json';

// 默认状态
const DEFAULT_STATE: ComputerPoolState = {
  lastUsedComputer: 'This PC',
  sessions: {},
  queue: {},
};

export class ComputerStateManager {
  private state: ComputerPoolState;
  private stateFilePath: string;
  private saveDebounceTimer: NodeJS.Timeout | null = null;

  constructor(configDir: string) {
    this.stateFilePath = path.join(configDir, STATE_FILE_NAME);
    this.state = this.loadState();
  }

  /**
   * 加载状态文件
   */
  private loadState(): ComputerPoolState {
    try {
      if (fs.existsSync(this.stateFilePath)) {
        const content = fs.readFileSync(this.stateFilePath, 'utf-8');
        const parsed = JSON.parse(content);
        return {
          ...DEFAULT_STATE,
          ...parsed,
        };
      }
    } catch (e) {
      console.error('[ComputerStateManager] Failed to load state:', e);
    }
    return { ...DEFAULT_STATE };
  }

  /**
   * 保存状态文件（防抖）
   */
  private saveState(): void {
    if (this.saveDebounceTimer) {
      clearTimeout(this.saveDebounceTimer);
    }

    this.saveDebounceTimer = setTimeout(() => {
      try {
        const dir = path.dirname(this.stateFilePath);
        if (!fs.existsSync(dir)) {
          fs.mkdirSync(dir, { recursive: true });
        }
        fs.writeFileSync(this.stateFilePath, JSON.stringify(this.state, null, 2), 'utf-8');
        console.log('[ComputerStateManager] State saved');
      } catch (e) {
        console.error('[ComputerStateManager] Failed to save state:', e);
      }
    }, 500);
  }

  /**
   * 获取完整状态
   */
  getState(): ComputerPoolState {
    return { ...this.state };
  }

  /**
   * 获取上次使用的电脑
   */
  getLastUsedComputer(): string {
    return this.state.lastUsedComputer;
  }

  /**
   * 设置上次使用的电脑
   */
  setLastUsedComputer(name: string): void {
    this.state.lastUsedComputer = name;
    this.saveState();
  }

  /**
   * 绑定 Session 到电脑
   */
  bindSession(chatId: string, computerName: string): void {
    // 先解绑旧的
    this.unbindSession(chatId);

    // 绑定新的
    this.state.sessions[chatId] = {
      computer: computerName,
      boundAt: new Date().toISOString(),
      status: 'active',
    };

    // 更新上次使用的电脑
    this.state.lastUsedComputer = computerName;

    // 从队列中移除（如果在队列中）
    this.removeFromQueue(chatId);

    this.saveState();
  }

  /**
   * 解绑 Session
   */
  unbindSession(chatId: string): void {
    if (this.state.sessions[chatId]) {
      delete this.state.sessions[chatId];
      this.saveState();
    }
  }

  /**
   * 获取 Session 绑定的电脑
   */
  getSessionComputer(chatId: string): string | null {
    const binding = this.state.sessions[chatId];
    return binding?.computer || null;
  }

  /**
   * 获取 Session 绑定信息
   */
  getSessionBinding(chatId: string): SessionBinding | null {
    return this.state.sessions[chatId] || null;
  }

  /**
   * 检查电脑是否被占用
   */
  isComputerOccupied(computerName: string): boolean {
    return Object.values(this.state.sessions).some(
      (binding) => binding.computer === computerName && binding.status === 'active'
    );
  }

  /**
   * 获取占用电脑的 Session
   */
  getOccupyingSession(computerName: string): string | null {
    for (const [chatId, binding] of Object.entries(this.state.sessions)) {
      if (binding.computer === computerName && binding.status === 'active') {
        return chatId;
      }
    }
    return null;
  }

  /**
   * 添加到队列
   * @returns 队列位置（从 1 开始）
   */
  addToQueue(chatId: string, computerName: string): number {
    if (!this.state.queue[computerName]) {
      this.state.queue[computerName] = [];
    }

    // 避免重复添加
    if (!this.state.queue[computerName].includes(chatId)) {
      this.state.queue[computerName].push(chatId);
      this.saveState();
    }

    return this.state.queue[computerName].indexOf(chatId) + 1;
  }

  /**
   * 从队列中移除
   */
  removeFromQueue(chatId: string): void {
    let changed = false;
    for (const computerName of Object.keys(this.state.queue)) {
      const index = this.state.queue[computerName].indexOf(chatId);
      if (index !== -1) {
        this.state.queue[computerName].splice(index, 1);
        changed = true;
      }
    }
    if (changed) {
      this.saveState();
    }
  }

  /**
   * 获取队列位置
   * @returns 位置（从 1 开始），0 表示不在队列中
   */
  getQueuePosition(chatId: string, computerName: string): number {
    const queue = this.state.queue[computerName];
    if (!queue) return 0;
    const index = queue.indexOf(chatId);
    return index === -1 ? 0 : index + 1;
  }

  /**
   * 获取电脑的队列
   */
  getComputerQueue(computerName: string): string[] {
    return [...(this.state.queue[computerName] || [])];
  }

  /**
   * 处理队列中的下一个（当电脑空闲时调用）
   * @returns 下一个 chatId，或 null
   */
  processNextInQueue(computerName: string): string | null {
    const queue = this.state.queue[computerName];
    if (!queue || queue.length === 0) {
      return null;
    }

    const nextChatId = queue.shift()!;
    this.saveState();
    return nextChatId;
  }

  /**
   * 清理过期的 Session（超过 24 小时未活动）
   */
  cleanupExpiredSessions(): void {
    const now = new Date().getTime();
    const expireTime = 24 * 60 * 60 * 1000; // 24 hours

    let changed = false;
    for (const [chatId, binding] of Object.entries(this.state.sessions)) {
      const boundTime = new Date(binding.boundAt).getTime();
      if (now - boundTime > expireTime) {
        delete this.state.sessions[chatId];
        changed = true;
      }
    }

    if (changed) {
      this.saveState();
    }
  }

  /**
   * 更新 Session 状态
   */
  updateSessionStatus(chatId: string, status: SessionBinding['status']): void {
    if (this.state.sessions[chatId]) {
      this.state.sessions[chatId].status = status;
      this.saveState();
    }
  }
}



