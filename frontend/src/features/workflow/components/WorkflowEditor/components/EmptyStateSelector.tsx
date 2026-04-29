import React from 'react';
import { Video, Sparkles, Play, MessageSquare, FilePlus, Clock } from 'lucide-react';

interface EmptyStateSelectorProps {
  onCreateFromDemo: () => void;
  onCreateFromChat: () => void;
  onCreateBlank: () => void;
}

export function EmptyStateSelector({ onCreateFromDemo, onCreateFromChat, onCreateBlank }: EmptyStateSelectorProps) {
  return (
    <div className="w-full h-full bg-[#FAFAFA] flex flex-col items-center justify-center overflow-y-auto font-sans selection:bg-black/5">
      {/* Subtle background pattern */}
      <div 
        className="absolute inset-0 opacity-[0.4] pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.03) 1px, transparent 0)',
          backgroundSize: '24px 24px'
        }}
      />

      <div className="w-full max-w-[1000px] px-8 py-12 flex flex-col gap-6 animate-in fade-in zoom-in-95 duration-500 relative z-10">
        
        {/* Header */}
        <div className="space-y-2 text-center">
          <h1 className="text-xl font-black text-black tracking-tight">Initialize Workflow</h1>
          <p className="text-sm text-black/50 font-medium">
            Choose how to start building your agent.
          </p>
        </div>

        {/* Divider */}
        <div className="h-px bg-gradient-to-r from-transparent via-black/10 to-transparent" />

        {/* Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          
          {/* From Demonstration - Orange highlighted card */}
          <button
            onClick={onCreateFromDemo}
            className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-orange-50/60 via-amber-50/30 to-stone-50 border border-orange-200/40 hover:border-orange-300/60 transition-all text-left overflow-hidden hover:shadow-[0_8px_30px_-8px_rgba(194,114,63,0.2)]"
          >
            {/* Subtle radial glow */}
            <div 
              className="absolute -top-20 -right-20 w-40 h-40 opacity-30 group-hover:opacity-50 transition-opacity pointer-events-none"
              style={{
                background: 'radial-gradient(circle, rgba(234,162,107,0.4) 0%, transparent 70%)'
              }}
            />
            
            {/* Grid pattern overlay - softer orange */}
            <div 
              className="absolute inset-0 opacity-[0.12] group-hover:opacity-[0.18] transition-opacity pointer-events-none"
              style={{
                backgroundImage: 'linear-gradient(to right, rgb(194 114 63 / 0.35) 1px, transparent 1px), linear-gradient(to bottom, rgb(194 114 63 / 0.35) 1px, transparent 1px)',
                backgroundSize: '20px 20px'
              }}
            />
            
            {/* Decorative corner accent */}
            <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
              <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-orange-300/50 to-transparent" />
              <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-orange-300/50 to-transparent" />
            </div>

            {/* AI Powered badge */}
            <div className="absolute top-3 right-3 px-2 py-0.5 bg-orange-500/90 text-white text-[9px] font-bold uppercase tracking-wider rounded-sm flex items-center gap-1">
              <Sparkles className="w-2.5 h-2.5" />
              AI Powered
            </div>
            
            {/* Icon */}
            <div className="w-10 h-10 bg-gradient-to-br from-orange-400/90 to-amber-600/90 text-white flex items-center justify-center transition-all group-hover:from-orange-500 group-hover:to-amber-700 group-hover:shadow-md relative z-10">
              <Video className="w-5 h-5" />
            </div>
            
            {/* Content */}
            <div className="mt-4 space-y-1.5 flex-1 relative z-10 pr-4">
              <h3 className="font-bold text-[15px] text-stone-800 group-hover:text-stone-900 leading-tight">
                From Demonstration
              </h3>
              <p className="text-xs text-stone-500 leading-relaxed">
                Record your actions on the screen. AI will analyze and generate an agent workflow automatically.
              </p>
            </div>
            
            {/* Footer */}
            <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-orange-600/70 font-semibold uppercase tracking-wider group-hover:text-orange-700 transition-colors relative z-10">
              <Play className="w-3 h-3" />
              <span>Start Recording</span>
            </div>
            
            {/* Hover indicator bar */}
            <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-orange-400/80 to-amber-500/80 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
          </button>

          {/* Blank Workflow - Clean neutral card */}
          <button
            onClick={onCreateBlank}
            className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-stone-50/60 via-gray-50/30 to-white border border-stone-200/40 hover:border-stone-300/60 transition-all text-left overflow-hidden hover:shadow-[0_8px_30px_-8px_rgba(120,113,108,0.15)]"
          >
            {/* Subtle radial glow */}
            <div 
              className="absolute -top-20 -right-20 w-40 h-40 opacity-30 group-hover:opacity-50 transition-opacity pointer-events-none"
              style={{
                background: 'radial-gradient(circle, rgba(168,162,158,0.3) 0%, transparent 70%)'
              }}
            />
            
            {/* Grid pattern overlay */}
            <div 
              className="absolute inset-0 opacity-[0.08] group-hover:opacity-[0.14] transition-opacity pointer-events-none"
              style={{
                backgroundImage: 'linear-gradient(to right, rgb(120 113 108 / 0.35) 1px, transparent 1px), linear-gradient(to bottom, rgb(120 113 108 / 0.35) 1px, transparent 1px)',
                backgroundSize: '20px 20px'
              }}
            />
            
            {/* Decorative corner accent */}
            <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
              <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-stone-300/50 to-transparent" />
              <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-stone-300/50 to-transparent" />
            </div>
            
            {/* Icon */}
            <div className="w-10 h-10 bg-gradient-to-br from-stone-400/90 to-stone-600/90 text-white flex items-center justify-center transition-all group-hover:from-stone-500 group-hover:to-stone-700 group-hover:shadow-md relative z-10">
              <FilePlus className="w-5 h-5" />
            </div>
            
            {/* Content */}
            <div className="mt-4 space-y-1.5 flex-1 relative z-10 pr-4">
              <h3 className="font-bold text-[15px] text-stone-800 group-hover:text-stone-900 leading-tight">
                Blank Workflow
              </h3>
              <p className="text-xs text-stone-500 leading-relaxed">
                Start from scratch with an empty canvas. Manually add and connect nodes to build your workflow step by step.
              </p>
            </div>
            
            {/* Footer */}
            <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-stone-500/70 font-semibold uppercase tracking-wider group-hover:text-stone-600 transition-colors relative z-10">
              <FilePlus className="w-3 h-3" />
              <span>Create Blank</span>
            </div>
            
            {/* Hover indicator bar */}
            <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-stone-400/80 to-stone-500/80 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
          </button>

          {/* Vibe Workflow - Grayed out Coming Soon card */}
          <div
            className="group relative flex flex-col items-start p-5 bg-gradient-to-br from-stone-100/60 via-gray-100/30 to-stone-50 border border-stone-200/30 text-left overflow-hidden opacity-60 cursor-not-allowed"
          >
            {/* Subtle radial glow */}
            <div 
              className="absolute -top-20 -right-20 w-40 h-40 opacity-20 pointer-events-none"
              style={{
                background: 'radial-gradient(circle, rgba(168,162,158,0.3) 0%, transparent 70%)'
              }}
            />
            
            {/* Grid pattern overlay */}
            <div 
              className="absolute inset-0 opacity-[0.08] pointer-events-none"
              style={{
                backgroundImage: 'linear-gradient(to right, rgb(168 162 158 / 0.25) 1px, transparent 1px), linear-gradient(to bottom, rgb(168 162 158 / 0.25) 1px, transparent 1px)',
                backgroundSize: '20px 20px'
              }}
            />
            
            {/* Decorative corner accent */}
            <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
              <div className="absolute top-0 right-0 w-[1.5px] h-10 bg-gradient-to-b from-stone-300/30 to-transparent" />
              <div className="absolute top-0 right-0 h-[1.5px] w-10 bg-gradient-to-l from-stone-300/30 to-transparent" />
            </div>

            {/* Coming Soon badge */}
            <div className="absolute top-3 right-3 px-2 py-0.5 bg-stone-400/80 text-white text-[9px] font-bold uppercase tracking-wider rounded-sm flex items-center gap-1">
              <Clock className="w-2.5 h-2.5" />
              Coming Soon
            </div>
            
            {/* Icon */}
            <div className="w-10 h-10 bg-gradient-to-br from-stone-300/90 to-stone-400/90 text-white flex items-center justify-center relative z-10">
              <MessageSquare className="w-5 h-5" />
            </div>
            
            {/* Content */}
            <div className="mt-4 space-y-1.5 flex-1 relative z-10 pr-4">
              <h3 className="font-bold text-[15px] text-stone-500 leading-tight">
                Vibe Workflow
              </h3>
              <p className="text-xs text-stone-400 leading-relaxed">
                Describe what you want in the chat. AI builds the graph with you—you can still drag nodes on the canvas anytime.
              </p>
            </div>
            
            {/* Footer */}
            <div className="mt-4 flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-stone-400/70 font-semibold uppercase tracking-wider relative z-10">
              <MessageSquare className="w-3 h-3" />
              <span>Start Conversation</span>
            </div>
          </div>

        </div>

        {/* Footer hint */}
        <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-[11px] text-black/30 font-medium pt-2">
          <span>Record once for a full draft</span>
          <span className="w-1 h-1 rounded-full bg-black/20 hidden sm:inline" />
          <span>Start blank and build manually</span>
        </div>

      </div>
    </div>
  );
}

