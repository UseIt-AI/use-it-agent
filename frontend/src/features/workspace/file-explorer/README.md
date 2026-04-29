# 文件资源管理器 (File Explorer) 功能说明文档

## 📋 目录

- [概述](#概述)
- [核心功能](#核心功能)
- [用户界面功能](#用户界面功能)
- [文件系统操作](#文件系统操作)
- [文件查看与编辑](#文件查看与编辑)
- [键盘快捷键](#键盘快捷键)
- [技术架构](#技术架构)
- [API 接口说明](#api-接口说明)
- [使用示例](#使用示例)
- [注意事项](#注意事项)

---

## 概述

文件资源管理器是一个基于 Electron 和 React 的完整文件系统管理工具，提供了类似 VSCode 的文件浏览、编辑和管理体验。它支持实时文件系统监听、文件/文件夹的创建、重命名、删除、复制、剪切、移动等操作，以及文本文件的查看和编辑功能。

### 主要特性

- ✅ **实时文件系统监听** - 自动检测文件系统变化并更新视图
- ✅ **完整的文件操作** - 创建、重命名、删除、复制、剪切、移动
- ✅ **拖拽支持** - 支持拖拽移动文件和文件夹
- ✅ **文件查看与编辑** - 支持文本文件和图片文件的查看，文本文件可编辑
- ✅ **右键菜单** - 丰富的上下文菜单操作
- ✅ **键盘快捷键** - 完整的快捷键支持
- ✅ **搜索功能** - 快速搜索文件（通过侧边栏搜索面板）

---

## 核心功能

### 1. 文件树显示

文件资源管理器以树形结构显示工作区目录下的所有文件和文件夹：

- **默认路径**: `workspace` 文件夹（项目根目录的上级目录）
- **实时更新**: 通过文件系统监听器自动检测变化
- **图标区分**: 不同类型文件显示不同颜色的图标
- **展开/折叠**: 支持文件夹的展开和折叠操作

### 2. 文件系统监听

系统会自动监听工作区目录的变化，包括：

- 文件/文件夹的创建
- 文件/文件夹的删除
- 文件/文件夹的重命名
- 文件/文件夹的移动

当检测到变化时，文件树会自动刷新（带防抖处理，避免频繁刷新）。

---

## 用户界面功能

### 1. 文件树节点

每个文件/文件夹节点支持以下交互：

- **单击**: 选中节点
- **双击**: 打开文件（仅文件，文件夹会展开/折叠）
- **右键**: 显示上下文菜单
- **拖拽**: 移动文件/文件夹到其他位置

### 2. 右键上下文菜单

右键点击文件/文件夹节点会显示上下文菜单，包含以下操作：

#### 通用操作（所有节点）
- **新建文件** (`Ctrl+N`)
- **新建文件夹** (`Ctrl+Shift+N`)
- **粘贴** (`Ctrl+V`) - 当剪贴板有内容时显示

#### 文件/文件夹操作（非根节点）
- **重命名** (`F2`)
- **复制** (`Ctrl+C`)
- **剪切** (`Ctrl+X`)
- **删除** (`Delete`)

### 3. 文件图标

不同类型的文件显示不同颜色的图标：

- **文件夹**: 绿色 (#6A9955)
- **JSON 文件**: 红色 (#F56565)
- **JavaScript/TypeScript**: 黄色/蓝色 (#F7DF1E / #3178C6)
- **Python**: 蓝色 (#3776AB)
- **图片文件**: 紫色 (#A78BFA)
- **文本/Markdown**: 灰色 (#9CA3AF)
- **其他文件**: 默认灰色

---

## 文件系统操作

### 1. 创建文件/文件夹

#### 创建文件
- **方式一**: 右键菜单 → "新建文件"
- **方式二**: 快捷键 `Ctrl+N`
- **默认名称**: `untitled`（会自动添加序号避免重名）

#### 创建文件夹
- **方式一**: 右键菜单 → "新建文件夹"
- **方式二**: 快捷键 `Ctrl+Shift+N`
- **默认名称**: `New Folder`（会自动添加序号避免重名）

### 2. 重命名

#### 重命名文件/文件夹
- **方式一**: 右键菜单 → "重命名"
- **方式二**: 快捷键 `F2`
- **方式三**: 拖拽时按住左键选择文本（编辑模式下禁用拖拽）

重命名时会进入编辑模式，输入框支持文本选择，不会触发拖拽操作。

### 3. 删除

#### 删除文件/文件夹
- **方式一**: 右键菜单 → "删除"
- **方式二**: 快捷键 `Delete`
- **确认提示**: 删除前会弹出确认对话框

删除文件夹会递归删除其所有子文件和子文件夹。

### 4. 复制/剪切/粘贴

#### 复制
- **方式一**: 右键菜单 → "复制"
- **方式二**: 快捷键 `Ctrl+C`
- **功能**: 将文件/文件夹复制到剪贴板

#### 剪切
- **方式一**: 右键菜单 → "剪切"
- **方式二**: 快捷键 `Ctrl+X`
- **功能**: 将文件/文件夹移动到剪贴板（标记为待移动）

#### 粘贴
- **方式一**: 右键菜单 → "粘贴"
- **方式二**: 快捷键 `Ctrl+V`
- **功能**: 将剪贴板中的文件/文件夹粘贴到目标位置
- **自动重命名**: 如果目标位置已存在同名文件，会自动添加序号

### 5. 移动文件/文件夹

#### 拖拽移动
- **操作**: 按住文件/文件夹节点，拖拽到目标文件夹
- **限制**: 不能将文件夹移动到其自身的子目录中
- **视觉反馈**: 拖拽时显示目标位置高亮

### 6. 文件系统监听

系统会自动监听以下事件：

- **文件创建**: 检测到新文件时自动刷新
- **文件删除**: 检测到文件删除时自动刷新
- **文件重命名**: 检测到文件重命名时自动刷新
- **文件移动**: 检测到文件移动时自动刷新

监听器使用防抖机制，避免频繁刷新影响性能。

---

## 文件查看与编辑

### 1. 打开文件

双击文件节点即可在文件查看器中打开文件。

### 2. 支持的文件类型

#### 文本文件
支持以下扩展名的文本文件：
- `.txt`, `.md`, `.json`, `.py`, `.js`, `.ts`, `.tsx`, `.jsx`
- `.html`, `.css`, `.xml`, `.yaml`, `.yml`
- `.log`, `.csv`, `.ini`, `.conf`, `.config`
- `.sh`, `.bat`, `.ps1`, `.sql`
- `.vue`, `.svelte`

#### 图片文件
支持以下格式的图片文件：
- `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`
- `.bmp`, `.webp`, `.ico`

#### 文件大小限制
- 文本文件: 最大 10MB
- 图片文件: 最大 10MB

### 3. 文件查看器功能

#### 文本文件查看
- **只读模式**: 默认以只读模式显示文件内容
- **等宽字体**: 使用等宽字体显示代码
- **行号**: 支持显示行号（通过样式实现）
- **语法高亮**: 基础文本显示（可扩展为语法高亮）

#### 图片文件查看
- **Base64 编码**: 图片以 Base64 格式传输
- **自适应显示**: 图片自动适应容器大小
- **居中显示**: 图片在容器中居中显示

#### 状态栏信息
文件查看器底部显示类似 VSCode 的状态栏：

- **左侧**: 文件完整路径
- **右侧**: 
  - 编码格式（文本文件）
  - 文件大小
  - 文件类型/扩展名

### 4. 文本文件编辑

#### 进入编辑模式
- **方式**: 点击文件查看器右上角的"编辑"按钮
- **状态**: 进入编辑模式后，文本区域变为可编辑

#### 编辑功能
- **实时编辑**: 支持实时编辑文件内容
- **未保存提示**: 有未保存更改时，文件名旁显示橙色圆点（●）
- **状态栏提示**: 编辑模式下状态栏显示"● 编辑中"

#### 保存文件
- **方式一**: 点击"保存"按钮
- **方式二**: 快捷键 `Ctrl+S`
- **状态**: 保存时显示"保存中..."提示
- **更新**: 保存后更新文件大小和状态

#### 取消编辑
- **方式一**: 点击"取消"按钮
- **方式二**: 快捷键 `Esc`
- **确认**: 如果有未保存更改，会弹出确认对话框

#### 关闭保护
关闭文件标签页时，如果有未保存的更改，会弹出确认对话框。

---

## 键盘快捷键

### 文件操作快捷键

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `F2` | 重命名 | 重命名选中的文件/文件夹 |
| `Delete` | 删除 | 删除选中的文件/文件夹（需确认） |
| `Ctrl+C` | 复制 | 复制选中的文件/文件夹 |
| `Ctrl+X` | 剪切 | 剪切选中的文件/文件夹 |
| `Ctrl+V` | 粘贴 | 粘贴剪贴板中的文件/文件夹 |
| `Ctrl+N` | 新建文件 | 在选中位置创建新文件 |
| `Ctrl+Shift+N` | 新建文件夹 | 在选中位置创建新文件夹 |

### 文件编辑快捷键

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `Ctrl+S` | 保存 | 保存当前编辑的文件 |
| `Esc` | 取消编辑 | 取消编辑并恢复原始内容 |

### 快捷键使用说明

- 快捷键只在文件资源管理器获得焦点时生效
- 如果焦点在输入框或文本区域，快捷键不会触发
- 某些操作（如删除）需要用户确认

---

## 技术架构

### 1. 架构概览

文件资源管理器采用三层架构：

```
┌─────────────────────────────────────┐
│   React 前端 (Renderer Process)     │
│  - FileExplorer.tsx                 │
│  - FileViewer.tsx                   │
│  - useFileExplorerTree.ts           │
└──────────────┬──────────────────────┘
               │ IPC Communication
┌──────────────▼──────────────────────┐
│   Electron Preload (Bridge)         │
│  - preload.ts                       │
└──────────────┬──────────────────────┘
               │ IPC Handlers
┌──────────────▼──────────────────────┐
│   Electron Main Process              │
│  - main.ts (fs operations)           │
│  - Node.js fs module                 │
└─────────────────────────────────────┘
```

### 2. 核心组件

#### 前端组件

- **FileExplorer.tsx**: 主文件资源管理器组件
  - 使用 `react-arborist` 渲染文件树
  - 处理用户交互（点击、拖拽、右键菜单）
  - 管理键盘快捷键

- **FileViewer.tsx**: 文件查看器组件
  - 显示文本文件和图片文件
  - 提供文本编辑功能
  - 显示文件状态信息

- **FileTreeNode.tsx**: 文件树节点组件
  - 渲染单个文件/文件夹节点
  - 处理节点交互（点击、拖拽、右键）

- **ContextMenu.tsx**: 右键菜单组件
  - 显示上下文操作菜单
  - 支持快捷键显示

#### Hooks

- **useFileExplorerTree.ts**: 文件树管理 Hook
  - 加载文件树数据
  - 处理文件系统操作
  - 管理剪贴板状态
  - 文件系统监听

- **useContainerSize.ts**: 容器尺寸 Hook
  - 监听容器尺寸变化
  - 用于响应式布局

### 3. Electron IPC 通信

#### IPC 通道列表

| IPC 通道 | 方向 | 功能 |
|---------|------|------|
| `fs-get-project-root` | Renderer → Main | 获取项目根目录路径 |
| `fs-read-directory-tree` | Renderer → Main | 读取目录树结构 |
| `fs-watch-directory` | Renderer → Main | 开始监听目录变化 |
| `fs-unwatch-directory` | Renderer → Main | 停止监听目录变化 |
| `fs-directory-changed` | Main → Renderer | 目录变化事件通知 |
| `fs-create-file` | Renderer → Main | 创建新文件 |
| `fs-create-folder` | Renderer → Main | 创建新文件夹 |
| `fs-rename` | Renderer → Main | 重命名文件/文件夹 |
| `fs-delete` | Renderer → Main | 删除文件/文件夹 |
| `fs-copy` | Renderer → Main | 复制文件/文件夹 |
| `fs-move` | Renderer → Main | 移动文件/文件夹 |
| `fs-read-file` | Renderer → Main | 读取文件内容 |
| `fs-write-file` | Renderer → Main | 写入文件内容 |

---

## API 接口说明

### 1. 文件系统 API (window.electron)

所有文件系统操作通过 `window.electron` 对象访问。

#### 获取项目根目录

```typescript
const rootPath = await window.electron.fsGetProjectRoot(projectId?: string);
// 返回: string - 项目根目录的绝对路径
```

#### 读取目录树

```typescript
const tree = await window.electron.fsReadDirectoryTree(dirPath: string);
// 返回: FileNode[] - 目录树结构
```

#### 创建文件

```typescript
await window.electron.fsCreateFile(filePath: string);
// 创建空文件
```

#### 创建文件夹

```typescript
await window.electron.fsCreateFolder(folderPath: string);
// 创建文件夹（递归创建父目录）
```

#### 重命名

```typescript
await window.electron.fsRename(oldPath: string, newPath: string);
// 重命名文件或文件夹
```

#### 删除

```typescript
await window.electron.fsDelete(path: string);
// 删除文件或文件夹（递归删除）
```

#### 复制

```typescript
const newPath = await window.electron.fsCopy(sourcePath: string, destPath: string);
// 复制文件或文件夹，返回新路径
```

#### 移动

```typescript
const newPath = await window.electron.fsMove(sourcePath: string, destPath: string);
// 移动文件或文件夹，返回新路径
```

#### 读取文件

```typescript
const result = await window.electron.fsReadFile(filePath: string);
// 返回: {
//   content: string,      // 文件内容（文本或 Base64）
//   type: 'text' | 'image',
//   encoding?: string,    // 编码格式（文本文件）
//   size: number          // 文件大小（字节）
// }
```

#### 写入文件

```typescript
const result = await window.electron.fsWriteFile(
  filePath: string,
  content: string,
  encoding?: string
);
// 返回: { size: number } - 写入后的文件大小
```

#### 监听目录变化

```typescript
// 开始监听
window.electron.fsWatchDirectory(dirPath: string);

// 停止监听
window.electron.fsUnwatchDirectory(dirPath: string);

// 监听变化事件
window.electron.onFsDirectoryChanged((dirPath: string) => {
  // 处理目录变化
});
```

### 2. 组件 Props

#### FileExplorer Props

```typescript
interface FileExplorerProps {
  projectId?: string;                    // 项目 ID（可选）
  onFileSelect?: (filePath: string) => void;  // 文件选中回调
  onFileOpen?: (filePath: string, fileName: string) => void;  // 文件打开回调
  onFileTreeChange?: (tree: FileNode[]) => void;  // 文件树变化回调
}
```

#### FileViewer Props

```typescript
interface FileViewerProps {
  filePath: string;      // 文件路径
  fileName: string;      // 文件名
  onClose?: () => void;  // 关闭回调
}
```

### 3. 数据类型

#### FileNode

```typescript
interface FileNode {
  id: string;              // 节点唯一标识（通常是文件路径）
  name: string;            // 文件/文件夹名称
  type: 'file' | 'folder'; // 节点类型
  children?: FileNode[];   // 子节点（文件夹）
  path?: string;          // 文件/文件夹的绝对路径
  modified?: boolean;     // 是否已修改
  isNew?: boolean;        // 是否为新创建
}
```

---

## 使用示例

### 1. 基本使用

```tsx
import FileExplorer from '@/features/workspace/file-explorer/FileExplorer';

function MyComponent() {
  const handleFileOpen = (filePath: string, fileName: string) => {
    console.log('打开文件:', filePath, fileName);
  };

  return (
    <FileExplorer
      projectId="your-project-id"
      onFileOpen={handleFileOpen}
    />
  );
}
```

### 2. 监听文件树变化

```tsx
import FileExplorer from '@/features/workspace/file-explorer/FileExplorer';
import { useState } from 'react';

function MyComponent() {
  const [fileTree, setFileTree] = useState([]);

  return (
    <FileExplorer
      projectId="your-project-id"
      onFileTreeChange={setFileTree}
    />
  );
}
```

### 3. 文件查看器使用

```tsx
import { FileViewer } from '@/features/workspace/file-explorer/components/FileViewer';

function MyComponent() {
  return (
    <FileViewer
      filePath="/path/to/file.txt"
      fileName="file.txt"
      onClose={() => console.log('关闭文件')}
    />
  );
}
```

### 4. 直接调用文件系统 API

```typescript
// 创建文件
await window.electron.fsCreateFile('/path/to/newfile.txt');

// 读取文件
const result = await window.electron.fsReadFile('/path/to/file.txt');
console.log(result.content);

// 写入文件
await window.electron.fsWriteFile('/path/to/file.txt', 'Hello World');

// 复制文件
await window.electron.fsCopy('/path/to/source.txt', '/path/to/dest.txt');
```

---

## 注意事项

### 1. 文件路径

- 所有文件路径都使用绝对路径
- 路径分隔符在不同操作系统上会自动处理（Windows: `\`, Unix: `/`）
- 项目根目录默认为 `workspace` 文件夹

### 2. 文件大小限制

- 文本文件和图片文件最大支持 10MB
- 超过限制的文件无法在查看器中打开
- 建议使用外部工具处理大文件

### 3. 文件编码

- 文本文件默认使用 UTF-8 编码
- 写入文件时可以通过 `encoding` 参数指定编码
- 支持的编码格式取决于 Node.js Buffer 支持

### 4. 文件系统监听

- 文件系统监听使用 Node.js `fs.watch` API
- 在某些系统上可能不够稳定，建议定期刷新
- 监听器使用防抖机制，避免频繁刷新

### 5. 错误处理

- 所有文件操作都会返回错误信息
- 前端会显示错误提示
- 建议在生产环境中添加更详细的错误日志

### 6. 性能考虑

- 大型目录树可能影响性能
- 文件系统监听会消耗一定资源
- 建议对大型项目进行优化

### 7. 安全性

- 文件操作仅限于项目工作区目录
- 不允许访问系统关键目录
- 删除操作需要用户确认

---

## 更新日志

### v1.0.0 (当前版本)

- ✅ 实现基础文件树显示
- ✅ 实现文件系统监听
- ✅ 实现文件/文件夹的创建、重命名、删除
- ✅ 实现复制、剪切、粘贴功能
- ✅ 实现拖拽移动功能
- ✅ 实现文件查看和编辑功能
- ✅ 实现右键菜单和键盘快捷键
- ✅ 实现搜索功能（通过侧边栏）

---

## 相关文件

### 前端文件

- `FileExplorer.tsx` - 主文件资源管理器组件
- `FileViewer.tsx` - 文件查看器组件
- `FileTreeNode.tsx` - 文件树节点组件
- `ContextMenu.tsx` - 右键菜单组件
- `useFileExplorerTree.ts` - 文件树管理 Hook
- `useContainerSize.ts` - 容器尺寸 Hook
- `types.ts` - TypeScript 类型定义

### Electron 文件

- `main.ts` - Electron 主进程，包含所有文件系统操作
- `preload.ts` - Electron 预加载脚本，暴露 API 给渲染进程
- `types/electron.d.ts` - Electron API 类型定义

---

## 技术支持

如有问题或建议，请联系开发团队。

---

**最后更新**: 2024年

