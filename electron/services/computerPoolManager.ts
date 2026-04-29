/**
 * 电脑池管理器
 * 整合配置解析、状态管理、状态检测
 */

import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { app, shell } from 'electron';
import { exec } from 'child_process';
import { promisify } from 'util';

import type {
  ComputerConfig,
  ComputerWithStatus,
  ComputerPool,
  ComputerPoolState,
  ComputerStatus,
  SessionBinding,
} from '../../src/types/computer';
import { THIS_PC_CONFIG, DEFAULT_PORTS } from '../../src/types/computer';
import { parseComputersConfig, serializeComputersConfig, generateExampleConfig } from './computerConfigParser';
import { ComputerStateManager } from './computerStateManager';

const execAsync = promisify(exec);

// 配置目录和文件名
const CONFIG_DIR_NAME = '.useit';
const CONFIG_FILE_NAME = 'computers';

export class ComputerPoolManager {
  private configDir: string;
  private configFilePath: string;
  private stateManager: ComputerStateManager;
  private computers: ComputerConfig[] = [];
  private statusCache: Map<string, { status: ComputerStatus; resolvedHost?: string; timestamp: number }> = new Map();
  private statusCacheTTL = 30000; // 30 seconds

  constructor() {
    // 配置目录: %USERPROFILE%\.useit (Windows) 或 ~/.useit (Unix)
    this.configDir = path.join(os.homedir(), CONFIG_DIR_NAME);
    this.configFilePath = path.join(this.configDir, CONFIG_FILE_NAME);

    // 确保配置目录存在
    this.ensureConfigDir();

    // 初始化状态管理器
    this.stateManager = new ComputerStateManager(this.configDir);

    // 加载配置
    this.loadConfig();

    console.log('[ComputerPoolManager] Initialized');
    console.log('[ComputerPoolManager] Config dir:', this.configDir);
    console.log('[ComputerPoolManager] Computers loaded:', this.computers.length);
  }

  /**
   * 确保配置目录存在
   */
  private ensureConfigDir(): void {
    if (!fs.existsSync(this.configDir)) {
      fs.mkdirSync(this.configDir, { recursive: true });
      console.log('[ComputerPoolManager] Created config dir:', this.configDir);
    }
  }

  /**
   * 加载配置文件
   */
  private loadConfig(): void {
    try {
      if (fs.existsSync(this.configFilePath)) {
        const content = fs.readFileSync(this.configFilePath, 'utf-8');
        this.computers = parseComputersConfig(content);
        console.log('[ComputerPoolManager] Loaded', this.computers.length, 'computers from config');
      } else {
        // 创建示例配置文件
        this.createExampleConfig();
        this.computers = [];
      }
    } catch (e) {
      console.error('[ComputerPoolManager] Failed to load config:', e);
      this.computers = [];
    }
  }

  /**
   * 创建示例配置文件
   */
  private createExampleConfig(): void {
    try {
      const exampleContent = generateExampleConfig();
      fs.writeFileSync(this.configFilePath, exampleContent, 'utf-8');
      console.log('[ComputerPoolManager] Created example config file');
    } catch (e) {
      console.error('[ComputerPoolManager] Failed to create example config:', e);
    }
  }

  /**
   * 重新加载配置
   */
  reloadConfig(): void {
    this.loadConfig();
    this.statusCache.clear();
  }

  /**
   * 获取所有电脑（包含 This PC）
   */
  getAllComputers(): ComputerConfig[] {
    return [THIS_PC_CONFIG, ...this.computers];
  }

  /**
   * 获取电脑配置
   */
  getComputer(name: string): ComputerConfig | null {
    if (name === 'This PC') {
      return THIS_PC_CONFIG;
    }
    return this.computers.find((c) => c.name === name) || null;
  }

  /**
   * 检查电脑状态
   */
  async checkComputerStatus(name: string): Promise<{ status: ComputerStatus; resolvedHost?: string }> {
    // 检查缓存
    const cached = this.statusCache.get(name);
    if (cached && Date.now() - cached.timestamp < this.statusCacheTTL) {
      return { status: cached.status, resolvedHost: cached.resolvedHost };
    }

    const computer = this.getComputer(name);
    if (!computer) {
      return { status: 'offline' };
    }

    let status: ComputerStatus = 'offline';
    let resolvedHost: string | undefined;

    try {
      // This PC 始终在线
      if (computer.type === 'thispc') {
        status = 'online';
        resolvedHost = 'localhost';
      }
      // VM 类型：需要获取 IP
      else if (computer.type === 'vm' && computer.host === 'auto') {
        const vmIp = await this.getVmIp(computer.vmName!);
        if (vmIp) {
          resolvedHost = vmIp;
          const isOnline = await this.pingLocalEngine(resolvedHost, computer.localEnginePort);
          status = isOnline ? 'online' : 'offline';
        }
      }
      // 其他类型：直接检查
      else {
        resolvedHost = computer.host;
        const isOnline = await this.pingLocalEngine(computer.host, computer.localEnginePort);
        status = isOnline ? 'online' : 'offline';
      }

      // 检查是否被占用
      if (status === 'online' && this.stateManager.isComputerOccupied(name)) {
        status = 'busy';
      }
    } catch (e) {
      console.error(`[ComputerPoolManager] Failed to check status for ${name}:`, e);
      status = 'offline';
    }

    // 更新缓存
    this.statusCache.set(name, { status, resolvedHost, timestamp: Date.now() });

    return { status, resolvedHost };
  }

  /**
   * 获取 VM IP 地址
   */
  private async getVmIp(vmName: string): Promise<string | null> {
    try {
      const script = `(Get-VM -Name '${vmName}' | Get-VMNetworkAdapter).IPAddresses | Where-Object { $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' } | Select-Object -First 1`;
      const { stdout } = await execAsync(`powershell -Command "${script}"`);
      const ip = stdout.trim();
      return ip || null;
    } catch (e) {
      console.error(`[ComputerPoolManager] Failed to get VM IP for ${vmName}:`, e);
      return null;
    }
  }

  /**
   * Ping Local Engine 检查是否在线
   */
  private async pingLocalEngine(host: string, port: number): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(`http://${host}:${port}/health`, {
        signal: controller.signal,
      });

      clearTimeout(timeout);
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * 获取电脑池（包含状态）
   */
  async getComputerPool(): Promise<ComputerPool> {
    const allComputers = this.getAllComputers();
    const computersWithStatus: ComputerWithStatus[] = [];

    for (const computer of allComputers) {
      const { status, resolvedHost } = await this.checkComputerStatus(computer.name);
      const occupiedBy = this.stateManager.getOccupyingSession(computer.name);

      computersWithStatus.push({
        ...computer,
        status,
        resolvedHost,
        occupiedBy: occupiedBy || undefined,
      });
    }

    return {
      computers: computersWithStatus,
      state: this.stateManager.getState(),
    };
  }

  /**
   * 获取电脑的 Local Engine URL
   */
  async getLocalEngineUrl(name: string): Promise<string | null> {
    const computer = this.getComputer(name);
    if (!computer) {
      return null;
    }

    let host = computer.host;

    // 如果是 auto，需要解析
    if (host === 'auto' && computer.type === 'vm') {
      const { resolvedHost } = await this.checkComputerStatus(name);
      if (!resolvedHost) {
        return null;
      }
      host = resolvedHost;
    }

    return `http://${host}:${computer.localEnginePort}`;
  }

  // ==================== 状态管理委托 ====================

  getLastUsedComputer(): string {
    return this.stateManager.getLastUsedComputer();
  }

  setLastUsedComputer(name: string): void {
    this.stateManager.setLastUsedComputer(name);
  }

  bindSession(chatId: string, computerName: string): void {
    this.stateManager.bindSession(chatId, computerName);
    // 清除状态缓存，因为占用状态变了
    this.statusCache.delete(computerName);
  }

  unbindSession(chatId: string): void {
    const computer = this.stateManager.getSessionComputer(chatId);
    this.stateManager.unbindSession(chatId);
    // 清除状态缓存
    if (computer) {
      this.statusCache.delete(computer);
    }
  }

  getSessionComputer(chatId: string): string | null {
    return this.stateManager.getSessionComputer(chatId);
  }

  getSessionBinding(chatId: string): SessionBinding | null {
    return this.stateManager.getSessionBinding(chatId);
  }

  isComputerOccupied(computerName: string): boolean {
    return this.stateManager.isComputerOccupied(computerName);
  }

  getOccupyingSession(computerName: string): string | null {
    return this.stateManager.getOccupyingSession(computerName);
  }

  addToQueue(chatId: string, computerName: string): number {
    return this.stateManager.addToQueue(chatId, computerName);
  }

  removeFromQueue(chatId: string): void {
    this.stateManager.removeFromQueue(chatId);
  }

  getQueuePosition(chatId: string, computerName: string): number {
    return this.stateManager.getQueuePosition(chatId, computerName);
  }

  getComputerQueue(computerName: string): string[] {
    return this.stateManager.getComputerQueue(computerName);
  }

  // ==================== 配置文件操作 ====================

  /**
   * 打开配置文件（用系统默认编辑器）
   */
  openConfigFile(): void {
    // 确保配置文件存在
    if (!fs.existsSync(this.configFilePath)) {
      this.createExampleConfig();
    }
    shell.openPath(this.configFilePath);
  }

  /**
   * 获取配置文件路径
   */
  getConfigFilePath(): string {
    return this.configFilePath;
  }

  /**
   * 添加电脑配置
   */
  addComputer(config: ComputerConfig): void {
    // 检查是否已存在
    const existing = this.computers.findIndex((c) => c.name === config.name);
    if (existing !== -1) {
      this.computers[existing] = config;
    } else {
      this.computers.push(config);
    }

    // 保存配置
    this.saveConfig();
  }

  /**
   * 删除电脑配置
   */
  removeComputer(name: string): void {
    this.computers = this.computers.filter((c) => c.name !== name);
    this.saveConfig();
    this.statusCache.delete(name);
  }

  /**
   * 保存配置到文件
   */
  private saveConfig(): void {
    try {
      const content = serializeComputersConfig(this.computers);
      fs.writeFileSync(this.configFilePath, content, 'utf-8');
      console.log('[ComputerPoolManager] Config saved');
    } catch (e) {
      console.error('[ComputerPoolManager] Failed to save config:', e);
    }
  }
}

// 单例
let instance: ComputerPoolManager | null = null;

export function getComputerPoolManager(): ComputerPoolManager {
  if (!instance) {
    instance = new ComputerPoolManager();
  }
  return instance;
}

