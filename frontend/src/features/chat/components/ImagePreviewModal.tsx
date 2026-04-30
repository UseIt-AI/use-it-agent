import React, { useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

interface ImagePreviewModalProps {
  src: string;
  alt?: string;
  onClose: () => void;
}

export const ImagePreviewModal: React.FC<ImagePreviewModalProps> = ({ src, alt, onClose }) => {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="relative max-w-[90vw] max-h-[90vh] animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 z-10 p-1.5 rounded-full bg-black/70 hover:bg-black/90 text-white/80 hover:text-white transition-colors shadow-lg"
        >
          <X className="w-4 h-4" />
        </button>
        <img
          src={src}
          alt={alt || 'Preview'}
          className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
          draggable={false}
        />
      </div>
    </div>,
    document.body
  );
};
