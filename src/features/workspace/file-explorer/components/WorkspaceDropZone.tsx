'use client';

import React, { useCallback, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload } from 'lucide-react';

/** 从路径取文件名（兼容 / 和 \） */
function basename(filePath: string): string {
  const normalized = filePath.replace(/[/\\]+$/, '');
  const parts = normalized.split(/[/\\]/);
  return parts[parts.length - 1] || '';
}

/** 在扩展名前插入后缀，用于生成不重复文件名，如 "a (1).txt" */
function insertSuffixBeforeExt(filePath: string, suffix: string): string {
  const lastDot = filePath.lastIndexOf('.');
  if (lastDot <= 0) return filePath + suffix;
  return filePath.slice(0, lastDot) + suffix + filePath.slice(lastDot);
}

export interface WorkspaceDropZoneProps {
  /** 当前项目 workspace 目录的绝对路径（即 projectRoot/workspace） */
  workspacePath: string;
  /** 复制完成后调用，用于刷新文件树 */
  onFilesAdded?: () => void;
  /** 是否禁用（如无项目） */
  disabled?: boolean;
}

export function WorkspaceDropZone({
  workspacePath,
  onFilesAdded,
  disabled = false,
}: WorkspaceDropZoneProps) {
  const { t } = useTranslation();
  const [isCopying, setIsCopying] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounterRef = useRef(0);

  const copyFilesToWorkspace = useCallback(
    async (sourcePaths: string[]) => {
      const electron = window.electron as any;
      if (!electron?.fsCopy || !workspacePath) return;

      setIsCopying(true);
      setCopyError(null);
      let copied = 0;
      const errors: string[] = [];

      for (const sourcePath of sourcePaths) {
        const name = basename(sourcePath);
        if (!name) continue;

        let destPath = `${workspacePath.replace(/[/\\]+$/, '')}/${name}`;
        let lastError: string | null = null;

        for (let attempt = 0; attempt < 20; attempt++) {
          try {
            await electron.fsCopy(sourcePath, destPath);
            copied++;
            lastError = null;
            break;
          } catch (e: any) {
            lastError = e?.message || String(e);
            if (lastError.includes('already exists') || lastError.includes('Destination already exists')) {
              destPath = insertSuffixBeforeExt(destPath, ` (${attempt + 1})`);
            } else {
              errors.push(`${name}: ${lastError}`);
              break;
            }
          }
        }

        if (lastError && (lastError.includes('already exists') || lastError.includes('Destination already exists'))) {
          errors.push(`${basename(sourcePath)}: ${lastError}`);
        }
      }

      setIsCopying(false);
      if (errors.length > 0) {
        setCopyError(errors.slice(0, 3).join('；') + (errors.length > 3 ? '…' : ''));
        setTimeout(() => setCopyError(null), 5000);
      } else {
        setCopyError(null);
      }
      if (copied > 0) {
        onFilesAdded?.();
      }
    },
    [workspacePath, onFilesAdded]
  );

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.types.includes('Files') && !disabled) {
      setIsDragOver(true);
    }
  }, [disabled]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragOver(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragOver(false);

    if (disabled || !workspacePath) return;

    const files = Array.from(e.dataTransfer.files);
    const paths = files
      .map((f) => (f as any).path as string | undefined)
      .filter((p): p is string => !!p);

    if (paths.length > 0) {
      copyFilesToWorkspace(paths);
    }
  }, [disabled, workspacePath, copyFilesToWorkspace]);

  const hasElectron = typeof window !== 'undefined' && !!(window as any).electron;
  if (!hasElectron) return null;

  const isVisible = isDragOver || isCopying || !!copyError;

  return (
    <div
      className="flex flex-col min-w-0"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isVisible && (
        <div
          className={`
            flex items-center justify-center gap-2 py-2 px-3 mx-2 my-1 text-[11px] select-none rounded-md border border-dashed transition-colors
            ${isCopying ? 'border-orange-300 bg-orange-50/50 text-orange-600' : isDragOver ? 'border-orange-400 bg-orange-50/60 text-orange-600' : 'border-transparent'}
          `}
        >
          {isCopying ? (
            <span className="flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5 animate-pulse" />
              {t('workspace.fileExplorer.copyingToWorkspace')}
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5" />
              {t('workspace.fileExplorer.dropToCopy')}
            </span>
          )}
        </div>
      )}
      {copyError && (
        <p className="mt-1 mx-2 px-1 text-[10px] text-red-600 truncate" title={copyError}>
          {copyError}
        </p>
      )}
    </div>
  );
}
