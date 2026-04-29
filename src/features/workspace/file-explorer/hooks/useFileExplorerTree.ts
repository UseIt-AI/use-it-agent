import { useState, useCallback, useEffect, useRef } from 'react';
import type { FileNode } from '../types';

// 默认需要锁定的文件和文件夹名称
const LOCKED_NAMES = new Set(['downloads', 'outputs', 'uploads', 'workspace', '.cua']);

// 获取解锁状态存储的键名
const getUnlockedKeysKey = (projectId?: string) => {
  return projectId ? `unlocked_files_${projectId}` : 'unlocked_files_default';
};

const getLastSyncedAtKey = (projectId?: string) => {
  return projectId ? `workspace_fileExplorer_lastSyncAt_${projectId}` : 'workspace_fileExplorer_lastSyncAt_default';
};

// 从本地存储加载解锁的文件/文件夹列表
const loadUnlockedFiles = (projectId?: string): Set<string> => {
  try {
    const key = getUnlockedKeysKey(projectId);
    const stored = localStorage.getItem(key);
    if (stored) {
      const unlocked = JSON.parse(stored) as string[];
      return new Set(unlocked);
    }
  } catch (err) {
    console.error('Failed to load unlocked files:', err);
  }
  return new Set<string>();
};

// 保存解锁的文件/文件夹列表到本地存储
const saveUnlockedFiles = (projectId: string | undefined, unlocked: Set<string>) => {
  try {
    const key = getUnlockedKeysKey(projectId);
    localStorage.setItem(key, JSON.stringify(Array.from(unlocked)));
  } catch (err) {
    console.error('Failed to save unlocked files:', err);
  }
};

type UseFileExplorerTreeOptions = {
  projectId?: string;
  rootPath?: string;
  enableLocking?: boolean;
  onError?: (message: string) => void;
};

// 检查节点是否是默认锁定的文件/文件夹（可以重新上锁）
const isDefaultLockable = (
  nodeName: string,
  nodePath: string,
  basePath: string,
  enableLocking: boolean
): boolean => {
  if (!enableLocking) return false;
  // 检查是否是项目根目录本身
  if (basePath && nodePath && nodePath === basePath) {
    return true;
  }
  
  const normalizedName = nodeName.toLowerCase();
  
  // 检查是否是默认文件夹或文件
  if (LOCKED_NAMES.has(normalizedName)) {
    // 检查是否在项目根目录下（不是子目录中的同名文件夹）
    if (basePath && nodePath) {
      // 获取相对于项目根目录的路径
      const relativePath = nodePath.replace(basePath, '').replace(/^[\\/]+/, '').replace(/[\\/]+/g, '/');
      // 获取第一级路径（项目根目录下的直接子项）
      const firstLevel = relativePath.split('/')[0];
      // 检查是否是项目根目录下的直接子项
      return firstLevel === normalizedName || firstLevel === nodeName;
    }
    // 如果没有 basePath，假设是根目录下的文件
    return true;
  }
  
  return false;
};

// 检查节点是否应该被锁定
const shouldBeLocked = (
  nodeName: string, 
  nodePath: string, 
  basePath: string, 
  unlockedFiles: Set<string>,
  enableLocking: boolean
): boolean => {
  if (!enableLocking) return false;
  // 首先检查是否是项目根目录本身
  if (basePath && nodePath && nodePath === basePath) {
    // 项目根目录默认锁定，除非在解锁列表中
    return !unlockedFiles.has(nodePath);
  }
  
  const normalizedName = nodeName.toLowerCase();
  
  // 检查是否是默认文件夹或文件
  if (LOCKED_NAMES.has(normalizedName)) {
    // 检查是否在项目根目录下（不是子目录中的同名文件夹）
    if (basePath && nodePath) {
      // 获取相对于项目根目录的路径
      const relativePath = nodePath.replace(basePath, '').replace(/^[\\/]+/, '').replace(/[\\/]+/g, '/');
      // 获取第一级路径（项目根目录下的直接子项）
      const firstLevel = relativePath.split('/')[0];
      // 检查是否是项目根目录下的直接子项
      const isRootLevel = firstLevel === normalizedName || firstLevel === nodeName;
      
      if (isRootLevel) {
        // 检查是否在解锁列表中
        return !unlockedFiles.has(nodePath);
      }
    }
    // 如果没有 basePath，假设是根目录下的文件
    // 检查是否在解锁列表中
    return !unlockedFiles.has(nodePath || nodeName);
  }
  
  return false;
};

// 将文件系统节点转换为 FileNode
const processData = (
  node: any, 
  basePath: string = '', 
  unlockedFiles: Set<string> = new Set(),
  enableLocking: boolean = true,
  lastSyncedAtMs: number = 0
): FileNode => {
  const relativePath = basePath ? node.path.replace(basePath, '').replace(/^[\\/]/, '') : node.name;
  const normalizedRelativePath = relativePath.replace(/[\\/]+/g, '/').replace(/^\/+/, '');
  const firstSegment = normalizedRelativePath.split('/')[0]?.toLowerCase() || '';
  // `outputs` is system-managed runtime output; do not show as unsynced (blue).
  const isOutputsManaged = firstSegment === 'outputs';
  const isLocked = shouldBeLocked(node.name, node.path || '', basePath, unlockedFiles, enableLocking);
  const canLock = isDefaultLockable(node.name, node.path || '', basePath, enableLocking);
  const isModifiedSinceLastSync =
    node.type === 'file' &&
    !isOutputsManaged &&
    lastSyncedAtMs > 0 &&
    typeof node.modified === 'number' &&
    node.modified > lastSyncedAtMs;
  
  return {
    id: node.path || 'root',
    name: node.name,
    type: node.type,
    path: node.path || '',
    modified: Boolean(isModifiedSinceLastSync),
    isLocked: isLocked,
    canLock: canLock, // 标记是否可以上锁/解锁
    children: node.children?.map((child: any) => processData(child, basePath, unlockedFiles, enableLocking, lastSyncedAtMs)),
  };
};

// 获取项目根目录路径（异步）
const getProjectRootPath = async (projectId?: string): Promise<string> => {
  // 在 Electron 环境中，从主进程获取绝对路径
  const electron = window.electron as any;
  if (electron?.fsGetProjectRoot) {
    try {
      return await electron.fsGetProjectRoot(projectId);
    } catch (err) {
      console.error('Failed to get project root path:', err);
      // 如果失败，返回相对路径作为后备
      return 'workspace';
    }
  }
  // 如果不在 Electron 环境中，返回相对路径
  return 'workspace';
};

// 辅助函数：查找节点
const findNode = (nodes: FileNode[], id: string): FileNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findNode(node.children, id);
      if (found) return found;
    }
  }
  return null;
};

// 辅助函数：查找父节点
const findParentNode = (nodes: FileNode[], targetId: string, parent: FileNode | null = null): FileNode | null => {
  for (const node of nodes) {
    if (node.id === targetId) return parent;
    if (node.children) {
      const found = findParentNode(node.children, targetId, node);
      if (found !== null) return found;
    }
  }
  return null;
};

// 辅助函数：更新节点
const updateNode = (nodes: FileNode[], id: string, updater: (node: FileNode) => FileNode): FileNode[] => {
  return nodes.map(node => {
    if (node.id === id) {
      return updater(node);
    }
    if (node.children) {
      return { ...node, children: updateNode(node.children, id, updater) };
    }
    return node;
  });
};

// 辅助函数：删除节点
const deleteNode = (nodes: FileNode[], id: string): FileNode[] => {
  return nodes
    .filter(node => node.id !== id)
    .map(node => {
      if (node.children) {
        return { ...node, children: deleteNode(node.children, id) };
      }
      return node;
    });
};

// 辅助函数：添加节点
const addNode = (nodes: FileNode[], parentId: string | null, newNode: FileNode): FileNode[] => {
  if (parentId === null || parentId === 'root') {
    return [...nodes, newNode];
  }

  return updateNode(nodes, parentId, node => {
    if (node.type === 'folder') {
      return {
        ...node,
        children: [...(node.children || []), newNode],
      };
    }
    return node;
  });
};

// 辅助函数：获取同级节点名称集合
const getSiblingNames = (nodes: FileNode[], parentId: string | null): Set<string> => {
  if (parentId === null || parentId === 'root') {
    return new Set(nodes.map(node => node.name));
  }
  const parent = findNode(nodes, parentId);
  if (!parent || parent.type !== 'folder') return new Set();
  return new Set((parent.children || []).map(child => child.name));
};

// 辅助函数：根据同级名称生成唯一名称，格式 base / base_1 / base_2 ...
const getUniqueName = (baseName: string, siblingNames: Set<string>): string => {
  if (!siblingNames.has(baseName)) return baseName;
  let suffix = 1;
  while (siblingNames.has(`${baseName}_${suffix}`)) {
    suffix += 1;
  }
  return `${baseName}_${suffix}`;
};

// 辅助函数：文件名避重（后缀插在扩展名前），例如 new_file.txt -> new_file_1.txt
const getUniqueFileName = (baseName: string, siblingNames: Set<string>): string => {
  if (!siblingNames.has(baseName)) return baseName;
  const dotIndex = baseName.lastIndexOf('.');
  const hasExt = dotIndex > 0 && dotIndex < baseName.length - 1;
  const stem = hasExt ? baseName.slice(0, dotIndex) : baseName;
  const ext = hasExt ? baseName.slice(dotIndex) : '';
  let suffix = 1;
  while (siblingNames.has(`${stem}_${suffix}${ext}`)) {
    suffix += 1;
  }
  return `${stem}_${suffix}${ext}`;
};

// 辅助函数：将路径前缀 oldPrefix 替换为 newPrefix
const replacePathPrefix = (value: string | undefined, oldPrefix: string, newPrefix: string): string | undefined => {
  if (!value) return value;
  if (value === oldPrefix) return newPrefix;
  if (value.startsWith(`${oldPrefix}/`) || value.startsWith(`${oldPrefix}\\`)) {
    return `${newPrefix}${value.slice(oldPrefix.length)}`;
  }
  return value;
};

// 辅助函数：重命名节点及其所有子节点的 id/path（用于文件夹重命名）
const remapNodePathTree = (node: FileNode, oldPath: string, newPath: string): FileNode => {
  const nextId = replacePathPrefix(node.id, oldPath, newPath) ?? node.id;
  const nextPath = replacePathPrefix(node.path, oldPath, newPath);
  return {
    ...node,
    id: nextId,
    path: nextPath,
    children: node.children?.map(child => remapNodePathTree(child, oldPath, newPath)),
  };
};

export function useFileExplorerTree(options: UseFileExplorerTreeOptions = {}) {
  const { projectId, rootPath, enableLocking = true, onError } = options;
  const [data, setData] = useState<FileNode[]>([]);
  const [clipboard, setClipboard] = useState<{ type: 'copy' | 'cut'; nodes: FileNode[] } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const rootPathRef = useRef<string | null>(null);
  const watcherCleanupRef = useRef<(() => void) | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const unlockedFilesRef = useRef<Set<string>>(new Set());

  const notifyError = useCallback((message: string) => {
    if (onError) {
      onError(message);
      return;
    }
    alert(message);
  }, [onError]);

  const getLastSyncedAtMs = useCallback((): number => {
    try {
      const raw = localStorage.getItem(getLastSyncedAtKey(projectId));
      const parsed = Number(raw);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
    } catch {
      return 0;
    }
  }, [projectId]);

  // 初始化：加载解锁的文件列表
  useEffect(() => {
    unlockedFilesRef.current = loadUnlockedFiles(projectId);
  }, [projectId]);

  // 加载文件系统数据
  const loadFileSystem = useCallback(async (rootPath: string) => {
    try {
      setIsLoading(true);
      setError(null);

      const electron = window.electron as any;
      if (!electron?.fsReadDirectoryTree) {
        throw new Error('File system API not available');
      }

      const tree = await electron.fsReadDirectoryTree(rootPath);
      if (tree) {
        // 使用解锁列表处理数据
        const lastSyncedAtMs = getLastSyncedAtMs();
        const processedTree = processData(tree, rootPath, unlockedFilesRef.current, enableLocking, lastSyncedAtMs);
        setData([processedTree]);
        rootPathRef.current = rootPath;
      } else {
        throw new Error('Failed to read directory tree');
      }
    } catch (err: any) {
      console.error('Failed to load file system:', err);
      setError(err.message || 'Failed to load file system');
      // 如果加载失败，使用空数据
      setData([]);
    } finally {
      setIsLoading(false);
    }
  }, [enableLocking, getLastSyncedAtMs]);

  // 初始化：加载文件系统并设置监听
  useEffect(() => {
    let isMounted = true;

    const initialize = async () => {
      const rootPathValue = rootPath || await getProjectRootPath(projectId);
      
      if (!isMounted) return;
      
      // 加载文件系统
      await loadFileSystem(rootPathValue);

      // 设置文件监听
      const electron = window.electron as any;
      if (electron?.fsWatchDirectory && electron?.onFsDirectoryChanged) {
        try {
          await electron.fsWatchDirectory(rootPathValue);
          
          // 监听文件变化事件
          const cleanup = electron.onFsDirectoryChanged((changeData: any) => {
            // 当文件变化时，重新加载文件系统
            // 使用防抖，避免频繁刷新
            if (debounceTimerRef.current) {
              clearTimeout(debounceTimerRef.current);
            }
            debounceTimerRef.current = setTimeout(() => {
              if (rootPathRef.current && isMounted) {
                loadFileSystem(rootPathRef.current);
              }
            }, 500); // 500ms 防抖
          });
          watcherCleanupRef.current = cleanup || null;
        } catch (err) {
          console.error('Failed to watch directory:', err);
        }
      }
    };

    initialize();

    // 清理函数
    return () => {
      isMounted = false;
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      if (watcherCleanupRef.current) {
        watcherCleanupRef.current();
        watcherCleanupRef.current = null;
      }
      const electron = window.electron as any;
      if (rootPathRef.current && electron?.fsUnwatchDirectory) {
        electron.fsUnwatchDirectory(rootPathRef.current).catch(console.error);
      }
    };
  }, [projectId, rootPath, loadFileSystem]);

  const handleMove = useCallback(
    async ({
      dragIds,
      parentId,
    }: {
      dragIds: string[];
      parentId: string | null;
      index: number;
    }) => {
      if (!dragIds || dragIds.length === 0) return;

      const electron = window.electron as any;
      const parent = parentId ? findNode(data, parentId) : null;
      const parentPath = parent?.path || rootPathRef.current || '';

      // 处理每个被拖拽的文件/文件夹
      for (const dragId of dragIds) {
        const node = findNode(data, dragId);
        if (!node || !node.path) continue;

        // 检查是否锁定
        if (node.isLocked) {
          notifyError(`无法移动：文件/文件夹 "${node.name}" 已锁定`);
          continue; // 跳过这个文件，继续处理其他文件
        }

        // 检查是否拖拽到自己的子目录中（防止循环）
        if (parentId && node.type === 'folder') {
          const targetParent = findNode(data, parentId);
          if (targetParent && isDescendant(node, targetParent.id)) {
            console.warn('Cannot move folder into itself');
            notifyError('不能将文件夹移动到自己的子目录中');
            continue;
          }
        }

        // 构建目标路径
        const pathSeparator = parentPath.includes('\\') ? '\\' : '/';
        const destPath = parentPath 
          ? `${parentPath}${pathSeparator}${node.name}` 
          : node.name;

        // 如果目标路径和源路径相同，跳过
        if (node.path === destPath) continue;

        try {
          if (electron?.fsMove) {
            // 移动文件或文件夹
            await electron.fsMove(node.path, destPath);
          } else {
            // 如果没有 Electron API，只更新内存数据
            setData(prev => {
              // 先从原位置删除
              const removed = deleteNode(prev, dragId);
              // 再添加到新位置
              const newNode: FileNode = {
                ...node,
                id: destPath,
                path: destPath,
                children: node.children?.map(child => ({
                  ...child,
                  id: `${destPath}${pathSeparator}${child.name}`,
                  path: `${destPath}${pathSeparator}${child.name}`,
                })),
              };
              return addNode(removed, parentId, newNode);
            });
          }
        } catch (error: any) {
          console.error('Failed to move file:', error);
          notifyError(`移动失败: ${error.message || '未知错误'}`);
          // 如果移动失败，刷新文件系统以恢复状态
          if (rootPathRef.current) {
            loadFileSystem(rootPathRef.current);
          }
          return; // 如果移动失败，停止处理其他文件
        }
      }

      // 刷新文件系统以显示变化
      if (rootPathRef.current && electron?.fsMove) {
        setTimeout(() => {
          loadFileSystem(rootPathRef.current!);
        }, 100);
      }
    },
    [data, loadFileSystem]
  );

  // 辅助函数：检查 targetId 是否是 node 的后代（用于防止将文件夹移动到自己的子目录中）
  const isDescendant = (node: FileNode, targetId: string): boolean => {
    // 如果节点本身就是要检查的目标节点，返回 true
    if (node.id === targetId) return true;
    
    // 如果节点有子节点，递归检查
    if (node.children) {
      for (const child of node.children) {
        if (isDescendant(child, targetId)) {
          return true;
        }
      }
    }
    return false;
  };

  const handleRename = useCallback(
    async ({ id, name }: { id: string; name: string }) => {
      if (!name || name.trim() === '') return null;

      const node = findNode(data, id);
      if (!node || !node.path) return null;

      // 检查是否锁定
      if (node.isLocked) {
        notifyError('无法重命名：该文件/文件夹已锁定');
        return null;
      }

      const electron = window.electron as any;
      if (electron?.fsRename) {
        try {
          const oldPath = node.path;
          const newPath = await electron.fsRename(node.path, name.trim());
          // 更新数据（包含子节点 id/path 同步）
          setData(prev =>
            updateNode(prev, id, currentNode => ({
              ...remapNodePathTree(currentNode, oldPath, newPath),
              name: name.trim(),
            }))
          );
          return { oldPath, newPath };
        } catch (error: any) {
          console.error('Failed to rename:', error);
          notifyError(`重命名失败: ${error?.message || '未知错误'}`);
          // 如果重命名失败，刷新文件系统以恢复状态
          if (rootPathRef.current) {
            loadFileSystem(rootPathRef.current);
          }
          return null;
        }
      } else {
        // 如果没有 Electron API，只更新内存数据
        const oldPath = node.path;
        const pathSeparator = oldPath.includes('\\') ? '\\' : '/';
        const lastSeparatorIndex = Math.max(oldPath.lastIndexOf('/'), oldPath.lastIndexOf('\\'));
        const parentPath = lastSeparatorIndex >= 0 ? oldPath.slice(0, lastSeparatorIndex) : '';
        const newPath = parentPath ? `${parentPath}${pathSeparator}${name.trim()}` : name.trim();

        setData(prev =>
          updateNode(prev, id, currentNode => ({
            ...remapNodePathTree(currentNode, oldPath, newPath),
            name: name.trim(),
          }))
        );
        return { oldPath, newPath };
      }
    },
    [data, loadFileSystem]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      const node = findNode(data, id);
      if (!node || !node.path) return;

      // 检查是否锁定
      if (node.isLocked) {
        notifyError('无法删除：该文件/文件夹已锁定');
        return;
      }

      const electron = window.electron as any;
      if (electron?.fsDelete) {
        try {
          await electron.fsDelete(node.path);
          // 删除成功后更新数据
          setData(prev => deleteNode(prev, id));
        } catch (error: any) {
          console.error('Failed to delete:', error);
          notifyError(`删除失败: ${error.message}`);
        }
      } else {
        // 如果没有 Electron API，只更新内存数据
        setData(prev => deleteNode(prev, id));
      }
    },
    [data]
  );

  const handleNewFile = useCallback(
    async (parentId: string | null) => {
      const parent = parentId ? findNode(data, parentId) : null;
      const parentPath = parent?.path || rootPathRef.current || '';
      
      const baseFileName = 'new_file.txt';
      const siblingNames = getSiblingNames(data, parentId);
      let newFileName = getUniqueFileName(baseFileName, siblingNames);
      const electron = window.electron as any;
      
      if (electron?.fsCreateFile) {
        // 构建文件路径（使用路径分隔符）
        const pathSeparator = parentPath.includes('\\') ? '\\' : '/';
        
        try {
          let newPath = parentPath
            ? `${parentPath}${pathSeparator}${newFileName}`
            : newFileName;
          let retryCount = 0;
          while (true) {
            try {
              await electron.fsCreateFile(newPath);
              break;
            } catch (createErr: any) {
              const msg = String(createErr?.message || '');
              const isAlreadyExists = /already exists|EEXIST|exist/i.test(msg);
              if (!isAlreadyExists || retryCount >= 50) {
                throw createErr;
              }
              retryCount += 1;
              siblingNames.add(newFileName);
              newFileName = getUniqueFileName(baseFileName, siblingNames);
              newPath = parentPath
                ? `${parentPath}${pathSeparator}${newFileName}`
                : newFileName;
            }
          }
          
          const newNode: FileNode = {
            id: newPath,
            name: newFileName,
            type: 'file',
            path: newPath,
            isNew: true,
          };
          
          setData(prev => addNode(prev, parentId, newNode));
        } catch (error: any) {
          console.error('Failed to create file:', error);
          notifyError(`创建文件失败: ${error.message}`);
        }
      } else {
        // 如果没有 Electron API，只更新内存数据
        const pathSeparator = parentPath.includes('\\') ? '\\' : '/';
        const newPath = parentPath ? `${parentPath}${pathSeparator}${newFileName}` : newFileName;
        const newNode: FileNode = {
          id: newPath,
          name: newFileName,
          type: 'file',
          path: newPath,
          isNew: true,
        };
        setData(prev => addNode(prev, parentId, newNode));
      }
    },
    [data]
  );

  const handleNewFolder = useCallback(
    async (parentId: string | null) => {
      const parent = parentId ? findNode(data, parentId) : null;
      const parentPath = parent?.path || rootPathRef.current || '';
      const baseFolderName = 'new_folder';
      const siblingNames = getSiblingNames(data, parentId);
      let newFolderName = getUniqueName(baseFolderName, siblingNames);
      
      const electron = window.electron as any;
      
      if (electron?.fsCreateFolder) {
        // 构建文件夹路径（使用路径分隔符）
        const pathSeparator = parentPath.includes('\\') ? '\\' : '/';
        
        try {
          // 若并发场景下磁盘已存在同名目录，自动递增后缀重试。
          let newPath = parentPath
            ? `${parentPath}${pathSeparator}${newFolderName}`
            : newFolderName;
          let retryCount = 0;
          while (true) {
            try {
              await electron.fsCreateFolder(newPath);
              break;
            } catch (createErr: any) {
              const msg = String(createErr?.message || '');
              const isAlreadyExists = /already exists|EEXIST|exist/i.test(msg);
              if (!isAlreadyExists || retryCount >= 50) {
                throw createErr;
              }
              retryCount += 1;
              newFolderName = `${baseFolderName}_${retryCount}`;
              newPath = parentPath
                ? `${parentPath}${pathSeparator}${newFolderName}`
                : newFolderName;
            }
          }
          
          const newNode: FileNode = {
            id: newPath,
            name: newFolderName,
            type: 'folder',
            path: newPath,
            children: [],
            isNew: true,
          };
          
          setData(prev => addNode(prev, parentId, newNode));
        } catch (error: any) {
          console.error('Failed to create folder:', error);
          notifyError(`创建文件夹失败: ${error.message}`);
        }
      } else {
        // 如果没有 Electron API，只更新内存数据
        const pathSeparator = parentPath.includes('\\') ? '\\' : '/';
        const newPath = parentPath ? `${parentPath}${pathSeparator}${newFolderName}` : newFolderName;
        const newNode: FileNode = {
          id: newPath,
          name: newFolderName,
          type: 'folder',
          path: newPath,
          children: [],
          isNew: true,
        };
        setData(prev => addNode(prev, parentId, newNode));
      }
    },
    [data]
  );

  const handleCopy = useCallback((idOrIds: string | string[]) => {
    const ids = Array.isArray(idOrIds) ? idOrIds : [idOrIds];
    const uniqueIds = Array.from(new Set(ids));
    const nodes = uniqueIds
      .map(id => findNode(data, id))
      .filter((node): node is FileNode => !!node);
    if (nodes.length > 0) {
      setClipboard({ type: 'copy', nodes });
    }
  }, [data]);

  const handleCut = useCallback((idOrIds: string | string[]) => {
    const ids = Array.isArray(idOrIds) ? idOrIds : [idOrIds];
    const uniqueIds = Array.from(new Set(ids));
    const nodes = uniqueIds
      .map(id => findNode(data, id))
      .filter((node): node is FileNode => !!node);
    if (nodes.length === 0) return;

    // 检查是否锁定
    if (nodes.some(node => node.isLocked)) {
      notifyError('无法剪切：所选项目中包含已锁定文件/文件夹');
      return;
    }
    setClipboard({ type: 'cut', nodes });
  }, [data]);

  const handlePaste = useCallback(
    async (parentId: string | null) => {
      const electron = window.electron as any;
      // If paste target is a file, normalize destination to its parent folder.
      const targetNode = parentId ? findNode(data, parentId) : null;
      const normalizedParentId = targetNode?.type === 'file'
        ? (findParentNode(data, parentId as string)?.id ?? null)
        : parentId;
      const parent = normalizedParentId ? findNode(data, normalizedParentId) : null;
      const parentPath = parent?.path || rootPathRef.current || '';
      const pathSeparator = parentPath.includes('\\') ? '\\' : '/';
      const withSuffix = (name: string, suffix: number) => {
        const lastDot = name.lastIndexOf('.');
        if (lastDot <= 0) return `${name}_${suffix}`;
        return `${name.slice(0, lastDot)}_${suffix}${name.slice(lastDot)}`;
      };
      const basenameFromPath = (p: string) => {
        const normalized = p.replace(/[/\\]+$/, '');
        const parts = normalized.split(/[/\\]/);
        return parts[parts.length - 1] || '';
      };
      const moveOrCopyFromAbsolutePath = async (sourcePath: string, mode: 'copy' | 'cut') => {
        if (!sourcePath) return;
        const baseName = basenameFromPath(sourcePath);
        if (!baseName) return;
        let candidateName = baseName;
        let destPath = parentPath ? `${parentPath}${pathSeparator}${candidateName}` : candidateName;
        for (let attempt = 0; attempt <= 50; attempt += 1) {
          try {
            if (mode === 'copy') {
              await electron.fsCopy(sourcePath, destPath);
            } else {
              await electron.fsMove(sourcePath, destPath);
            }
            return;
          } catch (err: any) {
            const msg = String(err?.message || err);
            const existsConflict = /already exists|Destination already exists|EEXIST|exist/i.test(msg);
            if (!existsConflict) throw err;
            candidateName = withSuffix(baseName, attempt + 1);
            destPath = parentPath ? `${parentPath}${pathSeparator}${candidateName}` : candidateName;
          }
        }
      };

      // Internal cut must take precedence over OS clipboard,
      // otherwise cut may degrade to copy when system clipboard also has files.
      if (clipboard?.type === 'cut') {
        for (const node of clipboard.nodes) {
          if (!node.path) continue;
          const destPath = parentPath
            ? `${parentPath}${pathSeparator}${node.name}`
            : node.name;
          try {
            if (electron?.fsMove) {
              await electron.fsMove(node.path, destPath);
              if (rootPathRef.current) {
                setTimeout(() => {
                  loadFileSystem(rootPathRef.current!);
                }, 100);
              }
            } else {
              const newNode: FileNode = {
                ...node,
                id: destPath,
                path: destPath,
                isNew: true,
                children: node.children?.map(child => ({
                  ...child,
                  id: `${destPath}${pathSeparator}${child.name}`,
                  path: `${destPath}${pathSeparator}${child.name}`,
                })),
              };
              setData(prev => {
                const updated = addNode(prev, normalizedParentId, newNode);
                return deleteNode(updated, node.id);
              });
            }
          } catch (error: any) {
            console.error('Failed to move file:', error);
            const errorMsg = error.message || '未知错误';
            notifyError(`移动失败: ${errorMsg}`);
            break;
          }
        }
        setClipboard(null);
        return;
      }

      // Prefer OS clipboard file list (Explorer copy/cut) when available.
      try {
        if (electron?.fsGetClipboardFilePaths && electron?.fsCopy && electron?.fsMove) {
          const payload = await electron.fsGetClipboardFilePaths();
          const sourcePaths = Array.from(new Set((payload?.paths || []) as string[]));
          if (sourcePaths.length > 0) {
            const mode: 'copy' | 'cut' = payload?.operation === 'cut' ? 'cut' : 'copy';
            for (const sourcePath of sourcePaths) {
              await moveOrCopyFromAbsolutePath(sourcePath, mode);
            }
            if (rootPathRef.current) {
              setTimeout(() => {
                loadFileSystem(rootPathRef.current!);
              }, 100);
            }
            return;
          }
        }
      } catch (error: any) {
        const errorMsg = error?.message || '未知错误';
        notifyError(`粘贴失败: ${errorMsg}`);
        return;
      }

      if (!clipboard) return;

      // 处理每个要粘贴的节点
      for (const node of clipboard.nodes) {
        if (!node.path) continue;
        const destPath = parentPath
          ? `${parentPath}${pathSeparator}${node.name}`
          : node.name;

        try {
          if (clipboard.type === 'copy') {
            // 复制文件或文件夹
            if (electron?.fsCopy) {
              const newPath = await electron.fsCopy(node.path, destPath);
              
              // 刷新文件系统以显示新文件
              if (rootPathRef.current) {
                // 延迟刷新，确保文件系统操作完成
                setTimeout(() => {
                  loadFileSystem(rootPathRef.current!);
                }, 100);
              }
            } else {
              // 如果没有 Electron API，只更新内存数据
              const newNode: FileNode = {
                ...node,
                id: destPath,
                path: destPath,
                isNew: true,
                children: node.children?.map(child => ({
                  ...child,
                  id: `${destPath}${pathSeparator}${child.name}`,
                  path: `${destPath}${pathSeparator}${child.name}`,
                })),
              };
              setData(prev => addNode(prev, normalizedParentId, newNode));
            }
          } else if (clipboard.type === 'cut') {
            // 移动文件或文件夹
            if (electron?.fsMove) {
              const newPath = await electron.fsMove(node.path, destPath);
              
              // 刷新文件系统
              if (rootPathRef.current) {
                setTimeout(() => {
                  loadFileSystem(rootPathRef.current!);
                }, 100);
              }
            } else {
              // 如果没有 Electron API，只更新内存数据
              const newNode: FileNode = {
                ...node,
                id: destPath,
                path: destPath,
                isNew: true,
                children: node.children?.map(child => ({
                  ...child,
                  id: `${destPath}${pathSeparator}${child.name}`,
                  path: `${destPath}${pathSeparator}${child.name}`,
                })),
              };
              setData(prev => {
                const updated = addNode(prev, normalizedParentId, newNode);
                return deleteNode(updated, node.id);
              });
            }
          }
        } catch (error: any) {
          console.error(`Failed to ${clipboard.type} file:`, error);
          const errorMsg = error.message || '未知错误';
          notifyError(`${clipboard.type === 'copy' ? '复制' : '移动'}失败: ${errorMsg}`);
          // 如果操作失败，不继续处理其他节点
          break;
        }
      }

      // 清空剪贴板（无论成功或失败）
      setClipboard(null);
    },
    [clipboard, data, loadFileSystem, notifyError]
  );

  // 解锁节点
  const handleUnlock = useCallback((id: string) => {
    if (!enableLocking) return;
    const node = findNode(data, id);
    if (!node || !node.path) return;

    // 添加到解锁列表
    unlockedFilesRef.current.add(node.path);
    
    // 保存到本地存储
    saveUnlockedFiles(projectId, unlockedFilesRef.current);

    // 更新数据
    setData(prev =>
      updateNode(prev, id, node => ({
        ...node,
        isLocked: false,
      }))
    );
  }, [data, projectId, enableLocking]);

  // 重新上锁节点
  const handleLock = useCallback((id: string) => {
    if (!enableLocking) return;
    const node = findNode(data, id);
    if (!node || !node.path || !node.canLock) return;

    // 从解锁列表中移除
    unlockedFilesRef.current.delete(node.path);
    
    // 保存到本地存储
    saveUnlockedFiles(projectId, unlockedFilesRef.current);

    // 更新数据
    setData(prev =>
      updateNode(prev, id, node => ({
        ...node,
        isLocked: true,
      }))
    );
  }, [data, projectId, enableLocking]);

  // 刷新文件系统
  const refresh = useCallback(() => {
    if (rootPathRef.current) {
      loadFileSystem(rootPathRef.current);
    }
  }, [loadFileSystem]);

  return {
    data,
    isLoading,
    error,
    refresh,
    handleMove,
    handleRename,
    handleDelete,
    handleNewFile,
    handleNewFolder,
    handleCopy,
    handleCut,
    handlePaste,
    handleUnlock,
    handleLock,
    clipboard,
  };
}















