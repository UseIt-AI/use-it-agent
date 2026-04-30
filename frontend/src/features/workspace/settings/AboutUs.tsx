import { Globe, ExternalLink } from 'lucide-react';
import { Modal } from '@/components/Modal';

interface AboutUsDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AboutUsDialog({ isOpen, onClose }: AboutUsDialogProps) {
  return (
    <Modal
      open={isOpen}
      onCancel={onClose}
      onConfirm={onClose}
      title=""
      footer=""
    >
      <div className="flex flex-col items-center text-center pt-6 pb-2 gap-5 w-72">
        {/* Logo */}
        <img
          src={`${import.meta.env.BASE_URL}useit-logo-no-text.svg`}
          alt="UseIt Agent Studio"
          className="h-10 object-contain"
        />

        {/* Name + Version */}
        <div className="flex flex-col items-center gap-2">
          <h2 className="text-sm font-bold text-black/80 dark:text-white/80 tracking-wide">
            UseIt Agent Studio
          </h2>
          <span className="px-2 py-0.5 rounded-sm bg-black/5 dark:bg-white/5 text-[10px] font-mono text-black/50 dark:text-white/50 border border-black/5 dark:border-white/5">
            v{__APP_VERSION__}
          </span>
        </div>

        <div className="w-full h-px bg-black/5 dark:bg-white/5" />

        {/* Tagline */}
        <p className="text-[11px] text-black/50 dark:text-white/50 leading-relaxed px-2">
          Effortlessly create, run, and deploy <br/> your personal agents.
        </p>

        {/* Website link */}
        <a
          href="https://useit.im"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-[11px] text-black/60 dark:text-white/40 hover:text-black dark:hover:text-white transition-colors group"
        >
          <Globe className="w-3 h-3" />
          <span>useit.im</span>
          <ExternalLink className="w-2.5 h-2.5 opacity-0 group-hover:opacity-60 transition-opacity" />
        </a>

        {/* Copyright */}
        <p className="text-[10px] text-black/50 dark:text-white/25">
          © 2025–2026 UseIt Studio. All rights reserved.
        </p>
      </div>
    </Modal>
  );
}
