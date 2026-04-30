import React from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface WelcomeModalProps {
  open: boolean;
  onStartTour: () => void;
  onSkip: () => void;
}

export function WelcomeModal({ open, onStartTour, onSkip }: WelcomeModalProps) {
  const { t } = useTranslation();

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[99999] flex items-center justify-center">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/70" />

      {/* Modal */}
      <div className="relative w-[420px] bg-[var(--bg-primary,#fff)] border border-[var(--border-primary,rgba(0,0,0,0.1))] shadow-[0_8px_40px_rgba(0,0,0,0.25)] animate-in fade-in zoom-in-95 duration-300">
        {/* Close button */}
        <button
          onClick={onSkip}
          className="absolute top-3 right-3 w-6 h-6 flex items-center justify-center text-[var(--text-secondary,rgba(0,0,0,0.4))] hover:text-[var(--text-primary,#000)] hover:bg-[var(--bg-secondary,rgba(0,0,0,0.05))] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Content */}
        <div className="px-8 pt-10 pb-8">
          {/* Logo / Brand */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 bg-black flex items-center justify-center">
              <span className="text-white text-sm font-black tracking-tighter">UI</span>
            </div>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary,#000)] tracking-tight leading-none">
                USEIT STUDIO
              </h1>
              <p className="text-[10px] font-semibold text-[var(--text-secondary,rgba(0,0,0,0.4))] uppercase tracking-[0.15em] mt-0.5">
                {t('welcome.subtitle')}
              </p>
            </div>
          </div>

          {/* Divider */}
          <div className="h-px bg-[var(--border-primary,rgba(0,0,0,0.1))] mb-5" />

          {/* Welcome text */}
          <p className="text-sm text-[var(--text-secondary,rgba(0,0,0,0.5))] leading-relaxed mb-8">
            {t('welcome.description')}
          </p>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={onStartTour}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-[var(--text-primary,#000)] text-[var(--bg-primary,#fff)] text-xs font-bold uppercase tracking-wider hover:opacity-90 transition-opacity"
            >
              <span>{t('welcome.startTour')}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onSkip}
              className="px-4 py-2.5 text-xs font-semibold text-[var(--text-secondary,rgba(0,0,0,0.4))] uppercase tracking-wider border border-[var(--border-primary,rgba(0,0,0,0.1))] hover:bg-[var(--bg-secondary,rgba(0,0,0,0.05))] hover:text-[var(--text-primary,#000)] transition-all"
            >
              {t('welcome.skip')}
            </button>
          </div>
        </div>

        {/* Bottom accent bar */}
        <div className="h-[2px] bg-[var(--text-primary,#000)]" />
      </div>
    </div>,
    document.body
  );
}
