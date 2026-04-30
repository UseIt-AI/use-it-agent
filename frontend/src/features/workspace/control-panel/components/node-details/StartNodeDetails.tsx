import React from 'react';
import { FileText, Type } from 'lucide-react';

export function StartNodeDetails() {
  return (
    <div className="flex flex-col gap-4">
      {/* 支持的输入类型 */}
      <div className="flex flex-col gap-2">
        <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider">Supported Inputs</span>

        {/* Text Input Item */}
        <div className="flex items-center gap-2 p-2 bg-white border border-black/5 rounded-sm">
          <div className="w-6 h-6 flex items-center justify-center bg-black/5 rounded-sm text-black/60">
            <Type className="w-3.5 h-3.5" />
          </div>
          <span className="text-[11px] text-black/80 font-medium">Text Input</span>
        </div>

        {/* File Upload Item */}
        <div className="flex items-center gap-2 p-2 bg-white border border-black/5 rounded-sm">
          <div className="w-6 h-6 flex items-center justify-center bg-black/5 rounded-sm text-black/60">
            <FileText className="w-3.5 h-3.5" />
          </div>
          <span className="text-[11px] text-black/80 font-medium">File Upload</span>
        </div>
      </div>
    </div>
  );
}


