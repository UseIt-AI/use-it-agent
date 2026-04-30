import React from 'react';

// 紧凑型设置项（label 与控件同一行）
export function SettingInline({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[10px] font-bold text-black/40 uppercase tracking-wider whitespace-nowrap">
        {label}
      </span>
      <div className="flex-1 flex justify-end">{children}</div>
    </div>
  );
}


