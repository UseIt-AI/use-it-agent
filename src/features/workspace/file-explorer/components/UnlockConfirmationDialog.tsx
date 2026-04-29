import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Unlock, AlertTriangle, File, Folder } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface UnlockConfirmationDialogProps {
  open: boolean;
  fileName: string;
  isFolder: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const UnlockConfirmationDialog: React.FC<UnlockConfirmationDialogProps> = ({
  open,
  fileName,
  isFolder,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (open) {
      setVisible(true);
    } else {
      const timer = setTimeout(() => setVisible(false), 200);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // 处理 ESC 键关闭
  useEffect(() => {
    if (!open) return;
    
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open, onCancel]);

  if (!visible && !open) return null;

  return createPortal(
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center font-sans transition-opacity duration-200 ${
        open ? 'opacity-100' : 'opacity-0 pointer-events-none'
      }`}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
        onClick={onCancel}
      />

      {/* Dialog Panel - Match Upload style */}
      <div
        className={`relative w-full max-w-[420px] mx-4 bg-white border border-black/[0.08] shadow-[0_8px_40px_-12px_rgba(0,0,0,0.15)] overflow-hidden transform transition-all duration-200 ${
          open ? 'scale-100 translate-y-0' : 'scale-95 translate-y-2'
        }`}
      >
        {/* Decorative corner lines */}
        <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden pointer-events-none">
          <div className="absolute top-0 right-0 w-[1px] h-10 bg-gradient-to-b from-black/10 to-transparent" />
          <div className="absolute top-0 right-0 h-[1px] w-10 bg-gradient-to-l from-black/10 to-transparent" />
        </div>

        {/* Header */}
        <div className="px-6 pt-6 pb-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-black/5 text-black/70">
                <Unlock className="w-5 h-5 text-orange-600" strokeWidth={2} />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-black/90">
                  {t('workspace.fileExplorer.unlockDialog.title')}
                </h3>
                <p className="text-xs mt-1 text-black/50">
                  {t('workspace.fileExplorer.unlockDialog.subtitle')}
                </p>
              </div>
            </div>
            <button
              onClick={onCancel}
              className="p-1.5 hover:bg-black/5 transition-colors -mt-1 -mr-1"
              title={t('workspace.fileExplorer.unlockDialog.cancel')}
            >
              <X className="w-4 h-4 text-black/40 hover:text-black/70" />
            </button>
          </div>
        </div>

        {/* Divider */}
        <div className="mx-6 h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" />

        {/* Content */}
        <div className="px-6 py-5">
          <div className="space-y-4">
            {/* File/Folder Info */}
            <div className="flex items-start gap-3 p-3 bg-black/[0.02] border border-black/[0.08]">
              <div className="flex-shrink-0 mt-0.5">
                {isFolder ? (
                  <Folder className="w-5 h-5 text-black/55" strokeWidth={2} />
                ) : (
                  <File className="w-5 h-5 text-black/55" strokeWidth={2} />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-black/90 truncate">
                  {fileName}
                </div>
                <div className="text-xs text-black/45 mt-0.5">
                  {isFolder
                    ? t('workspace.fileExplorer.unlockDialog.folder')
                    : t('workspace.fileExplorer.unlockDialog.file')}
                </div>
              </div>
            </div>

            {/* Warning Message */}
            <div className="flex items-start gap-3 p-3 bg-orange-50/45 border border-orange-200/55">
              <div className="flex-shrink-0 mt-0.5">
                <AlertTriangle className="w-4 h-4 text-amber-600" strokeWidth={2} />
              </div>
              <div className="flex-1">
                <p className="text-xs font-semibold text-amber-900 mb-1 uppercase tracking-wide">
                  {t('workspace.fileExplorer.unlockDialog.warningTitle')}
                </p>
                <p className="text-sm text-amber-800/85 leading-relaxed">
                  {t('workspace.fileExplorer.unlockDialog.warningDescription', {
                    type: isFolder
                      ? t('workspace.fileExplorer.unlockDialog.folder')
                      : t('workspace.fileExplorer.unlockDialog.file'),
                  })}
                  {isFolder && t('workspace.fileExplorer.unlockDialog.folderWarningExtra')}
                </p>
              </div>
            </div>

            {/* Info Box */}
            <div className="text-xs text-black/55 leading-relaxed bg-blue-50/45 p-3 border border-blue-200/45">
              <p>
                💡 <span className="font-medium text-black/70">{t('workspace.fileExplorer.unlockDialog.tipTitle')}</span>
                {t('workspace.fileExplorer.unlockDialog.tipDescription')}
              </p>
            </div>
          </div>
        </div>

        {/* Footer / Actions */}
        <div className="px-6 py-4 bg-black/[0.015] flex items-center justify-end gap-3 border-t border-black/[0.06]">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-[10px] text-black/50 font-semibold uppercase tracking-wider hover:bg-black hover:text-white transition-all"
          >
            {t('workspace.fileExplorer.unlockDialog.cancel')}
          </button>
          <button
            onClick={onConfirm}
            className="group relative px-4 py-2 bg-black text-white text-xs font-semibold uppercase tracking-wider hover:bg-black/90 transition-colors overflow-hidden"
          >
            {t('workspace.fileExplorer.unlockDialog.confirm')}
          </button>
        </div>

        {/* Bottom indicator bar */}
        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black" />
      </div>
    </div>,
    document.body
  );
};

