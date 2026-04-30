import React from 'react';

/**
 * 全屏启动加载页 - 与 index.html 内联骨架保持视觉一致
 * 用于 ProtectedRoute、ProjectRedirect、ProjectRoute 等等待阶段
 */
export default function AppLoadingScreen() {
  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center gap-4 bg-[#F8F9FA]">
      <img src={`${import.meta.env.BASE_URL}useit-logo-no-text.svg`} alt="" className="w-14 h-14" />
      <span
        className="text-lg font-bold text-gray-900"
        style={{ letterSpacing: '0.12em', fontFamily: "'Outfit', sans-serif" }}
      >
        USEIT Studio
      </span>
      <div className="w-5 h-5 rounded-full border-2 border-gray-200 border-t-orange-500 animate-spin mt-2" />
    </div>
  );
}
