import React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import clsx from 'clsx';

interface ModalProps {
  open: boolean;
  title?: string | React.ReactNode;
  children: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  footer?: React.ReactNode;
  bodyClass?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const Modal: React.FC<ModalProps> = ({
  open,
  onCancel,
  onConfirm,
  title,
  children,
  footer,
  bodyClass,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
}) => {

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 font-sans text-[#1A1A1A] dark:text-[#E5E5E5]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-[2px] animate-in fade-in duration-200"
        onClick={onCancel}
      />

      {/* Dialog Panel */}
      <div className="relative bg-[#FAF9F6] dark:bg-[#1A1A1A] shadow-2xl animate-in zoom-in-95 duration-200 flex flex-col border border-black/10 dark:border-white/10 rounded-sm">
        {/* Close button */}
        <button
          onClick={onCancel}
          className="absolute top-2 right-2 p-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-sm transition-colors text-black/40 dark:text-white/40 hover:text-black dark:hover:text-white z-10"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        {typeof title === 'string' ? (
          title !== '' && (
            <h3 className="m-4 text-sm font-semibold text-gray-900 leading-none">
              {title}
            </h3>
          )
        ) : (
          title !== undefined && (
            <div className="m-4">{title}</div>
          )
        )}

        {/* Custom Content */}
        <div className={clsx("px-5 pb-3",bodyClass)}>{children}</div>

        {/* Footer / Actions */}
        {footer ?? <div className="px-4 py-3 bg-gray-50/60 flex items-center justify-end gap-2 border-t border-black/10">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs font-medium text-gray-700 hover:text-gray-900 hover:bg-black/5 transition-colors border border-transparent"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-all bg-black hover:bg-black/90"
          >
            {confirmLabel}
          </button>
        </div>}
      </div>
    </div>,
    document.body
  );
};

