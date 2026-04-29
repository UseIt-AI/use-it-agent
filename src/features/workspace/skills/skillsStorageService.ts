/**
 * Skills 本地目录扫描与元数据收集。
 * 项目与 Skills 均位于用户本机 projects / 配置目录，不再走 S3 预签名上传/同步。
 */

function guessContentType(filename: string): string {
  const ext = filename.toLowerCase().split('.').pop() || '';
  const mimeTypes: Record<string, string> = {
    txt: 'text/plain',
    md: 'text/markdown',
    json: 'application/json',
    py: 'text/x-python',
    js: 'text/javascript',
    ts: 'text/typescript',
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
    pdf: 'application/pdf',
    zip: 'application/zip',
  };
  return mimeTypes[ext] || 'application/octet-stream';
}

function normalizePath(p: string): string {
  return p.replace(/\\/g, '/');
}

function getRelativePath(absolutePath: string, basePath: string): string {
  const normalizedAbs = normalizePath(absolutePath);
  const normalizedBase = normalizePath(basePath).replace(/\/+$/, '');
  if (!normalizedAbs.startsWith(normalizedBase)) {
    return absolutePath.split(/[/\\]/).pop() || '';
  }
  return normalizedAbs.slice(normalizedBase.length).replace(/^\//, '');
}

export interface SkillsFileInfo {
  filename: string;
  path?: string;
  content_type?: string;
  size_bytes?: number;
  etag?: string;
  last_modified?: string;
}

/**
 * 递归扫描 skills 目录，收集所有文件信息
 */
export async function collectSkillsFiles(
  rootPath: string
): Promise<Array<{ absolutePath: string; relativePath: string; name: string }>> {
  const electron = window.electron as any;
  if (!electron?.fsReadDirectoryRecursive && !electron?.fsReadDirectory) {
    throw new Error('File system API not available');
  }

  const files: Array<{ absolutePath: string; relativePath: string; name: string }> = [];

  const scanDir = async (dirPath: string) => {
    const children: Array<{ name: string; type: 'file' | 'folder' }> = await electron.fsReadDirectory(dirPath);
    for (const child of children) {
      const sep = dirPath.includes('\\') ? '\\' : '/';
      const childPath = `${dirPath}${sep}${child.name}`;
      if (child.type === 'file') {
        files.push({
          absolutePath: childPath,
          relativePath: getRelativePath(childPath, rootPath),
          name: child.name,
        });
      } else if (child.type === 'folder') {
        await scanDir(childPath);
      }
    }
  };

  await scanDir(rootPath);
  return files;
}

/**
 * 收集 skills 文件并附加 ETag/元数据
 */
export async function collectSkillsFilesWithMetadata(
  rootPath: string
): Promise<{ files: SkillsFileInfo[]; rawFiles: Array<{ absolutePath: string; relativePath: string; name: string }> }> {
  const rawFiles = await collectSkillsFiles(rootPath);
  const electron = window.electron as any;

  const files: SkillsFileInfo[] = await Promise.all(
    rawFiles.map(async (file) => {
      let etag: string | undefined;
      let sizeBytes: number | undefined;
      let lastModified: string | undefined;
      try {
        if (electron?.getFileMetadata) {
          const metadata = (await electron.getFileMetadata(file.absolutePath)) as {
            size?: number;
            lastModified?: number;
            etag?: string;
          } | null;
          if (metadata) {
            etag = metadata.etag;
            sizeBytes = metadata.size;
            if (metadata.lastModified) {
              lastModified = new Date(metadata.lastModified).toISOString();
            }
          }
        }
      } catch {
        // ignore metadata errors
      }
      return {
        filename: file.name,
        path: file.relativePath || file.name,
        content_type: guessContentType(file.name),
        etag,
        size_bytes: sizeBytes,
        last_modified: lastModified,
      };
    })
  );

  return { files, rawFiles };
}
