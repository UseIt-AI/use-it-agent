import type { FileNode } from '../types';

/** 删除确认 UI 使用的文件项结构（本地模式不再从接口填充） */
export interface DeletedFileInfo {
  s3_key: string;
  filename?: string;
  path?: string;
  delete_url: string;
  expires_at: string;
}

/**
 * 根据文件名猜测 MIME 类型（本地文件展示等场景仍可能用到）
 */
export function guessContentType(filename: string): string {
  const lower = filename.toLowerCase();
  const ext = lower.split('.').pop() || '';

  const mimeTypes: Record<string, string> = {
    txt: 'text/plain',
    md: 'text/markdown',
    json: 'application/json',
    py: 'text/x-python',
    js: 'text/javascript',
    ts: 'text/typescript',
    tsx: 'text/typescript',
    jsx: 'text/javascript',
    html: 'text/html',
    css: 'text/css',
    xml: 'application/xml',
    yaml: 'text/yaml',
    yml: 'text/yaml',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    svg: 'image/svg+xml',
    webp: 'image/webp',
    mp4: 'video/mp4',
    mkv: 'video/x-matroska',
    webm: 'video/webm',
    pdf: 'application/pdf',
    zip: 'application/zip',
  };

  return mimeTypes[ext] || 'application/octet-stream';
}

const SYNC_IGNORED_FOLDERS = new Set(['.cua']);

/**
 * 从文件树中收集所有文件路径
 * @param nodes 文件树节点数组
 * @param basePath 基础路径（用于计算相对路径）
 * @returns 文件路径列表（包含路径信息）
 */
export function collectFilesFromTree(
  nodes: FileNode[],
  basePath: string = ''
): Array<{ path: string; name: string; relativePath: string }> {
  const files: Array<{ path: string; name: string; relativePath: string }> = [];

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

  const traverse = (node: FileNode) => {
    if (!node.path) return;
    if (node.type === 'folder' && SYNC_IGNORED_FOLDERS.has(node.name)) return;

    if (node.type === 'file') {
      const relativePath = basePath ? getRelativePath(node.path, basePath) : node.name;

      files.push({
        path: node.path,
        name: node.name,
        relativePath: relativePath || node.name,
      });
    } else if (node.type === 'folder') {
      if (node.children && node.children.length > 0) {
        node.children.forEach((child) => {
          traverse(child);
        });
      }
    }
  };

  nodes.forEach((node) => {
    traverse(node);
  });

  console.log('[UploadService] collectFilesFromTree 结果:', {
    totalFiles: files.length,
    files: files.map((f) => ({ name: f.name, relativePath: f.relativePath })),
  });

  return files;
}
