import React, { useState } from 'react';
import { Monitor, Check, Plus, Trash2 } from 'lucide-react';
import type { AgentTarget } from '../types';
import { AlertDialog } from '@/components/AlertDialog';

interface AgentTargetListProps {
  targets: AgentTarget[];
  selectedId: string | null;
  activeId?: string | null;
  onSelect: (target: AgentTarget | null) => void;
  onActivate?: (targetId: string) => void;
  onDelete?: (targetId: string) => void;
}

export function AgentTargetList({
  targets,
  selectedId,
  activeId,
  onSelect,
  onActivate,
  onDelete,
}: AgentTargetListProps) {
  const [pendingDelete, setPendingDelete] = useState<AgentTarget | null>(null);

  const handleClick = (target: AgentTarget) => {
    if (selectedId === target.id) {
      return;
    } else {
      onSelect(target);
    }
  };

  const handleConfirmDelete = () => {
    if (pendingDelete && onDelete) {
      onDelete(pendingDelete.id);
      setPendingDelete(null);
    }
  };

  return (
    <div className="w-[280px] flex flex-col border-l border-divider bg-canvas-sub/30 relative">
      <div className="flex items-center justify-between px-4 h-[36px] border-b border-divider bg-canvas flex-shrink-0">
        <div className="flex items-center gap-2">
          <h3 className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Available</h3>
          <span className="text-[9px] font-mono text-black/30 bg-black/5 px-1 rounded-sm">
            {targets.filter((t) => t.available).length}
          </span>
        </div>

        <button
          onClick={() => onSelect(null)}
          className="p-1 hover:bg-black/5 rounded text-black/40 hover:text-black/80 transition-colors"
          title="Overview"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {targets.map((target) => {
          const isSelected = selectedId === target.id;
          const isActive = activeId === target.id;
          const canSelect = target.available;
          const dotColor = target.available ? 'bg-emerald-500' : 'bg-neutral-300';

          return (
            <div
              key={target.id}
              onClick={() => canSelect && handleClick(target)}
              className={`
                group flex items-center gap-3 pl-4 pr-2 h-[36px] border-b border-divider/50 
                cursor-pointer transition-colors
                ${isSelected ? 'bg-white text-black' : 'text-black/60 hover:bg-black/5 hover:text-black/90'}
                ${!canSelect ? 'opacity-40 cursor-not-allowed' : ''}
              `}
            >
              <div className={`w-1.5 h-1.5 flex-shrink-0 rounded-full ${dotColor}`} />

              <Monitor className={`w-3.5 h-3.5 flex-shrink-0 ${isSelected ? 'text-black' : 'text-black/40'}`} strokeWidth={1.5} />

              <div className="flex-1 min-w-0 flex items-center justify-between mr-2">
                <span className={`text-[11px] font-medium truncate leading-none ${isSelected ? 'text-black' : 'text-black/70'}`}>
                  {target.name}
                </span>
              </div>

              <div className="flex items-center gap-1">
                {target.deletable ? (
                  <button
                    className="w-6 h-6 flex items-center justify-center rounded-sm hover:bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDelete(target);
                    }}
                    title="Delete Environment"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-black/30 hover:text-black/70 transition-colors" />
                  </button>
                ) : null}

                <div
                  className="w-6 h-6 flex items-center justify-center rounded-sm hover:bg-black/5"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (target.available) onActivate?.(target.id);
                  }}
                  title={isActive ? 'Current Active Environment' : 'Set as Active Environment'}
                >
                  {isActive ? (
                    <Check className="w-3.5 h-3.5 text-orange-600" strokeWidth={2.5} />
                  ) : (
                    <Check className="w-3.5 h-3.5 text-black/20 opacity-0 group-hover:opacity-100 hover:text-orange-500 transition-all" />
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <AlertDialog
        open={!!pendingDelete}
        title="Delete Environment?"
        description={`Are you sure you want to delete "${pendingDelete?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
        isDestructive={true}
      />
    </div>
  );
}
