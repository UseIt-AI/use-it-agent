import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Check } from 'lucide-react';

export interface MenuOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
  recommended?: boolean;
}

export function InlineMenuSelect({
  value,
  options,
  onChange,
  align = 'right',
  showIcon = false,
}: {
  value: string;
  options: MenuOption[];
  onChange: (value: string) => void;
  align?: 'left' | 'right';
  showIcon?: boolean;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const currentOption = options.find((o) => o.value === value);
  const currentLabel = currentOption?.label || value;
  const currentIcon = currentOption?.icon;

  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (e: MouseEvent) => {
      const t = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(t) &&
        triggerRef.current &&
        !triggerRef.current.contains(t)
      ) {
        close();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = align === 'right' ? r.right : r.left;
    const y = r.bottom + 6;
    setPos({ x, y });
  }, [open, align]);

  // keep menu within viewport (same idea as WorkflowContextMenu)
  useEffect(() => {
    if (!open) return;
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (rect.right > vw) el.style.left = `${vw - rect.width - 10}px`;
    if (rect.bottom > vh) el.style.top = `${vh - rect.height - 10}px`;
  }, [open, pos.x, pos.y]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="group inline-flex items-center gap-1 px-1.5 py-1 -my-1 rounded-sm text-[11px] text-black/80 hover:text-black/90 hover:bg-black/5 transition-colors select-none"
        onClick={() => setOpen((v) => !v)}
      >
        {showIcon && currentIcon && (
          <span className="w-3.5 h-3.5 flex items-center justify-center text-black/60 flex-shrink-0">{currentIcon}</span>
        )}
        <span className="truncate">{currentLabel}</span>
        <ChevronDown className="w-3 h-3 text-black/40 group-hover:text-black/60 transition-colors" />
      </button>

      {open
        ? createPortal(
            <div
              ref={menuRef}
              className="fixed z-50 bg-canvas border border-divider rounded-md shadow-lg py-1 min-w-[220px]"
              style={{
                left: align === 'right' ? `${pos.x}px` : `${pos.x}px`,
                top: `${pos.y}px`,
                transform: align === 'right' ? 'translateX(-100%)' : undefined,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {options.map((opt) => {
                const selected = opt.value === value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs text-black/80 hover:bg-black/5 hover:text-black/90 transition-colors"
                    onClick={() => {
                      onChange(opt.value);
                      close();
                    }}
                  >
                    {opt.icon && (
                      <span className="w-4 h-4 flex items-center justify-center text-black/60 flex-shrink-0">{opt.icon}</span>
                    )}
                    <span className="flex-1 flex items-center gap-1.5">
                      {opt.label}
                      {opt.recommended && (
                        <span className="px-1 py-px text-[9px] font-semibold leading-tight rounded bg-orange-100 text-orange-600 uppercase tracking-wider">
                          Recommended
                        </span>
                      )}
                    </span>
                    <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                      {selected ? <Check className="w-3.5 h-3.5 text-black/60" /> : null}
                    </span>
                  </button>
                );
              })}
            </div>,
            document.body
          )
        : null}
    </>
  );
}


