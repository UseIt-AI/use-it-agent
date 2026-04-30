import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Monitor,
  ChevronDown,
  AlertTriangle,
} from 'lucide-react';
import type { AgentTarget } from '../types';

interface AgentTargetContentProps {
  selectedTarget: AgentTarget | null;
  activeTargetId?: string | null;
  onSelectTarget?: (targetId: string) => void;
  onActivateTarget?: (targetId: string) => void;
  targets?: AgentTarget[];
}

export function AgentTargetContent({
  selectedTarget,
  activeTargetId,
  onSelectTarget,
  onActivateTarget,
  targets,
}: AgentTargetContentProps) {
  if (!selectedTarget) {
    return (
      <IntroductionContent
        onSelectTarget={onSelectTarget}
        activeTargetId={activeTargetId}
        targets={targets}
      />
    );
  }

  return (
    <LocalMachineContent
      target={selectedTarget}
      isActive={selectedTarget.id === activeTargetId}
      onActivate={() => onActivateTarget?.(selectedTarget.id)}
    />
  );
}

function Tooltip({ children, content }: { children: React.ReactNode; content: string }) {
  const [coords, setCoords] = useState<{ x: number; y: number } | null>(null);

  const handleMouseEnter = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setCoords({
      x: rect.left + rect.width / 2,
      y: rect.top,
    });
  };

  const handleMouseLeave = () => {
    setCoords(null);
  };

  return (
    <>
      <div className="relative flex items-center" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
        {children}
      </div>
      {coords &&
        createPortal(
          <div
            className="fixed p-2 bg-white border border-black/10 shadow-xl text-xs text-black/70 rounded-sm z-[9999] text-center w-48 pointer-events-none animate-in fade-in duration-200"
            style={{
              left: coords.x,
              top: coords.y - 8,
              transform: 'translate(-50%, -100%)',
            }}
          >
            {content}
            <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-[1px] border-4 border-transparent border-t-white" />
          </div>,
          document.body
        )}
    </>
  );
}

function IntroductionContent({
  onSelectTarget,
  activeTargetId,
  targets,
}: {
  onSelectTarget?: (id: string) => void;
  activeTargetId?: string | null;
  targets?: AgentTarget[];
}) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const activeTargetName = targets?.find((t) => t.id === activeTargetId)?.name;

  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas flex flex-col py-2 pr-2 pl-4">
      <div className="flex items-center justify-between mb-1.5 flex-shrink-0 h-5">
        <h2 className="text-xs font-bold text-black/60 flex items-center gap-2">
          Environment
          <span className="w-px h-3 bg-black/10"></span>
          <span className="text-[12px] text-black/60 font-normal">
            Choose where the AI agent executes tasks.
          </span>
        </h2>

        {activeTargetName && (
          <div className="relative z-20">
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="flex items-center gap-2 hover:bg-black/5 px-2 py-0.5 rounded-sm transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] font-bold text-black/40 uppercase tracking-wider">Active:</span>
                <div className="relative flex items-center justify-center">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-20 animate-ping"></span>
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                </div>
                <span className="text-[10px] font-bold text-black/80 tracking-tight">{activeTargetName}</span>
                <ChevronDown className="w-3 h-3 text-black/40 ml-0.5" />
              </div>
            </button>

            {isDropdownOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setIsDropdownOpen(false)} />
                <div className="absolute right-0 top-full mt-1 w-[180px] bg-white border border-divider shadow-xl rounded-sm z-20 overflow-hidden flex flex-col animate-in fade-in slide-in-from-top-1 duration-200">
                  <div className="px-3 py-1.5 border-b border-divider/50 flex items-center justify-center bg-black/[0.02]">
                    <span className="text-[9px] font-bold text-black/40 uppercase tracking-wider">Switch Environment</span>
                  </div>
                  <div className="py-1 flex flex-col">
                    {targets?.map((target) => {
                      const isActive = target.id === activeTargetId;
                      return (
                        <button
                          key={target.id}
                          disabled={!target.available}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectTarget?.(target.id);
                            setIsDropdownOpen(false);
                          }}
                          className={`
                               flex items-center gap-2 px-3 py-1.5 text-left text-[11px] transition-colors w-full
                               ${isActive ? 'bg-orange-50 text-orange-700' : 'text-black/70 hover:bg-black/5'}
                               ${!target.available ? 'opacity-50 cursor-not-allowed' : ''}
                             `}
                        >
                          <div
                            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                              target.available ? 'bg-emerald-500' : 'bg-neutral-300'
                            }`}
                          />
                          <span className="font-medium truncate flex-1">{target.name}</span>
                          {isActive && <div className="w-1 h-1 rounded-full bg-orange-500" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-hidden flex items-center justify-center">
        <div className="flex items-center flex-wrap justify-center text-sm font-medium text-black/90 leading-loose">
          <span>Run the agent on</span>
          <Tooltip content="Execute tasks on this computer.">
            <button
              onClick={() => onSelectTarget?.('local')}
              className="inline-flex items-center gap-1.5 px-3 mx-2 bg-black text-white border border-black shadow-sm text-xs font-bold uppercase tracking-wide transition-all align-middle h-8 hover:bg-black/90"
            >
              <Monitor className="w-3 h-3" />
              This PC
            </button>
          </Tooltip>
          <span>.</span>
        </div>
      </div>
    </div>
  );
}

function LocalMachineContent({
  target,
  isActive,
  onActivate,
}: {
  target: AgentTarget;
  isActive: boolean;
  onActivate: () => void;
}) {
  return (
    <div className="flex-1 h-full overflow-hidden bg-canvas flex flex-col py-2 pr-2 pl-4">
      <div className="flex items-center justify-between mb-2 flex-shrink-0 h-6">
        <div className="flex items-center gap-2">
          <Monitor className="w-4 h-4 text-black/60" />
          <h2 className="text-sm font-bold text-black/80">{target.name}</h2>
          <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-sm tracking-wide ml-2">
            Ready
          </span>
        </div>

        <button
          onClick={onActivate}
          disabled={isActive}
          className={`
            flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-colors
            ${isActive ? 'bg-emerald-500/10 text-emerald-600 cursor-default' : 'bg-black/5 text-black/60 hover:bg-black/10 hover:text-black/80'}
          `}
        >
          {isActive ? (
            <>
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="font-bold">Active</span>
            </>
          ) : (
            <span>Activate</span>
          )}
        </button>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-2">
        <p className="text-[11px] text-black/60 leading-relaxed px-1">
          The agent runs directly on your operating system with user-level permissions.
        </p>

        <div className="w-fit p-3 bg-amber-50/50 border border-amber-100 rounded-sm flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <div className="flex flex-col gap-0.5">
            <h4 className="text-[10px] font-bold text-amber-800 uppercase tracking-wide">Live environment</h4>
            <p className="text-[10px] text-amber-900/70 leading-relaxed">
              The agent can control mouse and keyboard. Avoid interfering while it runs.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
