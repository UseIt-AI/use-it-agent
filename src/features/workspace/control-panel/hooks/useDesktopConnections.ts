import { useEffect, useRef, useState } from 'react';
import type { DesktopConnection } from '../types';

export interface UseDesktopConnectionsOptions {
  onOpenVm?: (vmId: string, title: string, vmName?: string) => void;
  onRenameConnection?: (id: string, newName: string) => void;
}

const generateDefaultName = (connections: DesktopConnection[]) => {
  const existingNames = connections.map(c => c.name);
  let index = 1;
  while (existingNames.includes(`Desktop ${index}`)) {
    index++;
  }
  return `Desktop ${index}`;
};

export function useDesktopConnections({
  onOpenVm,
  onRenameConnection,
}: UseDesktopConnectionsOptions) {
  const [connections, setConnections] = useState<DesktopConnection[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  // auto focus edit input
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const handleAddConnection = () => {
    const newConnection: DesktopConnection = {
      id: `desktop-${Date.now()}`,
      name: generateDefaultName(connections),
    };
    setConnections(prev => [...prev, newConnection]);
    onOpenVm?.(newConnection.id, newConnection.name, newConnection.name);
  };

  const handleDeleteConnection = (id: string) => {
    setConnections(prev => prev.filter(c => c.id !== id));
  };

  const startEditing = (e: React.MouseEvent, conn: DesktopConnection) => {
    e.stopPropagation();
    setEditingId(conn.id);
    setEditingName(conn.name);
  };

  const saveEditing = () => {
    if (editingId && editingName.trim()) {
      const newName = editingName.trim();
      setConnections(prev =>
        prev.map(c => (c.id === editingId ? { ...c, name: newName } : c))
      );
      onRenameConnection?.(editingId, newName);
    }
    setEditingId(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      saveEditing();
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  };

  return {
    connections,
    editingId,
    editingName,
    editInputRef,
    setEditingName,
    handleAddConnection,
    handleDeleteConnection,
    startEditing,
    saveEditing,
    handleKeyDown,
  };
}




