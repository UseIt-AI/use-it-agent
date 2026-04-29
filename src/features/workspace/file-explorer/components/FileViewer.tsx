'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { Loader2, AlertCircle, ChevronRight, FileText, Folder } from 'lucide-react';
import clsx from 'clsx';
import { useProject } from '@/contexts/ProjectContext';

const LANGUAGE_MAP: Record<string, string> = {
  '.json': 'json', '.js': 'javascript', '.jsx': 'javascript',
  '.ts': 'typescript', '.tsx': 'typescript', '.py': 'python',
  '.html': 'html', '.htm': 'html', '.css': 'css', '.scss': 'scss',
  '.less': 'less', '.md': 'markdown', '.xml': 'xml',
  '.yaml': 'yaml', '.yml': 'yaml', '.sql': 'sql',
  '.sh': 'shell', '.bash': 'shell', '.bat': 'bat', '.ps1': 'powershell',
  '.c': 'c', '.cpp': 'cpp', '.h': 'c', '.hpp': 'cpp',
  '.java': 'java', '.go': 'go', '.rs': 'rust', '.rb': 'ruby',
  '.php': 'php', '.swift': 'swift', '.kt': 'kotlin',
  '.r': 'r', '.lua': 'lua', '.ini': 'ini', '.toml': 'ini',
  '.dockerfile': 'dockerfile', '.graphql': 'graphql', '.gql': 'graphql',
};

function getLanguageFromFileName(name: string): string {
  const lower = name.toLowerCase();
  if (lower === 'dockerfile') return 'dockerfile';
  const ext = lower.slice(lower.lastIndexOf('.'));
  return LANGUAGE_MAP[ext] || 'plaintext';
}

interface FileViewerProps {
  filePath: string;
  fileName: string;
  onClose?: () => void;
  onFileOpen?: (filePath: string, fileName: string) => void;
}

interface DirectoryEntry {
  name: string;
  type: 'folder' | 'file';
  path: string;
  size?: number;
  modified?: number;
}

export function FileViewer({ filePath, fileName, onClose, onFileOpen }: FileViewerProps) {
  const { currentProject } = useProject();
  const [content, setContent] = useState<string | null>(null);
  const [originalContent, setOriginalContent] = useState<string | null>(null);
  const [fileType, setFileType] = useState<'text' | 'image' | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [encoding, setEncoding] = useState<string>('utf8');
  const [fileSize, setFileSize] = useState<number>(0);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved');
  const [projectRootPath, setProjectRootPath] = useState<string | null>(null);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // 下拉菜单状态
  const [dropdownOpen, setDropdownOpen] = useState<number | null>(null); // 哪个路径段的索引
  const [dropdownEntries, setDropdownEntries] = useState<DirectoryEntry[]>([]);
  const [isLoadingDirectory, setIsLoadingDirectory] = useState(false);
  const [isOpeningExternally, setIsOpeningExternally] = useState(false);
  const [openExternalError, setOpenExternalError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const breadcrumbRefs = useRef<(HTMLSpanElement | null)[]>([]);

  const handleEditorBeforeMount = useCallback((monaco: any) => {
    monaco.editor.defineTheme('useit-file-viewer', {
      base: 'vs',
      inherit: true,
      rules: [],
      colors: {
        // Use solid fill highlight for active line.
        'editor.lineHighlightBackground': '#EAF2FF',
        // Remove the default outline/border style.
        'editor.lineHighlightBorder': '#00000000',
      },
    });
  }, []);

  // 获取项目根目录路径
  useEffect(() => {
    const loadProjectRoot = async () => {
      if (!currentProject?.id) {
        setProjectRootPath(null);
        return;
      }

      try {
        const electron = window.electron as any;
        if (electron?.fsGetProjectRoot) {
          const rootPath = await electron.fsGetProjectRoot(currentProject.id);
          setProjectRootPath(rootPath);
        }
      } catch (err: any) {
        console.error('Failed to get project root path:', err);
        setProjectRootPath(null);
      }
    };

    loadProjectRoot();
  }, [currentProject?.id]);

  useEffect(() => {
    const loadFile = async () => {
      setIsLoading(true);
      setError(null);
      
      try {
        const electron = window.electron as any;
        if (!electron?.fsReadFile) {
          throw new Error('File reading API not available');
        }

        const result = await electron.fsReadFile(filePath);
        setContent(result.content);
        setOriginalContent(result.content);
        setFileType(result.type);
        setEncoding(result.encoding || 'utf8');
        setFileSize(result.size || 0);
        setHasUnsavedChanges(false);
        setSaveStatus('saved');
      } catch (err: any) {
        console.error('Failed to load file:', err);
        setError(err.message || 'Failed to load file');
      } finally {
        setIsLoading(false);
      }
    };

    if (filePath) {
      loadFile();
    }
  }, [filePath]);

  // 将绝对路径转换为相对于项目根目录的路径
  const getRelativePath = useCallback((absolutePath: string, rootPath: string | null): string => {
    if (!rootPath) {
      return absolutePath;
    }

    // 标准化路径（统一使用正斜杠）
    const normalizedAbsolute = absolutePath.replace(/\\/g, '/');
    const normalizedRoot = rootPath.replace(/\\/g, '/');

    // 确保根路径以 / 结尾（用于匹配）
    const rootWithSlash = normalizedRoot.endsWith('/') ? normalizedRoot : normalizedRoot + '/';

    // 如果文件路径以根路径开头，提取相对路径
    if (normalizedAbsolute.startsWith(rootWithSlash)) {
      return normalizedAbsolute.slice(rootWithSlash.length);
    } else if (normalizedAbsolute === normalizedRoot) {
      // 如果文件路径就是根路径，返回空字符串（但这种情况不应该发生，因为文件应该在项目内）
      return '';
    }

    // 如果无法匹配，返回原路径（可能是项目外的文件）
    return absolutePath;
  }, []);

  // 解析文件路径为面包屑路径（显示相对路径）
  const getBreadcrumbPath = useCallback((absolutePath: string, rootPath: string | null): string[] => {
    // 获取相对路径
    const relativePath = getRelativePath(absolutePath, rootPath);
    
    // 如果相对路径为空，返回项目名称
    if (!relativePath) {
      return currentProject ? [currentProject.name] : [];
    }

    // 如果相对路径等于绝对路径（无法匹配项目根路径），尝试简化显示
    if (relativePath === absolutePath) {
      // 如果无法匹配，至少显示最后几个路径段（最多显示最后4段）
      const normalizedPath = absolutePath.replace(/\\/g, '/');
      const parts = normalizedPath.split('/').filter(Boolean);
      if (parts.length > 4) {
        // 显示前2段（通常是盘符和主要目录）和最后2段
        return ['...', ...parts.slice(-3)];
      }
      return parts;
    }

    // 处理 Windows 和 Unix 路径
    const normalizedPath = relativePath.replace(/\\/g, '/');
    const parts = normalizedPath.split('/').filter(Boolean);
    
    // 如果项目根路径存在，在开头添加项目名称
    if (rootPath && currentProject) {
      return [currentProject.name, ...parts];
    }
    
    return parts;
  }, [getRelativePath, currentProject]);

  // 根据路径段索引计算绝对路径
  const getAbsolutePathForBreadcrumb = useCallback((index: number, breadcrumbParts: string[], rootPath: string | null): string | null => {
    if (!rootPath || !currentProject) {
      return null;
    }

    // 如果点击的是项目名称（索引0），返回项目根路径
    if (index === 0) {
      return rootPath;
    }

    // 构建到该路径段的相对路径
    const relativeParts = breadcrumbParts.slice(1, index + 1); // 跳过项目名称
    if (relativeParts.length === 0) {
      return rootPath;
    }

    // 组合路径（处理 Windows 和 Unix）
    const separator = rootPath.includes('\\') ? '\\' : '/';
    const relativePath = relativeParts.join(separator);
    return `${rootPath}${separator}${relativePath}`;
  }, [currentProject]);

  // 加载目录内容
  const loadDirectory = useCallback(async (dirPath: string) => {
    setIsLoadingDirectory(true);
    try {
      const electron = window.electron as any;
      if (!electron?.fsReadDirectory) {
        throw new Error('Directory reading API not available');
      }

      const entries = await electron.fsReadDirectory(dirPath);
      setDropdownEntries(entries || []);
    } catch (err: any) {
      console.error('Failed to load directory:', err);
      setDropdownEntries([]);
    } finally {
      setIsLoadingDirectory(false);
    }
  }, []);

  // 处理路径段点击
  const handleBreadcrumbClick = useCallback(async (index: number, breadcrumbParts: string[]) => {
    // 如果是最后一个路径段（文件名），不显示下拉菜单
    if (index === breadcrumbParts.length - 1) {
      return;
    }

    const absolutePath = getAbsolutePathForBreadcrumb(index, breadcrumbParts, projectRootPath);
    if (!absolutePath) {
      return;
    }

    // 如果点击的是当前打开的下拉菜单，关闭它
    if (dropdownOpen === index) {
      setDropdownOpen(null);
      return;
    }

    // 打开新的下拉菜单
    setDropdownOpen(index);
    await loadDirectory(absolutePath);
  }, [dropdownOpen, projectRootPath, getAbsolutePathForBreadcrumb, loadDirectory]);

  // 处理从下拉菜单选择文件
  const handleSelectFile = useCallback((entry: DirectoryEntry) => {
    if (entry.type === 'file' && onFileOpen) {
      onFileOpen(entry.path, entry.name);
      setDropdownOpen(null);
    }
  }, [onFileOpen]);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        // 检查是否点击在面包屑上
        const clickedBreadcrumb = breadcrumbRefs.current.some(ref => 
          ref && ref.contains(event.target as Node)
        );
        if (!clickedBreadcrumb) {
          setDropdownOpen(null);
        }
      }
    };

    if (dropdownOpen !== null) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [dropdownOpen]);

  // 自动保存函数（带 debounce）
  const autoSave = useCallback(async (contentToSave: string) => {
    if (!contentToSave || !filePath || fileType !== 'text') return;
    if (contentToSave === originalContent) {
      setHasUnsavedChanges(false);
      setSaveStatus('saved');
      return;
    }

    setIsSaving(true);
    setSaveStatus('saving');
    
    try {
      const electron = window.electron as any;
      if (!electron?.fsWriteFile) {
        throw new Error('File writing API not available');
      }

      await electron.fsWriteFile(filePath, contentToSave, encoding);
      
      // 更新原始内容
      setOriginalContent(contentToSave);
      setHasUnsavedChanges(false);
      setSaveStatus('saved');
      
      // 更新文件大小
      const newSize = new Blob([contentToSave]).size;
      setFileSize(newSize);
    } catch (err: any) {
      console.error('Failed to save file:', err);
      setSaveStatus('unsaved');
      // 不显示 alert，避免打断用户编辑
    } finally {
      setIsSaving(false);
    }
  }, [filePath, encoding, fileType, originalContent]);

  const handleContentChange = useCallback((value: string | undefined) => {
    const newContent = value ?? '';
    setContent(newContent);
    setHasUnsavedChanges(newContent !== originalContent);
    setSaveStatus('unsaved');

    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    saveTimeoutRef.current = setTimeout(() => {
      autoSave(newContent);
    }, 1000);
  }, [originalContent, autoSave]);

  const handleClose = () => {
    // 如果有未保存的更改，先保存
    if (hasUnsavedChanges && content !== null) {
      // 清除定时器，立即保存
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      autoSave(content).then(() => {
        onClose?.();
      });
    } else {
      onClose?.();
    }
  };

  // 清理定时器
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  // 当文件路径变化时，重置状态
  useEffect(() => {
    setHasUnsavedChanges(false);
    setSaveStatus('saved');
    setDropdownOpen(null); // 关闭下拉菜单
    setOpenExternalError(null);
    setIsOpeningExternally(false);
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
  }, [filePath]);

  const isUnsupportedPreview = Boolean(
    error && /not supported for preview/i.test(error)
  );

  const handleOpenWithDefaultApplication = useCallback(async () => {
    try {
      setIsOpeningExternally(true);
      setOpenExternalError(null);
      const electron = window.electron as any;
      if (electron?.fsOpenWithDefaultApp) {
        await electron.fsOpenWithDefaultApp(filePath);
        return;
      }
      // Backward compatibility for running clients that haven't reloaded preload yet.
      if (electron?.fsShowInFolder) {
        await electron.fsShowInFolder(filePath);
        setOpenExternalError('Opened in file manager. Restart the app to enable direct open with default application.');
        return;
      }
      throw new Error('Unable to access desktop integration APIs in the current session. Please restart the app.');
    } catch (err: any) {
      setOpenExternalError(err?.message || 'Failed to open the file with the default application.');
    } finally {
      setIsOpeningExternally(false);
    }
  }, [filePath]);

  if (isLoading) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center bg-canvas">
        <Loader2 className="w-6 h-6 text-black/40 animate-spin mb-2" />
        <span className="text-sm text-black/60">加载文件中...</span>
      </div>
    );
  }

  if (error) {
    if (isUnsupportedPreview) {
      return (
        <div className="h-full w-full flex flex-col items-center justify-center bg-canvas p-4">
          <AlertCircle className="w-8 h-8 text-amber-500 mb-3" />
          <div className="text-sm text-black/80 text-center max-w-md">
            This file format cannot be previewed in-app.
          </div>
          <div className="text-xs text-black/50 text-center max-w-md mt-1">
            Open it with your system&apos;s default desktop application.
          </div>
          <button
            onClick={handleOpenWithDefaultApplication}
            disabled={isOpeningExternally}
            className="mt-4 inline-flex items-center gap-2 px-3 py-2 text-xs bg-black/5 hover:bg-black/10 rounded-md transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isOpeningExternally && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Open with Default Application
          </button>
          {openExternalError && (
            <div className="text-xs text-red-600 text-center max-w-md mt-2">{openExternalError}</div>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="mt-2 px-3 py-1.5 text-xs text-black/60 hover:text-black/80 transition-colors"
            >
              Close
            </button>
          )}
        </div>
      );
    }

    return (
      <div className="h-full w-full flex flex-col items-center justify-center bg-canvas p-4">
        <AlertCircle className="w-8 h-8 text-red-500 mb-3" />
        <div className="text-sm text-red-600 text-center max-w-md">{error}</div>
        {onClose && (
          <button
            onClick={onClose}
            className="mt-4 px-4 py-2 text-xs bg-black/5 hover:bg-black/10 rounded-md transition-colors"
          >
            关闭
          </button>
        )}
      </div>
    );
  }

  const breadcrumbPath = getBreadcrumbPath(filePath, projectRootPath);

  return (
    <div className="h-full w-full flex flex-col bg-canvas relative">
      {/* 文件路径面包屑（类似 Cursor） */}
      <div className="flex items-center gap-1 px-3 h-[28px] bg-[#FAF9F6] border-b border-divider flex-shrink-0 text-[11px] relative">
        {breadcrumbPath.map((part, index) => {
          const isLast = index === breadcrumbPath.length - 1;
          const isDropdownOpen = dropdownOpen === index;
          
          return (
            <React.Fragment key={index}>
              {index > 0 && (
                <ChevronRight className="w-3 h-3 text-black/30 flex-shrink-0" />
              )}
              <span
                ref={(el) => {
                  breadcrumbRefs.current[index] = el;
                }}
                onClick={() => !isLast && handleBreadcrumbClick(index, breadcrumbPath)}
                className={clsx(
                  'truncate max-w-[200px] px-1 py-0.5 rounded transition-colors',
                  isLast
                    ? 'text-black/90 font-medium'
                    : 'text-black/60 hover:text-black/80 hover:bg-black/5 cursor-pointer',
                  isDropdownOpen && 'bg-black/10 text-black/90'
                )}
                title={part}
              >
                {part}
              </span>
            </React.Fragment>
          );
        })}
        
        {/* 下拉菜单 */}
        {dropdownOpen !== null && breadcrumbRefs.current[dropdownOpen] && (
          <div
            ref={dropdownRef}
            className="absolute top-full mt-1 bg-white border border-divider rounded-md shadow-lg z-50 max-h-[300px] overflow-y-auto min-w-[200px] scrollbar-thin"
            style={{
              left: `${breadcrumbRefs.current[dropdownOpen]!.offsetLeft}px`,
            }}
          >
            {isLoadingDirectory ? (
              <div className="flex items-center justify-center p-4">
                <Loader2 className="w-4 h-4 animate-spin text-black/40" />
              </div>
            ) : dropdownEntries.length === 0 ? (
              <div className="px-3 py-2 text-[11px] text-black/40">空文件夹</div>
            ) : (
              <div className="py-1">
                {dropdownEntries.map((entry, idx) => (
                  <div
                    key={idx}
                    onClick={() => handleSelectFile(entry)}
                    className={clsx(
                      'flex items-center gap-2 px-3 py-1.5 text-[11px] cursor-pointer transition-colors',
                      entry.type === 'file'
                        ? 'hover:bg-orange-50 hover:text-orange-700 text-black/80'
                        : 'text-black/60 hover:bg-black/5'
                    )}
                  >
                    {entry.type === 'folder' ? (
                      <Folder className="w-3.5 h-3.5 text-black/50 flex-shrink-0" />
                    ) : (
                      <FileText className="w-3.5 h-3.5 text-black/50 flex-shrink-0" />
                    )}
                    <span className="truncate flex-1">{entry.name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {/* 保存状态指示器 */}
        {fileType === 'text' && (
          <div className="ml-auto flex items-center gap-2">
            {saveStatus === 'saving' && (
              <div className="flex items-center gap-1.5 text-[10px] text-black/50">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>保存中...</span>
              </div>
            )}
            {saveStatus === 'saved' && !hasUnsavedChanges && (
              <div className="flex items-center gap-1.5 text-[10px] text-black/40">
                <span>已保存</span>
              </div>
            )}
            {saveStatus === 'unsaved' && hasUnsavedChanges && (
              <div className="flex items-center gap-1.5 text-[10px] text-orange-600">
                <span>●</span>
                <span>未保存</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 文件内容区域 */}
      <div className="flex-1 min-h-0 bg-white relative">
        {fileType === 'image' && content ? (
          <div className="h-full w-full flex items-center justify-center p-4">
            <img
              src={content}
              alt={fileName}
              className="max-w-full max-h-full object-contain"
            />
          </div>
        ) : fileType === 'text' && content !== null ? (
          <Editor
            height="100%"
            language={getLanguageFromFileName(fileName)}
            value={content}
            onChange={handleContentChange}
            beforeMount={handleEditorBeforeMount}
            theme="useit-file-viewer"
            loading={
              <div className="h-full w-full flex items-center justify-center">
                <Loader2 className="w-5 h-5 text-black/40 animate-spin" />
              </div>
            }
            options={{
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: 'on',
              wordWrap: 'on',
              automaticLayout: true,
              scrollBeyondLastLine: false,
              folding: true,
              formatOnPaste: true,
              tabSize: 2,
              renderLineHighlight: 'line',
              smoothScrolling: true,
              cursorBlinking: 'smooth',
              cursorSmoothCaretAnimation: 'on',
              padding: { top: 8, bottom: 8 },
              scrollbar: {
                verticalScrollbarSize: 8,
                horizontalScrollbarSize: 8,
              },
            }}
          />
        ) : (
          <div className="h-full w-full flex items-center justify-center text-black/40">
            <span className="text-sm">无法预览此文件类型</span>
          </div>
        )}
      </div>
    </div>
  );
}

