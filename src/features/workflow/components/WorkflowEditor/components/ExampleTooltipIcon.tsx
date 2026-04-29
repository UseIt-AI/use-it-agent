import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface ExampleTooltipIconProps {
  text: string;
}

export function ExampleTooltipIcon({ text }: ExampleTooltipIconProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const anchorRef = useRef<HTMLDivElement>(null);

  const show = () => {
    const el = anchorRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({ x: r.left + r.width / 2, y: r.bottom });
    setOpen(true);
  };

  const hide = () => setOpen(false);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => show();
    const onResize = () => show();
    // Capture scroll from any container
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <>
      <div
        ref={anchorRef}
        className="w-3.5 h-3.5 rounded-full border border-black/20 flex items-center justify-center text-[9px] cursor-help text-black/50 hover:text-black/80 transition-colors"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={0}
        role="button"
        aria-label="Example"
      >
        i
      </div>
      {open && pos
        ? createPortal(
            <div
              className="fixed z-[9999] pointer-events-none"
              style={{ left: pos.x, top: pos.y + 8, transform: 'translateX(-50%)' }}
            >
              <div className="w-[420px] max-w-[80vw] bg-white border border-black/10 shadow-lg rounded-sm px-3 py-2 text-[10px] text-black/70 leading-relaxed">
                {text}
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}


