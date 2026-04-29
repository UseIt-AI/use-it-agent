import React, { useState, useEffect, useCallback } from 'react';
import { X } from 'lucide-react';

const PANEL_HINTS_KEY = 'useit_panel_hints_dismissed';
const ONBOARDING_ENABLED = import.meta.env.VITE_ENABLE_ONBOARDING !== 'false';

function getDismissed(): string[] {
  try {
    const stored = localStorage.getItem(PANEL_HINTS_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

function setDismissed(ids: string[]) {
  localStorage.setItem(PANEL_HINTS_KEY, JSON.stringify(ids));
}

interface PanelHintProps {
  panelId: string;
  message: string;
}

export function PanelHint({ panelId, message }: PanelHintProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const dismissed = getDismissed();
    if (!dismissed.includes(panelId)) {
      setVisible(true);
    }
  }, [panelId]);

  const handleDismiss = useCallback(() => {
    setVisible(false);
    const dismissed = getDismissed();
    if (!dismissed.includes(panelId)) {
      setDismissed([...dismissed, panelId]);
    }
  }, [panelId]);

  if (!ONBOARDING_ENABLED || !visible) return null;

  return (
    <div className="flex flex-col px-3 py-2.5 bg-black/[0.03] border-t border-black/[0.08] flex-shrink-0 animate-in fade-in slide-in-from-bottom-1 duration-200">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-black/35 uppercase tracking-wider">Tip</span>
        <button
          onClick={handleDismiss}
          className="w-4 h-4 flex items-center justify-center text-black/25 hover:text-black/50 transition-colors"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
      <p className="text-[11px] text-black/50 leading-relaxed mt-0.5">{message}</p>
    </div>
  );
}
