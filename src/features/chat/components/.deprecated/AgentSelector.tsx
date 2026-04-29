/**
 * @deprecated This component is no longer used.
 * The AgentSelector has been removed from the chat interface.
 */

import React, { useState } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import type { AgentMode } from '../../hooks/useChat';
import { useChatAgents } from '../../hooks/useChatAgents';

interface AgentSelectorProps {
  mode: AgentMode;
  setMode: (mode: AgentMode) => void;
}

export const AgentSelector: React.FC<AgentSelectorProps> = ({ mode, setMode }) => {
  const [isAgentMenuOpen, setIsAgentMenuOpen] = useState(false);

  const { agents } = useChatAgents();
  const currentAgent = agents.find(a => a.id === mode) || agents[0];

  return (
    <div className="flex justify-center mb-3 relative z-30">
      <button
        type="button"
        onClick={() => setIsAgentMenuOpen(!isAgentMenuOpen)}
        // 硬朗风格：无圆角(或微圆角)，纯白背景，细边框
        className="flex items-center gap-2 px-3 py-2 bg-white border border-black/10 hover:border-orange-500/50 transition-all text-sm font-medium text-black/80 min-w-[240px] justify-between group"
      >
        <div className="flex items-center gap-3">
          {/* Icon Box */}
          <div className={`flex items-center justify-center w-6 h-6 bg-gray-50 border border-black/10 ${currentAgent.color}`}>
            <currentAgent.icon className="w-3.5 h-3.5" />
          </div>
          <div className="flex flex-col items-start leading-none gap-0.5">
             <span className="text-[10px] text-black/40 font-mono uppercase tracking-wider">Agent</span>
             <span className="text-black/90 font-semibold tracking-tight">{currentAgent.label}</span>
          </div>
        </div>
        <ChevronDown className={`w-3.5 h-3.5 text-black/30 transition-transform duration-200 group-hover:text-black/60 ${isAgentMenuOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* 下拉菜单 */}
      {isAgentMenuOpen && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setIsAgentMenuOpen(false)} />
          <div className="absolute top-full mt-1 w-[240px] bg-white border border-black/10 shadow-xl flex flex-col z-40">
            {agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => {
                  setMode(agent.id as AgentMode);
                  setIsAgentMenuOpen(false);
                }}
                className={`
                  flex items-start gap-3 px-3 py-3 text-left transition-colors border-b border-black/[0.03] last:border-none
                  ${mode === agent.id 
                    ? 'bg-orange-50/30' 
                    : 'hover:bg-gray-50'
                  }
                `}
              >
                <div className={`mt-0.5 flex items-center justify-center w-5 h-5 border border-black/10 ${mode === agent.id ? 'bg-white' : 'bg-gray-50'} ${agent.color}`}>
                  <agent.icon className="w-3 h-3" />
                </div>
                <div className="flex flex-col flex-1 min-w-0 gap-0.5">
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${mode === agent.id ? 'text-orange-900' : 'text-black/90'}`}>
                      {agent.label}
                    </span>
                    {mode === agent.id && <Check className="w-3.5 h-3.5 text-orange-600" />}
                  </div>
                  <span className={`text-xs truncate ${mode === agent.id ? 'text-orange-900/60' : 'text-black/40'}`}>
                    {agent.desc}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};


