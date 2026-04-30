'use client';

import React from 'react';
import { Check, Loader2, Circle, Clock, ArrowRight } from 'lucide-react';

interface Step {
  id: string;
  title: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  time?: string;
}

interface ProgressBarProps {
  steps?: Step[];
}

const defaultSteps: Step[] = [
  { id: '1', title: '任务解析', status: 'completed', time: '2s' },
  { id: '2', title: '环境准备', status: 'completed', time: '15s' },
  { id: '3', title: '执行绘图', status: 'running' },
  { id: '4', title: '质量检查', status: 'pending' },
  { id: '5', title: '导出文件', status: 'pending' },
];

export default function ProgressBar({ steps = defaultSteps }: ProgressBarProps) {
  const activeIndex = steps.findIndex(s => s.status === 'running');
  const progress = activeIndex === -1 
    ? (steps.every(s => s.status === 'completed') ? 100 : 0)
    : (activeIndex / (steps.length - 1)) * 100;

  return (
    <div className="bg-white border-t border-black/[0.04] p-4">
      {/* 顶部信息 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-5 h-5 rounded bg-orange-50 text-orange-600">
            <ActivityIcon />
          </div>
          <span className="text-xs font-semibold text-black/70 uppercase tracking-wider">Workflow Progress</span>
        </div>
        <span className="font-mono text-[10px] text-black/40">ID: 8f2e...9a1c</span>
      </div>

      {/* 进度条轨道 */}
      <div className="relative h-1 bg-black/[0.05] rounded-full mb-4 overflow-hidden">
        <div 
          className="absolute top-0 left-0 h-full bg-orange-500 transition-all duration-1000 ease-out rounded-full"
          style={{ width: `${progress}%` }}
        >
          <div className="absolute top-0 right-0 h-full w-20 bg-gradient-to-r from-transparent to-white/30" />
        </div>
      </div>

      {/* 步骤详情 - 网格布局 */}
      <div className="grid grid-cols-5 gap-2">
        {steps.map((step, index) => {
          const isActive = step.status === 'running';
          const isCompleted = step.status === 'completed';
          const isPending = step.status === 'pending';

          return (
            <div 
              key={step.id}
              className={`
                relative flex flex-col p-2 rounded-lg border transition-all duration-300
                ${isActive 
                  ? 'bg-orange-50/50 border-orange-200 shadow-[0_2px_8px_rgba(255,77,0,0.08)]' 
                  : 'bg-transparent border-transparent hover:bg-black/[0.02]'
                }
              `}
            >
              {/* 状态点 */}
              <div className="flex items-center justify-between mb-1.5">
                <div className={`
                  w-1.5 h-1.5 rounded-full
                  ${isCompleted ? 'bg-green-500' : ''}
                  ${isActive ? 'bg-orange-500 animate-pulse' : ''}
                  ${isPending ? 'bg-black/10' : ''}
                `} />
                {step.time && (
                  <span className="font-mono text-[9px] text-black/30">{step.time}</span>
                )}
              </div>
              
              {/* 标题 */}
              <span className={`text-[11px] font-medium truncate ${
                isActive ? 'text-orange-700' : 
                isCompleted ? 'text-black/60' : 'text-black/30'
              }`}>
                {step.title}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ActivityIcon = () => (
  <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </svg>
);
