import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Info, CheckCircle } from 'lucide-react';

interface InfoDialogProps {
  open: boolean;
  title: string | React.ReactNode;
  description?: string;
  icon?: 'info' | 'success' | React.ReactNode;
  confirmLabel?: string;
  onClose: () => void;
  children?: React.ReactNode;
}

export const InfoDialog: React.FC<InfoDialogProps> = ({
  open,
  title,
  description,
  icon = 'info',
  confirmLabel = 'Got it',
  onClose,
  children,
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

  const renderIcon = () => {
    if (icon === 'info') {
      return (
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center text-blue-500">
          <Info className="w-5 h-5" />
        </div>
      );
    }
    if (icon === 'success') {
      return (
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-green-50 flex items-center justify-center text-green-500">
          <CheckCircle className="w-5 h-5" />
        </div>
      );
    }
    return icon;
  };

  return createPortal(
    <div className={`fixed inset-0 z-[100] flex items-center justify-center transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}`}>
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]" 
        onClick={onClose}
      />
      
      {/* Dialog Panel */}
      <div className={`
        relative w-full max-w-[380px] bg-white rounded-lg shadow-xl border border-black/10 overflow-hidden transform transition-all duration-200
        ${open ? 'scale-100 translate-y-0' : 'scale-95 translate-y-2'}
      `}>
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 text-black/30 hover:text-black/60 hover:bg-black/5 rounded-md transition-colors z-10"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Content */}
        <div className="px-6 pt-6 pb-4">
          {/* Icon + Title */}
          <div className="flex items-start gap-4 mb-3">
            {renderIcon()}
            <div className="flex-1 pt-1">
              <h3 className="text-base font-semibold text-gray-900 leading-tight pr-6">
                {title}
              </h3>
            </div>
          </div>

          {/* Description */}
          {description && (
            <p className="text-sm text-gray-500 leading-relaxed ml-14">
              {description}
            </p>
          )}

          {/* Custom children */}
          {children && (
            <div className="mt-4 ml-14">
              {children}
            </div>
          )}
        </div>

        {/* Footer / Actions */}
        <div className="px-6 py-4 bg-gray-50/50 flex items-center justify-end border-t border-gray-100">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-black hover:bg-gray-800 rounded-md shadow-sm transition-all"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
