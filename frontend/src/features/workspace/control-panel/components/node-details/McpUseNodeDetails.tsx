import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import type { WorkflowNode } from '@/features/workflow';

// MCP 可选服务器（先提供常用内置项）
const MCP_SERVERS = [
  { value: 'excel_executor', label: 'excel_executor' },
  { value: 'word_executor', label: 'word_executor' },
];

type McpServerItem = {
  id: string;
  label: string;
  group: 'openai' | 'third_party';
  enabled: boolean;
  icon?: React.ReactNode;
};

function McpServerPickerModal({
  open,
  onClose,
  current,
  onSelect,
}: {
  open: boolean;
  current: string;
  onClose: () => void;
  onSelect: (serverId: string) => void;
}) {
  const [tab, setTab] = useState<'all' | 'openai' | 'other'>('all');
  const [addingCustom, setAddingCustom] = useState(false);
  const [customId, setCustomId] = useState('');

  const mcpSrc = `${import.meta.env.BASE_URL}node/mcp.svg`;

  const servers: McpServerItem[] = useMemo(() => {
    const openAiConnectors: McpServerItem[] = [
      { id: 'gmail', label: 'Gmail', group: 'openai' as const, enabled: false },
      { id: 'google_calendar', label: 'Google Calendar', group: 'openai' as const, enabled: false },
      { id: 'google_drive', label: 'Google Drive', group: 'openai' as const, enabled: false },
      { id: 'outlook_email', label: 'Outlook Email', group: 'openai' as const, enabled: false },
      { id: 'outlook_calendar', label: 'Outlook Calendar', group: 'openai' as const, enabled: false },
      { id: 'sharepoint', label: 'Sharepoint', group: 'openai' as const, enabled: false },
      { id: 'microsoft_teams', label: 'Microsoft Teams', group: 'openai' as const, enabled: false },
      { id: 'dropbox', label: 'Dropbox', group: 'openai' as const, enabled: false },
    ].map((s) => ({
      ...s,
      group: 'openai' as const,
      icon: (
        <div className="w-8 h-8 rounded-lg bg-black/5 border border-black/10 flex items-center justify-center text-xs font-semibold text-black/60">
          {s.label
            .split(' ')
            .map((w) => w[0])
            .slice(0, 2)
            .join('')}
        </div>
      ),
    }));

    const thirdParty: McpServerItem[] = [
      ...MCP_SERVERS.map((s) => ({
        id: s.value,
        label: s.label,
        group: 'third_party' as const,
        enabled: true,
        icon: <img src={mcpSrc} alt="MCP" className="w-8 h-8 object-contain" />,
      })),
    ];

    if (current && !thirdParty.some((s) => s.id === current) && !openAiConnectors.some((s) => s.id === current)) {
      thirdParty.unshift({
        id: current,
        label: current,
        group: 'third_party',
        enabled: true,
        icon: <img src={mcpSrc} alt="MCP" className="w-8 h-8 object-contain" />,
      });
    }

    return [...openAiConnectors, ...thirdParty];
  }, [current]);

  const visible = servers.filter((s) => {
    if (tab === 'all') return true;
    if (tab === 'openai') return s.group === 'openai';
    return s.group === 'third_party';
  });

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      <div className="relative w-[820px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)] bg-canvas border border-divider rounded-md shadow-xl overflow-hidden">
        <div className="px-5 pt-5 pb-3 flex items-center justify-between">
          <div className="text-lg font-semibold text-black/90">Add MCP server</div>
          <div className="flex items-center gap-2">
            {addingCustom ? (
              <div className="flex items-center gap-2">
                <input
                  className="h-9 w-[220px] px-3 text-[12px] bg-white border border-black/10 rounded-md focus:outline-none focus:border-black/30"
                  placeholder="server id (e.g. excel_executor)"
                  value={customId}
                  onChange={(e) => setCustomId(e.target.value)}
                />
                <button
                  type="button"
                  className="h-9 px-3 rounded-md text-xs bg-black/90 text-white hover:bg-black transition-colors"
                  onClick={() => {
                    const v = customId.trim();
                    if (!v) return;
                    onSelect(v);
                    setCustomId('');
                    setAddingCustom(false);
                    onClose();
                  }}
                >
                  Add
                </button>
                <button
                  type="button"
                  className="h-9 px-3 rounded-md text-xs text-black/60 hover:text-black/80 hover:bg-black/5 transition-colors"
                  onClick={() => {
                    setCustomId('');
                    setAddingCustom(false);
                  }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="h-9 px-3 rounded-md text-xs bg-black/5 text-black/80 hover:bg-black/10 transition-colors inline-flex items-center gap-2"
                onClick={() => setAddingCustom(true)}
              >
                <span className="text-sm leading-none">+</span>
                <span>Server</span>
              </button>
            )}

            <button
              type="button"
              className="w-9 h-9 inline-flex items-center justify-center rounded-md text-black/40 hover:text-black/80 hover:bg-black/5 transition-colors"
              onClick={onClose}
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="px-5 pb-4 flex items-center gap-2">
          <button
            type="button"
            onClick={() => setTab('all')}
            className={`h-8 px-3 rounded-md text-xs transition-colors ${
              tab === 'all' ? 'bg-black/5 text-black/90' : 'text-black/60 hover:bg-black/5 hover:text-black/80'
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setTab('openai')}
            className={`h-8 px-3 rounded-md text-xs transition-colors ${
              tab === 'openai' ? 'bg-black/5 text-black/90' : 'text-black/60 hover:bg-black/5 hover:text-black/80'
            }`}
          >
            Official
          </button>
          <button
            type="button"
            onClick={() => setTab('other')}
            className={`h-8 px-3 rounded-md text-xs transition-colors ${
              tab === 'other' ? 'bg-black/5 text-black/90' : 'text-black/60 hover:bg-black/5 hover:text-black/80'
            }`}
          >
            Community
          </button>
        </div>

        <div className="px-5 pb-5 overflow-y-auto max-h-[calc(100vh-32px-120px)]">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {visible.map((s) => {
              const selected = s.id === current;
              return (
                <button
                  key={s.id}
                  type="button"
                  disabled={!s.enabled}
                  onClick={() => {
                    if (!s.enabled) return;
                    onSelect(s.id);
                    onClose();
                  }}
                  className={`p-4 rounded-xl border text-left transition-colors ${
                    selected ? 'border-orange-500/50 bg-orange-50/30' : 'border-divider bg-white hover:bg-black/5'
                  } ${!s.enabled ? 'opacity-60 cursor-not-allowed' : ''}`}
                  title={!s.enabled ? 'Coming soon' : s.label}
                >
                  <div className="w-full flex items-center justify-start">{s.icon}</div>
                  <div className="mt-3 text-[12px] font-medium text-black/80">{s.label}</div>
                  {!s.enabled ? (
                    <div className="mt-1 text-[10px] text-black/40 uppercase tracking-wider">Coming soon</div>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function McpUseNodeDetails({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate?: (nodeId: string, patch: Record<string, any>) => void;
}) {
  const data = node.data as any;

  const [instruction, setInstruction] = useState(data.instruction || '');
  const [server, setServer] = useState(data.mcp_server_name || '');
  const [pickerOpen, setPickerOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mcpSrc = `${import.meta.env.BASE_URL}node/mcp.svg`;

  useEffect(() => {
    setInstruction(data.instruction || '');
    setServer(data.mcp_server_name || '');
    setPickerOpen(false);
  }, [node.id]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [instruction]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (data.instruction !== instruction) {
        onUpdate?.(node.id, { instruction: instruction });
      }
    }, 250);
    return () => clearTimeout(t);
  }, [instruction, node.id, data.instruction, onUpdate]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col flex-shrink-0">
        <div className="flex items-center justify-between mb-1.5 flex-shrink-0">
          <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Instruction</span>
        </div>
        <textarea
          ref={textareaRef}
          rows={1}
          className="w-full min-h-[32px] p-2 text-[11px] bg-black/5 hover:bg-black/10 border border-black/10 rounded-sm resize-none focus:outline-none focus:border-black/30 focus:bg-white placeholder:text-black/20 overflow-hidden leading-relaxed transition-colors"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Enter instruction for MCP..."
        />
      </div>

      <div className="flex items-center justify-between min-h-[28px]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Add MCP Server</span>
          {server ? (
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="inline-flex items-center gap-1 bg-black/5 border border-black/10 rounded-full px-2 py-1 text-[11px] text-black/70 hover:bg-black/10 transition-colors"
              title="Change MCP server"
            >
              <img src={mcpSrc} alt="MCP" className="w-3.5 h-3.5 object-contain" />
              <span className="truncate max-w-[180px]">{server}</span>
            </button>
          ) : null}
        </div>

        <button
          type="button"
          className="inline-flex items-center gap-2 h-8 px-3 rounded-md text-xs bg-black/5 text-black/80 hover:bg-black/10 transition-colors"
          onClick={() => setPickerOpen(true)}
        >
          <span className="text-sm leading-none">+</span>
          <span>Server</span>
        </button>
      </div>

      <McpServerPickerModal
        open={pickerOpen}
        current={server || ''}
        onClose={() => setPickerOpen(false)}
        onSelect={(id) => {
          setServer(id);
          onUpdate?.(node.id, { mcp_server_name: id });
        }}
      />
    </div>
  );
}


