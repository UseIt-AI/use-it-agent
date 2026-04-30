/**
 * SyncStatusCard - 文件同步状态卡片（在聊天中显示）
 * 用于显示文件同步进度和删除确认选项
 */

import React, { useState } from 'react';
import { Download, Upload, Monitor, Cloud, ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LoadingSpinner } from './StatusIcons';
import type { DeletedFileInfo } from '@/features/workspace/file-explorer/services/uploadService';

// ==================== 同步进度卡片 ====================

export interface SyncProgressInfo {
  type: 'upload' | 'download';
  currentFileName?: string;
  completedCount: number;
  totalCount: number;
  progress: number; // 0-100
  error?: string;
}

interface SyncProgressCardProps {
  info: SyncProgressInfo;
  onCancel?: () => void;
}

export const SyncProgressCard: React.FC<SyncProgressCardProps> = ({
  info,
  onCancel,
}) => {
  const { t } = useTranslation();
  const isUpload = info.type === 'upload';
  const Icon = isUpload ? Upload : Download;
  
  return (
    <div className="border border-black/[0.08] bg-white overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-300">
      {/* Header */}
      <div className="px-4 py-3 flex items-center gap-3">
        <div className={`flex-shrink-0 w-8 h-8 flex items-center justify-center ${
          info.error ? 'bg-red-50 text-red-600' : 'bg-black/5 text-black/70'
        }`}>
          {info.error ? (
            <Icon className="w-4 h-4" />
          ) : (
            <LoadingSpinner size="sm" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-semibold ${info.error ? 'text-red-800' : 'text-black/80'}`}>
            {info.error 
              ? (isUpload ? t('workspace.upload.titleFailed') : t('workspace.sync.titleFailed'))
              : (isUpload ? t('workspace.upload.title') : t('workspace.sync.title'))}
          </div>
          <div className="text-xs text-black/50 mt-0.5">
            {info.error 
              ? t('workspace.sync.subtitleError')
              : t('workspace.sync.subtitle', { downloaded: info.completedCount, total: info.totalCount })}
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      {!info.error && (
        <div className="px-4 pb-3">
          <div className="w-full h-1 bg-black/[0.06] overflow-hidden">
            <div 
              className="h-full bg-black transition-all duration-300 ease-out"
              style={{ width: `${Math.max(0, Math.min(100, info.progress))}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-black/40 truncate max-w-[60%]">
              {info.currentFileName || ''}
            </span>
            <span className="text-xs font-semibold text-black/60">
              {info.progress.toFixed(0)}%
            </span>
          </div>
        </div>
      )}

      {/* Error */}
      {info.error && (
        <div className="px-4 pb-3">
          <div className="p-3 bg-red-50/50 border border-red-200/50 text-xs text-red-700/80">
            {info.error}
          </div>
        </div>
      )}

      {/* Cancel Button */}
      {onCancel && !info.error && (
        <div className="px-4 pb-3 flex justify-end">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider hover:bg-black hover:text-white transition-all"
          >
            {t('workspace.sync.cancel')}
          </button>
        </div>
      )}

      {/* Bottom indicator bar */}
      <div 
        className="h-[2px] bg-black transition-all duration-300" 
        style={{ width: info.error ? '100%' : `${info.progress}%` }} 
      />
    </div>
  );
};

// ==================== 删除确认卡片 ====================

// 从 uploadService 重新导出 DeletedFileInfo 类型
export type { DeletedFileInfo } from '@/features/workspace/file-explorer/services/uploadService';

interface DeleteConfirmationCardProps {
  deletedFiles: DeletedFileInfo[];
  onConfirm: (shouldDelete: boolean) => void;
  onCancel: () => void;
}

export const DeleteConfirmationCard: React.FC<DeleteConfirmationCardProps> = ({
  deletedFiles,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<'local' | 'cloud'>('local');
  const [isExpanded, setIsExpanded] = useState(false);

  const handleConfirm = () => {
    // local = 以本地为准 = 覆盖上传（删除云端多余文件）
    // cloud = 以云端为准 = 增量上传（保留云端文件）
    onConfirm(selected === 'local');
  };

  return (
    <div className="border border-black/[0.08] bg-white overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-300">
      {/* Header */}
      <div className="px-4 py-3">
        <div className="text-sm font-semibold text-black/80">
          {t('workspace.uploadConfirm.title')}
        </div>
        <div className="mt-2 p-2.5 bg-black/[0.03] border border-black/[0.06]">
          <p className="text-xs font-medium text-black/70">
            {t('workspace.uploadConfirm.description', { count: deletedFiles.length })}
          </p>
          <p className="text-[10px] text-black/40 mt-1">
            {t('workspace.uploadConfirm.hint')}
          </p>
        </div>
      </div>

      {/* Options */}
      <div className="px-4 pb-3">
        <div className="grid grid-cols-2 gap-2">
          {/* Local Version */}
          <button
            onClick={() => setSelected('local')}
            className={`group relative p-3 border text-left transition-all overflow-hidden ${
              selected === 'local' 
                ? 'border-black bg-black/[0.02]' 
                : 'border-black/[0.08] hover:border-black/20'
            }`}
          >
            {selected === 'local' && (
              <div className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-black" />
            )}
            <div className="flex items-center gap-1.5">
              <Monitor className="w-3.5 h-3.5 text-black/60" />
              <span className="text-xs font-semibold text-black/80">
                {t('workspace.uploadConfirm.localTitle')}
              </span>
            </div>
            <div 
              className="absolute bottom-0 left-0 right-0 h-[2px] bg-black transition-opacity" 
              style={{ opacity: selected === 'local' ? 1 : 0 }} 
            />
          </button>

          {/* Cloud Version */}
          <button
            onClick={() => setSelected('cloud')}
            className={`group relative p-3 border text-left transition-all overflow-hidden ${
              selected === 'cloud' 
                ? 'border-black bg-black/[0.02]' 
                : 'border-black/[0.08] hover:border-black/20'
            }`}
          >
            {selected === 'cloud' && (
              <div className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-black" />
            )}
            <div className="flex items-center gap-1.5">
              <Cloud className="w-3.5 h-3.5 text-black/60" />
              <span className="text-xs font-semibold text-black/80">
                {t('workspace.uploadConfirm.cloudTitle')}
              </span>
            </div>
            <div 
              className="absolute bottom-0 left-0 right-0 h-[2px] bg-black transition-opacity" 
              style={{ opacity: selected === 'cloud' ? 1 : 0 }} 
            />
          </button>
        </div>
      </div>

      {/* File List - Collapsible */}
      <div className="px-4 pb-3">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold text-black/50 hover:text-black/70 transition-colors"
        >
          {selected === 'local' 
            ? t('workspace.uploadConfirm.filesWillDelete', { count: deletedFiles.length })
            : t('workspace.uploadConfirm.filesWillKeep', { count: deletedFiles.length })}
          {isExpanded ? (
            <ChevronUp className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
        </button>
        
        {isExpanded && (
          <div className="mt-2 border border-black/[0.06] max-h-[120px] overflow-y-auto">
            {deletedFiles.map((file, index) => (
              <div
                key={file.s3_key || index}
                className="px-2.5 py-1.5 text-[10px] text-black/60 truncate border-b border-black/[0.04] last:border-b-0"
              >
                {file.filename || file.path || file.s3_key.split('/').pop() || t('workspace.uploadConfirm.unknownFile')}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-black/5 flex items-center justify-between">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider hover:bg-black hover:text-white transition-all"
        >
          {t('workspace.uploadConfirm.cancel')}
        </button>
        <button
          onClick={handleConfirm}
          className="px-3 py-1.5 bg-black text-white text-[10px] font-semibold uppercase tracking-wider hover:bg-black/90 transition-colors"
        >
          {t('workspace.uploadConfirm.confirm')}
        </button>
      </div>

      {/* Bottom indicator bar */}
      <div className="h-[2px] bg-black" />
    </div>
  );
};
