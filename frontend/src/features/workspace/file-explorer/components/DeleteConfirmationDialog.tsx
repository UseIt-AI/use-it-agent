import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Monitor, Cloud } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { DeletedFileInfo } from '../services/uploadService';

interface DeleteConfirmationDialogProps {
  open: boolean;
  deletedFiles: DeletedFileInfo[];
  onConfirm: (shouldDelete: boolean) => void;
  onCancel: () => void;
}

export const DeleteConfirmationDialog: React.FC<DeleteConfirmationDialogProps> = ({
  open,
  deletedFiles,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<'local' | 'cloud'>('local');
  
  if (!open) return null;

  const handleConfirm = () => {
    // local = 以本地为准 = 覆盖上传（删除云端多余文件）
    // cloud = 以云端为准 = 增量上传（保留云端文件）
    onConfirm(selected === 'local');
  };

  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-center justify-center font-sans">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" />
      
      {/* Dialog Panel - Quick Start style */}
      <div className="relative w-full max-w-[520px] mx-4 bg-white border border-black/[0.08] shadow-[0_8px_40px_-12px_rgba(0,0,0,0.15)] overflow-hidden transform transition-all duration-200 animate-in fade-in zoom-in-95 flex flex-col max-h-[80vh]">
        {/* Decorative corner lines */}
        <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden pointer-events-none">
          <div className="absolute top-0 right-0 w-[1px] h-10 bg-gradient-to-b from-black/10 to-transparent" />
          <div className="absolute top-0 right-0 h-[1px] w-10 bg-gradient-to-l from-black/10 to-transparent" />
        </div>
        
        {/* Header */}
        <div className="px-6 pt-6 pb-4 flex-shrink-0">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-[15px] font-bold text-black/90">
                {t('workspace.uploadConfirm.title')}
              </h3>
            </div>
            <button
              onClick={onCancel}
              className="p-1.5 hover:bg-black/5 transition-colors -mt-1 -mr-1"
            >
              <X className="w-4 h-4 text-black/40 hover:text-black/70" />
            </button>
          </div>
          {/* Problem description - prominent */}
          <div className="mt-3 p-3 bg-black/[0.03] border border-black/[0.06]">
            <p className="text-sm font-medium text-black/80">
              {t('workspace.uploadConfirm.description', { count: deletedFiles.length })}
            </p>
            <p className="text-xs text-black/40 mt-1">
              {t('workspace.uploadConfirm.hint')}
            </p>
          </div>
        </div>

        {/* Divider */}
        <div className="mx-6 h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent flex-shrink-0" />

        {/* Content */}
        <div className="px-6 py-5 overflow-y-auto flex-1">
          {/* Version Selection - Left/Right comparison */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            {/* Local Version */}
            <button
              onClick={() => setSelected('local')}
              className={`group relative p-4 border text-left transition-all overflow-hidden ${
                selected === 'local' 
                  ? 'border-black bg-black/[0.02]' 
                  : 'border-black/[0.06] hover:border-black/20'
              }`}
            >
              {/* Selected indicator */}
              {selected === 'local' && (
                <div className="absolute top-2 right-2 w-2 h-2 bg-black" />
              )}
              
              <div className="flex items-center gap-2">
                <Monitor className="w-4 h-4 text-black/60" />
                <span className="text-sm font-bold text-black/80">
                  {t('workspace.uploadConfirm.localTitle')}
                </span>
              </div>
              
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black" style={{ opacity: selected === 'local' ? 1 : 0 }} />
            </button>

            {/* Cloud Version */}
            <button
              onClick={() => setSelected('cloud')}
              className={`group relative p-4 border text-left transition-all overflow-hidden ${
                selected === 'cloud' 
                  ? 'border-black bg-black/[0.02]' 
                  : 'border-black/[0.06] hover:border-black/20'
              }`}
            >
              {/* Selected indicator */}
              {selected === 'cloud' && (
                <div className="absolute top-2 right-2 w-2 h-2 bg-black" />
              )}
              
              <div className="flex items-center gap-2">
                <Cloud className="w-4 h-4 text-black/60" />
                <span className="text-sm font-bold text-black/80">
                  {t('workspace.uploadConfirm.cloudTitle')}
                </span>
              </div>
              
              <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black" style={{ opacity: selected === 'cloud' ? 1 : 0 }} />
            </button>
          </div>

          {/* File List */}
          <div>
            <p className="text-[10px] uppercase tracking-wider font-semibold mb-2 text-black/70">
              {selected === 'local' 
                ? t('workspace.uploadConfirm.filesWillDelete', { count: deletedFiles.length })
                : t('workspace.uploadConfirm.filesWillKeep', { count: deletedFiles.length })}
            </p>
            <div className="border border-black/[0.06] max-h-[160px] overflow-y-auto">
              {deletedFiles.map((file, index) => (
                <div
                  key={file.s3_key || index}
                  className="px-3 py-2 text-xs text-black/60 truncate border-b border-black/[0.04] last:border-b-0"
                >
                  {file.filename || file.path || file.s3_key.split('/').pop() || t('workspace.uploadConfirm.unknownFile')}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-black/5 flex items-center justify-between flex-shrink-0">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider hover:bg-black hover:text-white transition-all"
          >
            {t('workspace.uploadConfirm.cancel')}
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 bg-black text-white text-xs font-semibold uppercase tracking-wider hover:bg-black/90 transition-colors"
          >
            {t('workspace.uploadConfirm.confirm')}
          </button>
        </div>
        
        {/* Bottom indicator bar */}
        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black" />
      </div>
    </div>,
    document.body
  );
};

