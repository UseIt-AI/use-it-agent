import React from 'react';
import { Loader2, X } from 'lucide-react';
import { DEFAULT_VM_NAME } from '../constants';

interface ShutdownModalProps {
  open: boolean;
  vmName?: string;
  isShuttingDown: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ShutdownModal({
  open,
  vmName,
  isShuttingDown,
  error,
  onCancel,
  onConfirm,
}: ShutdownModalProps) {
  if (!open) return null;

  const effectiveName = vmName || DEFAULT_VM_NAME;

  return (
    <div className="absolute inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="w-[320px] bg-white border border-divider shadow-xl rounded-sm">
        <div className="px-4 py-3 border-b border-divider bg-[#F8F9FA] flex items-center justify-between rounded-t-sm">
          <span className="text-xs font-semibold text-black/70">Shut down VM</span>
          <button
            className="p-1 text-black/30 hover:text-black/70"
            onClick={() => !isShuttingDown && onCancel()}
          >
            <X className="w-3 h-3" />
          </button>
        </div>
        <div className="px-4 py-3 space-y-2">
          <p className="text-xs text-black/70">
            Are you sure you want to shut down{' '}
            <span className="font-mono font-semibold">{effectiveName}</span>?
          </p>
          <p className="text-[11px] text-black/40">
            The connection will be closed and the virtual machine will be turned off.
          </p>
          {error && <p className="text-[11px] text-red-500">{error}</p>}
        </div>
        <div className="px-4 py-2 border-t border-divider flex justify-end gap-2 bg-[#F8F9FA]">
          <button
            onClick={() => !isShuttingDown && onCancel()}
            disabled={isShuttingDown}
            className="px-3 h-[28px] text-xs font-medium text-black/60 border border-divider bg-white hover:bg-black/5 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isShuttingDown}
            className="px-3 h-[28px] text-xs font-medium text-white bg-red-500 hover:bg-red-600 disabled:bg-red-300 flex items-center gap-1"
          >
            {isShuttingDown && <Loader2 className="w-3 h-3 animate-spin" />}
            Shut down
          </button>
        </div>
      </div>
    </div>
  );
}


