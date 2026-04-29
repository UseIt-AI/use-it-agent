import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, Loader2 } from 'lucide-react';

interface AlertDialogProps {
  open: boolean;
  title: string;
  description?: string;
  children?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  footer?: React.ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  isDestructive?: boolean;
  loading?: boolean;
}

export const AlertDialog: React.FC<AlertDialogProps> = ({
  open,
  title,
  description,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  footer,
  onConfirm,
  onCancel,
  isDestructive = false,
  loading = false,
}) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (open) {
      setVisible(true);
    } else {
      const timer = setTimeout(() => setVisible(false), 200);
      return () => clearTimeout(timer);
    }
  }, [open]);

  if (!visible && !open) return null;

  return createPortal(
    <div className={`fixed inset-0 z-[100] flex items-center justify-center transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}`}>
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
        onClick={loading ? undefined : onCancel}
      />
      
      {/* Dialog Panel */}
      <div className={`
        relative w-full max-w-[360px] bg-white border border-black/15 shadow-[0_12px_32px_-16px_rgba(0,0,0,0.35)] overflow-hidden transform transition-all duration-200
        ${open ? 'scale-100 translate-y-0' : 'scale-95 translate-y-2'}
      `}>
        {/* Header */}
        <div className="px-5 pt-5 pb-3">
          {/* Row 1: Icon + Title */}
          <div className="flex items-center gap-3 mb-2">
            {isDestructive && (
              <div className="flex-shrink-0 w-8 h-8 bg-red-50/60 flex items-center justify-center text-red-600">
                <AlertTriangle className="w-4 h-4" strokeWidth={2} />
              </div>
            )}
            <h3 className="text-sm font-semibold text-gray-900 leading-none">
              {title}
            </h3>
          </div>

          {/* Row 2: Description */}
          {description && (
            <p className="text-xs text-gray-600 leading-relaxed">
              {description}
            </p>
          )}
        </div>

        {/* Custom Content */}
        {children && <div className="px-5 pb-3">{children}</div>}

        {/* Footer / Actions */}
        {footer ?? <div className="px-4 py-3 bg-gray-50/60 flex items-center justify-end gap-2 border-t border-black/10">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium text-gray-700 hover:text-gray-900 hover:bg-black/5 transition-colors border border-transparent disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`
              px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-all flex items-center gap-1.5
              disabled:opacity-70 disabled:cursor-not-allowed
              ${isDestructive
                ? 'bg-red-600 hover:bg-red-700 shadow-red-600/20'
                : 'bg-black hover:bg-black/90'
              }
            `}
          >
            {loading && <Loader2 className="w-3 h-3 animate-spin" />}
            {confirmLabel}
          </button>
        </div>}
        
      </div>
    </div>,
    document.body
  );
};

