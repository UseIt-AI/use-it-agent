'use client';

import React from 'react';
import { Globe, MessageCircle, Send, Phone, ChevronRight } from 'lucide-react';
import { useRemotePolling } from '@/stores/useRemotePolling';

interface RemoteControlOption {
  id: string;
  name: string;
  icon: React.ReactNode;
  comingSoon: boolean;
  hasToggle?: boolean; // 是否显示开关
}

function RemoteControlItem({ option }: { option: RemoteControlOption }) {
  const { enabled, isPolling, toggle } = useRemotePolling();
  
  // Web 渠道特殊处理：显示开关
  if (option.hasToggle) {
    return (
      <div className="w-full flex items-center gap-2.5 px-2 py-2 rounded-sm">
        {/* Icon */}
        <div className="w-5 h-5 flex items-center justify-center text-black/60 dark:text-white/60">
          {option.icon}
        </div>

        {/* Name */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-black/80 dark:text-white/80 truncate">
              {option.name}
            </span>
            {enabled && (
              <span className="text-[10px] text-black/40 dark:text-white/40">
                {isPolling ? 'Listening...' : 'Ready'}
              </span>
            )}
          </div>
        </div>

        {/* Toggle Switch */}
        <button
          onClick={toggle}
          className={`relative w-9 h-5 rounded-full transition-colors flex-shrink-0 ${
            enabled
              ? 'bg-green-500'
              : 'bg-black/20 dark:bg-white/20'
          }`}
        >
          <div
            className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${
              enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>
    );
  }

  // 其他渠道（Coming Soon）
  return (
    <button
      disabled={option.comingSoon}
      className={`w-full flex items-center gap-2.5 px-2 py-2 rounded-sm transition-colors group text-left ${
        option.comingSoon
          ? 'opacity-60 cursor-not-allowed'
          : 'hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer'
      }`}
    >
      {/* Icon */}
      <div className="w-5 h-5 flex items-center justify-center text-black/60 dark:text-white/60">
        {option.icon}
      </div>

      {/* Name */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-black/80 dark:text-white/80 truncate">
            {option.name}
          </span>
          {option.comingSoon && (
            <span className="px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 rounded">
              Coming Soon
            </span>
          )}
        </div>
      </div>

      {/* Status Indicator & Arrow */}
      <div className="flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full transition-colors ${
            option.comingSoon
              ? 'bg-black/20 dark:bg-white/20'
              : 'bg-green-500'
          }`}
        />
        {/* 保持箭头占位以对齐，Coming Soon 时隐藏但保留空间 */}
        <ChevronRight className={`w-3.5 h-3.5 text-black/30 dark:text-white/30 transition-opacity ${
          option.comingSoon ? 'opacity-0' : 'opacity-0 group-hover:opacity-100'
        }`} />
      </div>
    </button>
  );
}

export function RemoteControlPanel() {
  const options: RemoteControlOption[] = [
    {
      id: 'web',
      name: 'Web',
      icon: <Globe className="w-4 h-4" />,
      comingSoon: false,
      hasToggle: true, // Web 渠道显示开关
    },
    {
      id: 'wechat',
      name: 'WeChat',
      icon: <MessageCircle className="w-4 h-4" />,
      comingSoon: true,
    },
    {
      id: 'telegram',
      name: 'Telegram',
      icon: <Send className="w-4 h-4" />,
      comingSoon: true,
    },
    {
      id: 'whatsapp',
      name: 'WhatsApp',
      icon: <Phone className="w-4 h-4" />,
      comingSoon: true,
    },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center px-3 h-[32px] bg-[#F2F1EE] dark:bg-[#1A1A1A] border-b border-divider flex-shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-widest text-black/40 dark:text-white/40 select-none">
          Remote Control
        </span>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Channels Section */}
        <div className="p-3">
          <div className="text-[10px] font-bold text-black/40 dark:text-white/40 uppercase tracking-wider mb-2 px-2">
            Channels
          </div>
          <div className="space-y-0.5">
            {options.map((option) => (
              <RemoteControlItem key={option.id} option={option} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
