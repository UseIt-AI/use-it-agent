import React from 'react';
import { Monitor, Plus, Trash2, PenLine } from 'lucide-react';
import type { DesktopConnection } from '../types';

interface VmConnectionsListProps {
  connections: DesktopConnection[];
  editingId: string | null;
  editingName: string;
  editInputRef: React.RefObject<HTMLInputElement>;
  onChangeEditingName: (name: string) => void;
  onAddConnection: () => void;
  onDeleteConnection: (id: string) => void;
  onStartEditing: (e: React.MouseEvent, conn: DesktopConnection) => void;
  onSaveEditing: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSelectConnection: (conn: DesktopConnection) => void;
}

export function VmConnectionsList({
  connections,
  editingId,
  editingName,
  editInputRef,
  onChangeEditingName,
  onAddConnection,
  onDeleteConnection,
  onStartEditing,
  onSaveEditing,
  onKeyDown,
  onSelectConnection,
}: VmConnectionsListProps) {
  return (
    <div className="w-[280px] flex flex-col border-l border-divider bg-canvas-sub/30">
      <div className="flex items-center justify-between px-3 h-[30px] border-b border-divider bg-canvas flex-shrink-0">
        <h3 className="text-[10px] font-bold text-black/40 uppercase tracking-wider">
          Connections
        </h3>
        <button
          onClick={onAddConnection}
          className="p-1 hover:bg-orange-50 text-black/40 hover:text-orange-500 transition-colors"
          title="Add Desktop"
        >
          <Plus className="w-3 h-3" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {connections.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-black/30 gap-2 px-4">
            <Monitor className="w-6 h-6 opacity-30" />
            <p className="text-[10px] text-center">
              No desktops yet.
              <br />
              <button
                onClick={onAddConnection}
                className="text-orange-500 hover:text-orange-600 font-medium"
              >
                Add your first desktop
              </button>
            </p>
          </div>
        ) : (
          connections.map(conn => (
            <div
              key={conn.id}
              className="group flex items-center justify-between px-3 h-[32px] border-b border-divider/50 hover:bg-white cursor-pointer transition-colors"
              onClick={() => {
                if (editingId !== conn.id) {
                  onSelectConnection(conn);
                }
              }}
              onDoubleClick={e => onStartEditing(e, conn)}
            >
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <Monitor className="w-3 h-3 text-black/60 flex-shrink-0" />
                {editingId === conn.id ? (
                  <input
                    ref={editInputRef}
                    type="text"
                    value={editingName}
                    onChange={e => onChangeEditingName(e.target.value)}
                    onBlur={onSaveEditing}
                    onKeyDown={onKeyDown}
                    onClick={e => e.stopPropagation()}
                    className="flex-1 h-[24px] px-1 text-[11px] font-medium bg-white border border-orange-500 outline-none min-w-0"
                  />
                ) : (
                  <span
                    className="text-[11px] font-medium text-black/80 truncate flex-1 select-none"
                    title="Double click to rename"
                  >
                    {conn.name}
                  </span>
                )}
              </div>

              {editingId !== conn.id && (
                <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 pl-2 flex-shrink-0">
                  <button
                    onClick={e => onStartEditing(e, conn)}
                    className="p-1 hover:text-orange-600 transition-colors"
                    title="Rename"
                  >
                    <PenLine className="w-2.5 h-2.5" />
                  </button>
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      onDeleteConnection(conn.id);
                    }}
                    className="p-1 hover:text-red-600 transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-2.5 h-2.5" />
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}




