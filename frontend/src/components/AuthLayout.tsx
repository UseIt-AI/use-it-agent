import React, { useEffect, useState } from 'react';
import { Minus, X, Folder } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface AuthLayoutProps {
  children: React.ReactNode;
}

const WindowControlBtn = ({ icon, onClick, hoverColor = 'hover:bg-black/20 hover:text-white', title }: any) => (
  <button
    onClick={onClick}
    title={title}
    className={`w-7 h-[28px] flex items-center justify-center transition-colors rounded-md text-white/80 outline-none focus:outline-none ${hoverColor}`}
  >
    {icon}
  </button>
);

export const AuthLayout: React.FC<AuthLayoutProps> = ({ children }) => {
  const { t } = useTranslation();
  const [countdown, setCountdown] = useState('');

  useEffect(() => {
    const target = new Date(2026, 2, 13, 0, 0, 0, 0); // 2026-03-13 00:00:00 local time
    const update = () => {
      const now = new Date();
      const diff = target.getTime() - now.getTime();
      if (diff <= 0) {
        setCountdown(t('auth.launch.started'));
        return;
      }
      const totalSeconds = Math.floor(diff / 1000);
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor((totalSeconds % 86400) / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      setCountdown(
        t('auth.launch.countdown', {
          days,
          hours: String(hours).padStart(2, '0'),
          minutes: String(minutes).padStart(2, '0'),
          seconds: String(seconds).padStart(2, '0'),
        })
      );
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [t]);

  return (
    <div className="flex flex-col h-screen bg-white font-sans selection:bg-orange-500/20 text-[#1A1A1A] overflow-hidden relative">
      {/*
      ===== 顶部倒计时条 =====
      <div className="absolute top-0 left-0 right-0 h-10 bg-orange-600 border-b border-black/30 z-30 pointer-events-none">
        <div className="absolute top-0 left-0 right-0 h-[1px] bg-black/30" />
        <div className="h-full flex items-center justify-center px-4 text-[10px] font-mono uppercase tracking-[0.2em] text-white/95">
          <div className="flex items-center gap-6">
            <span>{t('auth.launch.title')}</span>
            <span className="text-white">{t('auth.launch.date')}</span>
            <span className="text-white">{countdown}</span>
          </div>
        </div>
      </div>
      */}

      {/* ===== 顶部拖拽区域 (避开右上角按钮区域) ===== */}
      <div 
        className="absolute top-0 left-0 h-10 draggable z-40" 
        style={{ right: '100px' }} 
      />

      {/* ===== 悬浮窗口控制按钮 (右上角) ===== */}
      <div 
        className="absolute top-0 right-0 h-10 px-3 z-[100] flex items-center gap-1"
        style={{ WebkitAppRegion: 'no-drag' } as any}
      >
        <WindowControlBtn 
          onClick={() => (window as any).electron?.minimize()} 
          icon={<Minus className="w-4 h-4" />} 
          hoverColor="hover:bg-black/5 hover:text-black"
        />
        <WindowControlBtn
          onClick={() => (window as any).electron?.close()}
          icon={<X className="w-4 h-4" />}
          hoverColor="hover:bg-black/35 hover:text-white"
        />
      </div>

      {/* ===== 主内容区域 (全屏占满) ===== */}
      <div className="flex-1 min-h-0 relative">
        {children}
      </div>
    </div>
  );
};

