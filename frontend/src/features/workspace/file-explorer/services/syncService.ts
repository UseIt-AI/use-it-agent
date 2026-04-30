import type { FileNode } from '../types';

export interface LocalFileInfo {
  filename: string;
  path?: string;
  last_modified?: string;
  etag?: string;
  size_bytes?: number;
}

const SYNC_IGNORED_FOLDERS = new Set(['.cua']);

/**
 * 从文件树中收集所有文件信息（包含元数据），供本地工具或对比使用。
 */
export async function collectFilesWithMetadata(
  nodes: FileNode[],
  basePath: string = ''
): Promise<LocalFileInfo[]> {
  const files: LocalFileInfo[] = [];

  const normalizePath = (p: string): string => {
    return p.replace(/\\/g, '/');
  };

  const getRelativePath = (absolutePath: string, base: string): string => {
    const normalizedAbs = normalizePath(absolutePath);
    const normalizedBase = normalizePath(base);

    if (!normalizedAbs.startsWith(normalizedBase)) {
      return absolutePath.split(/[/\\]/).pop() || '';
    }

    const relative = normalizedAbs.slice(normalizedBase.length).replace(/^[/\\]/, '');
    return relative || '';
  };

  const traverse = async (node: FileNode) => {
    if (node.type === 'folder' && SYNC_IGNORED_FOLDERS.has(node.name)) return;
    if (!node.path || node.type !== 'file') {
      if (node.type === 'folder' && node.children && node.children.length > 0) {
        for (const child of node.children) {
          await traverse(child);
        }
      }
      return;
    }

    const relativePath = basePath ? getRelativePath(node.path, basePath) : node.name;

    let lastModified: string | undefined;
    let sizeBytes: number | undefined;
    let etag: string | undefined;

    try {
      const electron = window.electron as any;
      if (electron?.getFileMetadata) {
        const metadata = (await electron.getFileMetadata(node.path)) as {
          size: number;
          lastModified: number;
          etag?: string;
        } | null;
        if (metadata) {
          if (metadata.lastModified) {
            lastModified = new Date(metadata.lastModified).toISOString();
          }
          if (metadata.size !== undefined) {
            sizeBytes = metadata.size;
          }
          if (metadata.etag) {
            etag = metadata.etag;
          }
        }
      } else {
        console.warn('Electron getFileMetadata API not available, using fallback');
      }
    } catch (error) {
      console.warn(`Failed to get metadata for ${node.path}:`, error);
    }

    files.push({
      filename: node.name,
      path: relativePath || undefined,
      last_modified: lastModified,
      etag: etag,
      size_bytes: sizeBytes,
    });
  };

  for (const node of nodes) {
    await traverse(node);
  }

  console.log('[SyncService] collectFilesWithMetadata 结果:', {
    totalFiles: files.length,
    files: files.map((f) => ({
      name: f.filename,
      relativePath: f.path,
      hasMetadata: !!(f.last_modified || f.etag || f.size_bytes),
    })),
  });

  return files;
}
