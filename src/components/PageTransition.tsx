import React from 'react';
import { useLocation } from 'react-router-dom';

interface PageTransitionProps {
  children: React.ReactNode;
}

/**
 * 页面过渡动画组件
 * 简洁优雅的淡入 + 轻微上滑效果
 */
export const PageTransition: React.FC<PageTransitionProps> = ({ children }) => {
  const location = useLocation();

  return (
    <div
      key={location.pathname}
      className="page-transition page-enter"
    >
      {children}
    </div>
  );
};

// 添加样式
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  .page-transition {
    width: 100%;
    height: 100%;
  }
  
  .page-enter {
    animation: pageEnter 0.35s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }
  
  @keyframes pageEnter {
    from {
      opacity: 0;
      transform: translateY(12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

if (typeof document !== 'undefined' && !document.getElementById('page-transition-styles')) {
  styleSheet.id = 'page-transition-styles';
  document.head.appendChild(styleSheet);
}

export default PageTransition;
