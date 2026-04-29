import React, { useRef, useState, useCallback, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUp, Square, X, File, Folder, ImageIcon } from 'lucide-react';
import type { AgentId } from '../hooks/useChat';
import type { AttachedImage } from '../handlers/types';
import type { FileNode } from '@/features/workspace/file-explorer/types';
import { extractFilePaths, parseQuickStartMessage } from '@/features/workflow/utils/quickStartParser';
import { useChatAgents } from '../hooks/useChatAgents';
import { ComputerConflictDialog } from './ComputerConflictDialog';
import { ImagePreviewModal } from './ImagePreviewModal';
import { RichTextInput } from '@/features/workspace/components/RichTextInput';

export interface AttachedFile {
  id: string;
  path: string;
  name: string;
  type: 'file' | 'folder';
}

const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB
const ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'];

interface ChatInputProps {
  input: string;
  setInput: (value: string) => void;
  isLoading: boolean;
  isStopping: boolean;
  selectedAgentId: AgentId;
  setSelectedAgentId: (agentId: AgentId) => void;
  onSend: (message: string) => void;
  onStop: () => void;
  // 电脑选择相关
  chatId?: string;
  selectedComputer?: string;
  onComputerChange?: (computerName: string) => void;
  // 附加文件相关
  attachedFiles?: AttachedFile[];
  onRemoveFile?: (fileId: string) => void;
  // 附加图片相关
  attachedImages?: AttachedImage[];
  onAddImages?: (images: AttachedImage[]) => void;
  onRemoveImage?: (imageId: string) => void;
  // @ 文件引用相关
  fileTree?: FileNode[];
  onAddFile?: (filePath: string, fileName: string, type: 'file' | 'folder') => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  input,
  setInput,
  isLoading,
  isStopping,
  selectedAgentId,
  setSelectedAgentId,
  onSend,
  onStop,
  chatId,
  selectedComputer = 'This PC',
  onComputerChange,
  attachedFiles = [],
  onRemoveFile,
  attachedImages = [],
  onAddImages,
  onRemoveImage,
  fileTree = [],
  onAddFile,
}) => {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isAgentMenuOpen, setIsAgentMenuOpen] = useState(false);

  const [conflictDialog, setConflictDialog] = useState<{
    isOpen: boolean;
    computerName: string;
    occupiedBy: string;
  }>({ isOpen: false, computerName: '', occupiedBy: '' });

  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const { agents, loading: agentsLoading } = useChatAgents();
  const currentAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  const [agentFlash, setAgentFlash] = useState(false);
  const prevAgentIdRef = useRef(selectedAgentId);
  useEffect(() => {
    if (prevAgentIdRef.current !== selectedAgentId) {
      prevAgentIdRef.current = selectedAgentId;
      setAgentFlash(true);
      const timer = setTimeout(() => setAgentFlash(false), 1500);
      return () => clearTimeout(timer);
    }
  }, [selectedAgentId]);

  const handleComputerConflict = (computerName: string, occupiedBy: string) => {
    setConflictDialog({ isOpen: true, computerName, occupiedBy });
  };
  const handleCloseConflict = () => {
    setConflictDialog({ isOpen: false, computerName: '', occupiedBy: '' });
  };
  const handleSwitchComputer = () => handleCloseConflict();
  const handleWaitInQueue = () => handleCloseConflict();

  const fileToAttachedImage = useCallback((file: File): Promise<AttachedImage | null> => {
    return new Promise((resolve) => {
      if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) { resolve(null); return; }
      if (file.size > MAX_IMAGE_SIZE) { resolve(null); return; }
      const reader = new FileReader();
      reader.onload = () => resolve({
        id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        name: file.name || `image.${file.type.split('/')[1]}`,
        base64: reader.result as string,
        mimeType: file.type,
        size: file.size,
      });
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFileInputChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const results = await Promise.all(Array.from(files).map(fileToAttachedImage));
    const validImages = results.filter((img): img is AttachedImage => img !== null);
    if (validImages.length > 0) onAddImages?.(validImages);
    e.target.value = '';
  }, [fileToAttachedImage, onAddImages]);

  const inlineFileNames = useMemo(() => new Set(extractFilePaths(input).map(p => p.split(/[/\\]/).pop() || p)), [input]);
  const extraFiles = useMemo(() => attachedFiles.filter(f => !inlineFileNames.has(f.name)), [attachedFiles, inlineFileNames]);
  const imageNames = useMemo(() => new Set(attachedImages.map(img => img.name)), [attachedImages]);

  const displayInput = useMemo(() => {
    if (imageNames.size === 0) return input;
    return input.split('\n').map(line => {
      const segments = parseQuickStartMessage(line);
      return segments
        .filter(seg => !(seg.type === 'file' && imageNames.has(seg.name)))
        .map(seg => {
          if (seg.type === 'text') return seg.value;
          const needsQuotes = seg.path.includes(' ');
          return needsQuotes ? `@"${seg.path}"` : `@${seg.path}`;
        })
        .join('');
    }).join('\n').replace(/\s{2,}/g, ' ').trim();
  }, [input, imageNames]);

  const handleInlineFileRemove = useCallback((fileName: string) => {
    const file = attachedFiles.find(f => f.name === fileName);
    if (file) onRemoveFile?.(file.id);
  }, [attachedFiles, onRemoveFile]);

  const handlePasteFiles = useCallback(async (files: File[]) => {
    const imageFiles = files.filter(f => ACCEPTED_IMAGE_TYPES.includes(f.type) && f.size <= MAX_IMAGE_SIZE);
    if (imageFiles.length === 0) return;
    const results = await Promise.all(imageFiles.map(fileToAttachedImage));
    const valid = results.filter((img): img is AttachedImage => img !== null);
    if (valid.length > 0) onAddImages?.(valid);
  }, [fileToAttachedImage, onAddImages]);

  const handleSend = useCallback(() => { if (!isLoading) onSend(input); }, [onSend, input, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  return (
    <form
      onSubmit={handleSubmit}
      onDragOver={e => {
        e.preventDefault();
        const hasImage = Array.from(e.dataTransfer.items).some(
          item => item.kind === 'file' && ACCEPTED_IMAGE_TYPES.includes(item.type)
        );
        e.dataTransfer.dropEffect = hasImage ? 'copy' : 'none';
        setIsDragOver(hasImage);
      }}
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDragOver(false); }}
      onDrop={e => { e.preventDefault(); setIsDragOver(false); const files = Array.from(e.dataTransfer.files); if (files.length > 0) handlePasteFiles(files); }}
      className={`relative group flex flex-col rounded-lg bg-black/[0.04] transition-all duration-200 ${isDragOver ? 'ring-2 ring-orange-400/50 bg-orange-50/30' : ''}`}
    >
      {/* 隐藏的文件选择器 */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />

      {/* 输入区域 */}
      <div className="flex flex-col min-h-[40px]">
        {attachedImages.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pt-2.5 pb-1">
            {attachedImages.map((img) => {
              const src = img.url || img.base64 || '';
              return (
                <div
                  key={img.id}
                  className="relative group/img w-16 h-16 rounded-md overflow-hidden border border-gray-200 bg-gray-50 cursor-pointer"
                  onDoubleClick={() => setPreviewImage({ src, alt: img.name })}
                >
                  <img src={src} alt={img.name} className="w-full h-full object-cover" draggable={false} />
                  {onRemoveImage && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onRemoveImage(img.id); }}
                      className="absolute top-0.5 right-0.5 opacity-0 group-hover/img:opacity-100 transition-opacity p-0.5 bg-black/50 hover:bg-black/70 rounded-full flex-shrink-0"
                    >
                      <X className="w-3 h-3 text-white" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {extraFiles.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pt-2.5 pb-1">
            {extraFiles.map((file) => (
              <div
                key={file.id}
                className="inline-flex items-center gap-1.5 px-2 py-1 bg-orange-50/80 border border-orange-200/60 rounded-md text-xs text-orange-900 group/file hover:bg-orange-100/80 transition-colors"
              >
                {file.type === 'folder' ? (
                  <Folder className="w-3 h-3 flex-shrink-0 text-orange-700" />
                ) : (
                  <File className="w-3 h-3 flex-shrink-0 text-orange-700" />
                )}
                <span className="max-w-[200px] truncate font-medium">{file.name}</span>
                {onRemoveFile && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onRemoveFile(file.id); }}
                    className="opacity-0 group-hover/file:opacity-100 transition-opacity p-0.5 hover:bg-orange-200 rounded flex-shrink-0 ml-0.5"
                  >
                    <X className="w-3 h-3 text-orange-700" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        <RichTextInput
          content={displayInput}
          onChange={setInput}
          onSubmit={handleSend}
          onFileRemove={handleInlineFileRemove}
          onPasteFiles={handlePasteFiles}
          fileTree={fileTree}
          onAddFile={onAddFile}
          placeholder={t('workspace.chat.inputPlaceholder')}
          className="px-4 pt-3.5 pb-0"
        />
      </div>

      {/* 底部工具栏 */}
      <div className="flex items-end justify-between px-2.5 py-2 bg-transparent gap-2">

        {/* 左侧选择器组 - 可缩小 */}
        <div className="flex items-end min-w-0 flex-1">

        </div>

        {/* 右侧按钮组 - 固定不缩小 */}
        <div className="flex items-end gap-1 flex-shrink-0">
          {/* 图片上传 */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-7 h-7 rounded-md flex items-center justify-center text-black/40 hover:text-black/70 hover:bg-black/5 transition-colors"
            title="上传图片 (也可直接粘贴)"
          >
            <ImageIcon className="w-4 h-4" />
          </button>

          {/* 发送/停止按钮 */}
          {isLoading && selectedAgentId.startsWith('workflow:') ? (
            <button
              type="button"
              onClick={onStop}
              disabled={isStopping}
              className={`
                w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 transition-all duration-200
                bg-red-500 text-white hover:bg-red-600
                ${isStopping ? 'opacity-50 cursor-not-allowed' : ''}
              `}
              title="停止任务"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={(!input.trim() && attachedFiles.length === 0 && attachedImages.length === 0) || isLoading}
              className={`
                w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 transition-all duration-200
                ${(input.trim() || attachedFiles.length > 0 || attachedImages.length > 0) && !isLoading
                  ? 'bg-[#FF4D00] text-white hover:bg-[#E64500] shadow-sm'
                  : 'bg-black/10 text-black/25 cursor-not-allowed'
                }
              `}
            >
              <ArrowUp className="w-4 h-4 stroke-[2.5px]" />
            </button>
          )}
        </div>
      </div>

      {/* 电脑冲突对话框 */}
      <ComputerConflictDialog
        isOpen={conflictDialog.isOpen}
        computerName={conflictDialog.computerName}
        occupiedBy={conflictDialog.occupiedBy}
        onClose={handleCloseConflict}
        onSwitchComputer={handleSwitchComputer}
        onWaitInQueue={handleWaitInQueue}
      />

      {/* 图片预览弹窗 */}
      {previewImage && (
        <ImagePreviewModal
          src={previewImage.src}
          alt={previewImage.alt}
          onClose={() => setPreviewImage(null)}
        />
      )}
    </form>
  );
};
