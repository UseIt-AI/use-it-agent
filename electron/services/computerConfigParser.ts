/**
 * 电脑配置文件解析器
 * 解析类似 SSH config 格式的配置文件
 * 
 * 配置文件格式示例:
 * 
 * Computer VM-Dev
 *     Type vm
 *     VMName UseIt-Dev-VM
 *     Host auto
 *     LocalEnginePort 8324
 *     ...
 */

import type { ComputerConfig, ComputerType } from '../../src/types/computer';
import { DEFAULT_PORTS } from '../../src/types/computer';

// 字段名映射（配置文件字段 -> ComputerConfig 属性）
const FIELD_MAP: Record<string, keyof ComputerConfig> = {
  'type': 'type',
  'vmname': 'vmName',
  'host': 'host',
  'localengineport': 'localEnginePort',
  'computerserverport': 'computerServerPort',
  'username': 'username',
  'password': 'password',
  'vncport': 'vncPort',
  'wsport': 'wsPort',
  'ospassword': 'osPassword',
  'tags': 'tags',
  'capabilities': 'capabilities',
  'description': 'description',
};

// 需要解析为数字的字段
const NUMBER_FIELDS = new Set(['localEnginePort', 'computerServerPort', 'vncPort', 'wsPort']);

// 需要解析为数组的字段（逗号分隔）
const ARRAY_FIELDS = new Set(['tags', 'capabilities']);

/**
 * 解析配置文件内容
 */
export function parseComputersConfig(content: string): ComputerConfig[] {
  const lines = content.split('\n');
  const computers: ComputerConfig[] = [];
  let currentComputer: Partial<ComputerConfig> | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 跳过空行和注释
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    // 检查是否是 Computer 定义行
    const computerMatch = trimmed.match(/^Computer\s+(.+)$/i);
    if (computerMatch) {
      // 保存上一个 Computer
      if (currentComputer && currentComputer.name) {
        computers.push(finalizeComputer(currentComputer));
      }

      // 开始新的 Computer
      currentComputer = {
        name: computerMatch[1].trim(),
        tags: [],
        capabilities: [],
      };
      continue;
    }

    // 解析属性行（缩进的行）
    if (currentComputer && (line.startsWith('    ') || line.startsWith('\t'))) {
      const propMatch = trimmed.match(/^(\w+)\s+(.+)$/);
      if (propMatch) {
        const [, key, value] = propMatch;
        const fieldName = FIELD_MAP[key.toLowerCase()];

        if (fieldName) {
          let parsedValue: any = value.trim();

          // 解析数字
          if (NUMBER_FIELDS.has(fieldName)) {
            parsedValue = parseInt(parsedValue, 10);
            if (isNaN(parsedValue)) {
              console.warn(`[ComputerConfigParser] Invalid number for ${key}: ${value}`);
              continue;
            }
          }

          // 解析数组（逗号分隔）
          if (ARRAY_FIELDS.has(fieldName)) {
            parsedValue = parsedValue.split(',').map((s: string) => s.trim()).filter(Boolean);
          }

          // 解析类型
          if (fieldName === 'type') {
            parsedValue = parsedValue.toLowerCase() as ComputerType;
          }

          (currentComputer as any)[fieldName] = parsedValue;
        }
      }
    }
  }

  // 保存最后一个 Computer
  if (currentComputer && currentComputer.name) {
    computers.push(finalizeComputer(currentComputer));
  }

  return computers;
}

/**
 * 完成 Computer 配置，填充默认值
 */
function finalizeComputer(partial: Partial<ComputerConfig>): ComputerConfig {
  return {
    name: partial.name || 'Unknown',
    type: partial.type || 'physical',
    vmName: partial.vmName,
    host: partial.host || 'localhost',
    localEnginePort: partial.localEnginePort ?? DEFAULT_PORTS.localEngine,
    computerServerPort: partial.computerServerPort ?? DEFAULT_PORTS.computerServer,
    username: partial.username,
    password: partial.password,
    vncPort: partial.vncPort ?? DEFAULT_PORTS.vnc,
    wsPort: partial.wsPort ?? DEFAULT_PORTS.ws,
    osPassword: partial.osPassword,
    tags: partial.tags || [],
    capabilities: partial.capabilities || [],
    description: partial.description,
  };
}

/**
 * 序列化配置到文件格式
 */
export function serializeComputersConfig(configs: ComputerConfig[]): string {
  const lines: string[] = [
    '# UseIt Computers Configuration',
    '# 类似 SSH config 格式，每个 Computer 定义一台电脑',
    '#',
    '# 示例:',
    '# Computer VM-Dev',
    '#     Type vm',
    '#     VMName UseIt-Dev-VM',
    '#     Host auto',
    '#     LocalEnginePort 8324',
    '#',
    '',
  ];

  for (const config of configs) {
    // 跳过 This PC（自动生成，不需要保存）
    if (config.type === 'thispc') {
      continue;
    }

    lines.push(`Computer ${config.name}`);

    // 必填字段
    lines.push(`    Type ${config.type}`);
    
    if (config.vmName) {
      lines.push(`    VMName ${config.vmName}`);
    }
    
    lines.push(`    Host ${config.host}`);

    // 可选端口（如果不是默认值）
    if (config.localEnginePort !== DEFAULT_PORTS.localEngine) {
      lines.push(`    LocalEnginePort ${config.localEnginePort}`);
    }
    if (config.computerServerPort !== DEFAULT_PORTS.computerServer) {
      lines.push(`    ComputerServerPort ${config.computerServerPort}`);
    }
    if (config.vncPort !== DEFAULT_PORTS.vnc) {
      lines.push(`    VNCPort ${config.vncPort}`);
    }
    if (config.wsPort !== DEFAULT_PORTS.ws) {
      lines.push(`    WSPort ${config.wsPort}`);
    }

    // 认证信息
    if (config.username) {
      lines.push(`    Username ${config.username}`);
    }
    if (config.password) {
      lines.push(`    Password ${config.password}`);
    }
    if (config.osPassword) {
      lines.push(`    OSPassword ${config.osPassword}`);
    }

    // 标签和能力
    if (config.tags.length > 0) {
      lines.push(`    Tags ${config.tags.join(', ')}`);
    }
    if (config.capabilities.length > 0) {
      lines.push(`    Capabilities ${config.capabilities.join(', ')}`);
    }

    // 描述
    if (config.description) {
      lines.push(`    Description ${config.description}`);
    }

    lines.push('');
  }

  return lines.join('\n');
}

/**
 * 生成示例配置文件内容
 */
export function generateExampleConfig(): string {
  return `# UseIt Computers Configuration
# 类似 SSH config 格式，每个 Computer 定义一台电脑
#
# 字段说明:
#   Computer    - 电脑名称（唯一标识）
#   Type        - 类型: vm, physical, cloud
#   VMName      - VM 类型专用：Hyper-V 虚拟机名称
#   Host        - IP 地址，或 "auto"（VM 自动获取 IP）
#   LocalEnginePort    - Local Engine 端口（默认 8324）
#   ComputerServerPort - Computer Server 端口（默认 8080）
#   Username    - VM 登录用户名
#   Password    - VM 登录密码
#   VNCPort     - VNC 端口（默认 5900）
#   WSPort      - WebSocket 端口（默认 16080）
#   OSPassword  - 系统登录密码
#   Tags        - 标签（逗号分隔）
#   Capabilities - 支持的能力（逗号分隔）: excel, autocad, browser
#   Description - 描述信息
#
# 注意: "This PC" 会自动添加，无需配置

# 虚拟机示例
Computer VM-Dev
    Type vm
    VMName UseIt-Dev-VM
    Host auto
    Username useit
    Password 12345678
    OSPassword 123456
    Description 开发测试虚拟机

# 物理机示例
# Computer Office-PC
#     Type physical
#     Host 192.168.1.100
#     Description 办公室工作站

# 云端服务器示例
# Computer Cloud-Server
#     Type cloud
#     Host myserver.example.com
#     Description 云端测试服务器
`;
}



