import React from 'react';
import { createPortal } from 'react-dom';
import { X, Download, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface SyncProgressDialogProps {
  open: boolean;
  currentFileName?: string;
  downloadedCount: number;
  totalCount: number;
  progress: number; // 0-100
  error?: string; // 错误消息
  onCancel?: () => void;
  onClose?: () => void; // 关闭弹窗（用于错误时）
}

export const SyncProgressDialog: React.FC<SyncProgressDialogProps> = ({
  open,
  currentFileName,
  downloadedCount,
  totalCount,
  progress,
  error,
  onCancel,
  onClose,
}) => {
  const { t } = useTranslation();

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center font-sans">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" 
        onClick={error ? onClose : undefined}
      />
      
      {/* Dialog Panel - Quick Start style */}
      <div className="relative w-full max-w-[420px] mx-4 bg-white border border-black/[0.08] shadow-[0_8px_40px_-12px_rgba(0,0,0,0.15)] overflow-hidden transform transition-all duration-200 animate-in fade-in zoom-in-95">
        {/* Decorative corner lines */}
        <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden pointer-events-none">
          <div className="absolute top-0 right-0 w-[1px] h-10 bg-gradient-to-b from-black/10 to-transparent" />
          <div className="absolute top-0 right-0 h-[1px] w-10 bg-gradient-to-l from-black/10 to-transparent" />
        </div>
        
        {/* Header */}
        <div className="px-6 pt-6 pb-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              {/* Icon - Quick Start style square */}
              <div className={`flex-shrink-0 w-10 h-10 flex items-center justify-center transition-colors ${
                error ? 'bg-red-500/10 text-red-600' : 'bg-black/5 text-black/70'
              }`}>
                {error ? (
                  <AlertCircle className="w-5 h-5" />
                ) : (
                  <Download className="w-5 h-5" />
                )}
              </div>
              <div>
                <h3 className={`text-[15px] font-bold ${error ? 'text-red-900' : 'text-black/90'}`}>
                  {error ? t('workspace.sync.titleFailed') : t('workspace.sync.title')}
                </h3>
                <p className={`text-xs mt-1 ${error ? 'text-red-600/70' : 'text-black/50'}`}>
                  {error 
                    ? t('workspace.sync.subtitleError') 
                    : t('workspace.sync.subtitle', { downloaded: downloadedCount, total: totalCount })}
                </p>
              </div>
            </div>
            {(onCancel || onClose) && (
              <button
                onClick={error ? onClose : onCancel}
                className="p-1.5 hover:bg-black/5 transition-colors -mt-1 -mr-1"
                title={error ? t('workspace.sync.close') : t('workspace.sync.cancelSync')}
              >
                <X className="w-4 h-4 text-black/40 hover:text-black/70" />
              </button>
            )}
          </div>
        </div>

        {/* Divider */}
        <div className="mx-6 h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" />

        {/* Content */}
        <div className="px-6 py-5">
          {error ? (
            // 错误状态
            <div className="space-y-4">
              <div className="p-4 bg-red-50/50 border border-red-200/50">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-red-800 mb-1 uppercase tracking-wide">
                      {t('workspace.sync.errorDetails')}
                    </p>
                    <p className="text-sm text-red-700/80 break-words leading-relaxed">{error}</p>
                  </div>
                </div>
              </div>
              
              {/* 进度信息（即使出错也显示） */}
              {totalCount > 0 && (
                <div className="pt-3 border-t border-black/5">
                  <div className="flex items-center justify-between text-xs text-black/40">
                    <span>{t('workspace.sync.subtitle', { downloaded: downloadedCount, total: totalCount })}</span>
                    <span className="font-semibold">{progress.toFixed(0)}%</span>
                  </div>
                </div>
              )}
              
              {/* 关闭按钮 */}
              <div className="flex justify-end pt-2">
                <button
                  onClick={onClose}
                  className="group relative px-4 py-2 bg-black text-white text-xs font-semibold uppercase tracking-wider hover:bg-black/90 transition-colors overflow-hidden"
                >
                  <span>{t('workspace.sync.close')}</span>
                </button>
              </div>
            </div>
          ) : (
            // 正常同步状态
            <>
              {/* Progress Bar - minimal style */}
              <div className="mb-4">
                <div className="w-full h-1 bg-black/[0.06] overflow-hidden">
                  <div 
                    className="h-full bg-black transition-all duration-300 ease-out relative"
                    style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
                  />
                </div>
              </div>

              {/* Progress Text */}
              <div className="flex items-center justify-between">
                <span className="text-2xl font-black text-black/90 tracking-tight">
                  {progress.toFixed(0)}%
                </span>
                <span className="text-xs text-black/40 font-medium">
                  {downloadedCount} / {totalCount} {t('workspace.sync.files')}
                </span>
              </div>

              {/* Current File */}
              {currentFileName && (
                <p className="mt-3 text-xs text-black/40 truncate">
                  {currentFileName}
                </p>
              )}

              {/* Cancel button */}
              {onCancel && (
                <div className="flex justify-end mt-4">
                  <button
                    onClick={onCancel}
                    className="px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider hover:bg-black hover:text-white transition-all"
                  >
                    {t('workspace.sync.cancel')}
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {/* Bottom indicator bar on hover */}
        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black" style={{ width: error ? '100%' : `${progress}%`, transition: 'width 0.3s ease-out' }} />
      </div>
    </div>,
    document.body
  );
};

