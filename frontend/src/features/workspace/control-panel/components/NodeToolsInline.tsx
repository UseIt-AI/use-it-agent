import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, FileText, FolderOpen, Globe, Plus, Search, X } from 'lucide-react';
import type { WorkflowNode } from '@/features/workflow';

type ToolOption = {
  value: string;
  label: string;
  icon: React.ReactNode;
};

function ToolSettingsModal({
  open,
  tool,
  toolLabel,
  initialSettings,
  onClose,
  onSave,
}: {
  open: boolean;
  tool: string | null;
  toolLabel: string;
  initialSettings: any;
  onClose: () => void;
  onSave: (settings: any) => void;
}) {
  const [settings, setSettings] = useState<any>(initialSettings || {});

  useEffect(() => {
    setSettings(initialSettings || {});
  }, [open, tool, initialSettings]);

  if (!open || !tool) return null;

  const renderBody = () => {
    if (tool === 'web_search') {
      return (
        <div className="flex flex-col gap-2">
          <div className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instructions</div>
          <textarea
            className="w-full min-h-[160px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-y focus:outline-none focus:border-black/30 placeholder:text-black/20 leading-relaxed"
            value={settings?.instructions || ''}
            onChange={(e) => setSettings((prev: any) => ({ ...(prev || {}), instructions: e.target.value }))}
            placeholder="Enter instructions for Web Search..."
          />
        </div>
      );
    }

    if (tool === 'file_search') {
      const rows: Array<{ key: string; value: string }> = Array.isArray(settings?.meta_datafilter)
        ? settings.meta_datafilter
        : [];

      const updateRow = (idx: number, patch: Partial<{ key: string; value: string }>) => {
        const next = rows.map((r, i) => (i === idx ? { ...r, ...patch } : r));
        setSettings((prev: any) => ({ ...(prev || {}), meta_datafilter: next }));
      };

      const addRow = () => {
        setSettings((prev: any) => ({
          ...(prev || {}),
          meta_datafilter: [...rows, { key: '', value: '' }],
        }));
      };

      const removeRow = (idx: number) => {
        const next = rows.filter((_, i) => i !== idx);
        setSettings((prev: any) => ({ ...(prev || {}), meta_datafilter: next }));
      };

      return (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <div className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instructions</div>
            <textarea
              className="w-full min-h-[120px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-y focus:outline-none focus:border-black/30 placeholder:text-black/20 leading-relaxed"
              value={settings?.instructions || ''}
              onChange={(e) => setSettings((prev: any) => ({ ...(prev || {}), instructions: e.target.value }))}
              placeholder="Enter instructions for RAG..."
            />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-bold text-black/40 uppercase tracking-wider">meta_datafilter</div>
              <button
                type="button"
                onClick={addRow}
                className="inline-flex items-center gap-1 text-[11px] text-black/50 hover:text-black/80 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add</span>
              </button>
            </div>

            {rows.length === 0 ? (
              <div className="text-[11px] text-black/40">No filters</div>
            ) : (
              <div className="flex flex-col gap-2">
                {rows.map((r, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input
                      className="flex-1 h-8 px-2 text-[11px] bg-white border border-black/10 rounded-sm focus:outline-none focus:border-black/30"
                      value={r.key}
                      onChange={(e) => updateRow(idx, { key: e.target.value })}
                      placeholder="key"
                    />
                    <input
                      className="flex-1 h-8 px-2 text-[11px] bg-white border border-black/10 rounded-sm focus:outline-none focus:border-black/30"
                      value={r.value}
                      onChange={(e) => updateRow(idx, { value: e.target.value })}
                      placeholder="value"
                    />
                    <button
                      type="button"
                      className="w-8 h-8 inline-flex items-center justify-center text-black/30 hover:text-black/70 hover:bg-black/5 rounded-sm transition-colors"
                      onClick={() => removeRow(idx)}
                      title="Remove"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      );
    }

    if (tool === 'nano_banana') {
      return (
        <div className="flex flex-col gap-2">
          <div className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instructions</div>
          <textarea
            className="w-full min-h-[160px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-y focus:outline-none focus:border-black/30 placeholder:text-black/20 leading-relaxed"
            value={settings?.instructions || ''}
            onChange={(e) => setSettings((prev: any) => ({ ...(prev || {}), instructions: e.target.value }))}
            placeholder="Enter instructions for Nano Banana agent..."
          />
        </div>
      );
    }

    if (tool === 'file_system') {
      return (
        <div className="flex flex-col gap-2">
          <div className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instructions</div>
          <textarea
            className="w-full min-h-[160px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-y focus:outline-none focus:border-black/30 placeholder:text-black/20 leading-relaxed"
            value={settings?.instructions || ''}
            onChange={(e) => setSettings((prev: any) => ({ ...(prev || {}), instructions: e.target.value }))}
            placeholder="Enter instructions for File System operations..."
          />
        </div>
      );
    }

    if (tool === 'doc_extract') {
      return (
        <div className="flex flex-col gap-2">
          <div className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instructions</div>
          <textarea
            className="w-full min-h-[160px] p-2 text-[11px] bg-white border border-black/10 rounded-sm resize-y focus:outline-none focus:border-black/30 placeholder:text-black/20 leading-relaxed"
            value={settings?.instructions || ''}
            onChange={(e) => setSettings((prev: any) => ({ ...(prev || {}), instructions: e.target.value }))}
            placeholder="Enter instructions for Docling document processing..."
          />
        </div>
      );
    }

    return <div className="text-[11px] text-black/60">No settings available.</div>;
  };

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} role="button" tabIndex={-1} aria-label="Close tool settings" />

      <div className="relative w-[680px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)] bg-canvas border border-divider rounded-md shadow-xl overflow-hidden">
        <div className="h-[44px] px-4 flex items-center justify-between bg-canvas">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs font-semibold text-black/80 truncate">{toolLabel}</span>
            <span className="text-[10px] text-black/40 uppercase tracking-wider truncate">Tool Settings</span>
          </div>
          <button
            type="button"
            className="w-8 h-8 inline-flex items-center justify-center rounded-sm text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
            onClick={onClose}
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[calc(100vh-32px-44px-52px)]">{renderBody()}</div>

        <div className="h-[52px] px-4 flex items-center justify-end gap-2 bg-canvas">
          <button
            type="button"
            className="px-3 h-8 rounded-sm text-xs text-black/60 hover:text-black/80 hover:bg-black/5 transition-colors"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="px-3 h-8 rounded-sm text-xs bg-black/90 text-white hover:bg-black transition-colors"
            onClick={() => onSave(settings)}
          >
            Save
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function ToolsAddMenu({
  currentTools,
  options,
  onSelect,
}: {
  currentTools: string[];
  options: ToolOption[];
  onSelect: (toolValue: string) => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

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
    setPos({ x: r.right, y: r.bottom + 6 });
  }, [open]);

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
        className="inline-flex items-center justify-center w-5 h-5 text-black/40 hover:text-black/70 hover:bg-black/5 rounded-sm transition-colors flex-shrink-0"
        title="Add tool"
        type="button"
        onClick={() => setOpen((v) => !v)}
      >
        <Plus className="w-3.5 h-3.5" />
      </button>

      {open
        ? createPortal(
            <div
              ref={menuRef}
              className="fixed z-50 bg-canvas border border-divider rounded-md shadow-lg py-1 min-w-[220px]"
              style={{
                left: `${pos.x}px`,
                top: `${pos.y}px`,
                transform: 'translateX(-100%)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {options.map((opt) => {
                const added = currentTools.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs text-black/80 hover:bg-black/5 hover:text-black/90 transition-colors"
                    onClick={() => {
                      onSelect(opt.value);
                      close();
                    }}
                  >
                    <span className="w-4 h-4 flex items-center justify-center flex-shrink-0 text-black/60">{opt.icon}</span>
                    <span className="flex-1">{opt.label}</span>
                    <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                      {added ? <Check className="w-3.5 h-3.5 text-black/60" /> : null}
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

function ToolChip({
  label,
  icon,
  onClick,
  onRemove,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 bg-black/5 border border-black/10 rounded-full px-1.5 h-[22px] text-[11px] text-black/70 flex-shrink-0">
      <button
        type="button"
        className="inline-flex items-center gap-1 min-w-0 hover:text-black/90 transition-colors"
        onClick={onClick}
        title="Open tool settings"
      >
        <span className="w-3 h-3 flex items-center justify-center text-black/60 flex-shrink-0">{icon}</span>
        <span className="truncate max-w-[100px]">{label}</span>
      </button>
      <button
        type="button"
        className="w-3.5 h-3.5 inline-flex items-center justify-center text-black/40 hover:text-black/80 transition-colors"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        title="Remove tool"
      >
        <X className="w-2.5 h-2.5" />
      </button>
    </div>
  );
}

export function NodeToolsInline({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  const data = node.data as any;

  const [tools, setTools] = useState<string[]>(data.tools || []);
  const [toolSettings, setToolSettings] = useState<Record<string, any>>(data.toolSettings || {});
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [toolModalOpen, setToolModalOpen] = useState(false);

  const prevNodeIdRef = useRef(node.id);

  if (node.id !== prevNodeIdRef.current) {
    prevNodeIdRef.current = node.id;
    setTools(data.tools || []);
    setToolSettings(data.toolSettings || {});
    setActiveTool(null);
    setToolModalOpen(false);
  }

  const TOOL_OPTIONS: ToolOption[] = useMemo(() => {
    const nanoBananaSrc = `${import.meta.env.BASE_URL}node/nano-banana.svg`;
    return [
      { value: 'web_search', label: 'Web Search', icon: <Globe className="w-3.5 h-3.5" /> },
      { value: 'file_search', label: 'RAG', icon: <Search className="w-3.5 h-3.5" /> },
      { value: 'file_system', label: 'File System', icon: <FolderOpen className="w-3.5 h-3.5" /> },
      { value: 'doc_extract', label: 'Docling', icon: <FileText className="w-3.5 h-3.5" /> },
      { value: 'nano_banana', label: 'Nano Banana', icon: <img src={nanoBananaSrc} alt="Nano Banana" className="w-3.5 h-3.5 object-contain" /> },
    ];
  }, []);

  const openToolSettings = (toolValue: string) => {
    setActiveTool(toolValue);
    setToolModalOpen(true);
  };

  const handleAddTool = (toolValue: string) => {
    if (!tools.includes(toolValue)) {
      const next = [...tools, toolValue];
      setTools(next);
      onUpdate?.(node.id, { tools: next });
    }
    openToolSettings(toolValue);
  };

  const handleRemoveTool = (toolValue: string) => {
    const next = tools.filter((t) => t !== toolValue);
    setTools(next);
    const nextSettings = { ...(toolSettings || {}) };
    delete nextSettings[toolValue];
    setToolSettings(nextSettings);
    onUpdate?.(node.id, { tools: next, toolSettings: nextSettings });
  };

  const activeToolLabel = TOOL_OPTIONS.find((o) => o.value === activeTool)?.label || activeTool || '';

  return (
    <>
      <div className="flex items-center gap-1 overflow-hidden flex-nowrap">
        <span className="text-[11px] text-black/40 flex-shrink-0">Tools</span>
        {(tools || []).map((t) => {
          const opt = TOOL_OPTIONS.find((o) => o.value === t);
          if (!opt) return null;
          return (
            <ToolChip
              key={t}
              label={opt.label}
              icon={opt.icon}
              onClick={() => openToolSettings(t)}
              onRemove={() => handleRemoveTool(t)}
            />
          );
        })}
        <ToolsAddMenu currentTools={tools || []} options={TOOL_OPTIONS} onSelect={handleAddTool} />
      </div>

      <ToolSettingsModal
        open={toolModalOpen}
        tool={activeTool}
        toolLabel={activeToolLabel}
        initialSettings={activeTool ? toolSettings?.[activeTool] : {}}
        onClose={() => {
          setToolModalOpen(false);
          setActiveTool(null);
        }}
        onSave={(settings) => {
          const next = { ...(toolSettings || {}), [activeTool as string]: settings };
          setToolSettings(next);
          onUpdate?.(node.id, { toolSettings: next });
          setToolModalOpen(false);
          setActiveTool(null);
        }}
      />
    </>
  );
}
