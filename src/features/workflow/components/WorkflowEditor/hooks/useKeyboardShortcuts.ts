import { useEffect, useCallback } from 'react';

type InteractionMode = 'pan' | 'select';

interface UseKeyboardShortcutsOptions {
  onDelete: () => void;
  onCut: () => void;
  onCopy: () => void;
  onPaste: () => void;
  setInteractionMode: (mode: InteractionMode) => void;
}

export function useKeyboardShortcuts({
  onDelete,
  onCut,
  onCopy,
  onPaste,
  setInteractionMode,
}: UseKeyboardShortcutsOptions) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    const isInputTarget =
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable;

    const isCmdOrCtrl = e.ctrlKey || e.metaKey;

    // Copy selected nodes
    if (isCmdOrCtrl && e.key.toLowerCase() === 'c') {
      if (isInputTarget) return;
      e.preventDefault();
      onCopy();
      return;
    }

    // Cut selected nodes
    if (isCmdOrCtrl && e.key.toLowerCase() === 'x') {
      if (isInputTarget) return;
      e.preventDefault();
      onCut();
      return;
    }

    // Paste nodes at viewport center
    if (isCmdOrCtrl && e.key.toLowerCase() === 'v') {
      if (isInputTarget) return;
      e.preventDefault();
      onPaste();
      return;
    }

    // Delete 键删除选中节点
    if (e.key === 'Delete' || e.key === 'Backspace') {
      // 避免在输入框中触发
      if (isInputTarget) {
        return;
      }
      onDelete();
    }

    // 空格键临时切换到拖拽模式
    if (e.key === ' ' && !e.repeat) {
      if (isInputTarget) {
        return;
      }
      e.preventDefault();
      setInteractionMode('pan');
    }
  }, [onCopy, onCut, onDelete, onPaste, setInteractionMode]);

  const handleKeyUp = useCallback((e: KeyboardEvent) => {
    // 松开空格键恢复到选择模式
    if (e.key === ' ') {
      if ((e.target as HTMLElement).tagName === 'INPUT' ||
          (e.target as HTMLElement).tagName === 'TEXTAREA') {
        return;
      }
      setInteractionMode('select');
    }
  }, [setInteractionMode]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [handleKeyDown, handleKeyUp]);
}


