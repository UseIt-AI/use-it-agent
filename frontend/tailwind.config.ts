import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: 'class',
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
        display: ["var(--font-display)"],
      },
      fontSize: {
        // 使用 CSS 变量覆盖或扩展
        'app-xs': 'var(--font-size-xs)',
        'app-sm': 'var(--font-size-sm)',
        'app-base': 'var(--font-size-base)',
        'app-lg': 'var(--font-size-lg)',
        'app-xl': 'var(--font-size-xl)',
        'app-2xl': 'var(--font-size-2xl)',
      },
      colors: {
        canvas: {
          DEFAULT: "var(--bg-primary)", // bg-canvas
          sub: "var(--bg-secondary)",   // bg-canvas-sub
        },
        border: {
          DEFAULT: "var(--border-primary)", // border-border (可能和默认冲突，谨慎使用，推荐 border-divider)
          divider: "var(--border-primary)", // border-divider
        }
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic":
          "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
      },
      animation: {
        'spin-ease': 'spin 1.5s cubic-bezier(0.68, -0.55, 0.265, 1.55) infinite',
        'spin-slow': 'spin 3s linear infinite',
        'shimmer': 'shimmer 3s infinite',
        // 卡片入场动画
        'card-in': 'card-in 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'content-in': 'content-in 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-in-up': 'fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'agent-flash': 'agent-flash 1.5s ease-out forwards',
      },
      keyframes: {
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '10%': { transform: 'translateX(100%)' }, // 快速扫过
          '100%': { transform: 'translateX(100%)' }, // 剩下的时间保持在右侧不可见，等待下一次循环
        },
        // 卡片入场：从下方淡入 + 轻微缩放
        'card-in': {
          '0%': { 
            opacity: '0', 
            transform: 'translateY(8px) scale(0.98)',
          },
          '100%': { 
            opacity: '1', 
            transform: 'translateY(0) scale(1)',
          }
        },
        // 内容入场：简单淡入
        'content-in': {
          '0%': { 
            opacity: '0',
          },
          '100%': { 
            opacity: '1',
          }
        },
        // 淡入上移
        'fade-in-up': {
          '0%': { 
            opacity: '0', 
            transform: 'translateY(6px)',
          },
          '100%': { 
            opacity: '1', 
            transform: 'translateY(0)',
          }
        },
        'agent-flash': {
          '0%': { 
            backgroundColor: 'rgb(255 237 213)',
            transform: 'scale(1.08)',
          },
          '30%': { 
            backgroundColor: 'rgb(255 237 213)',
            transform: 'scale(1)',
          },
          '100%': { 
            backgroundColor: 'transparent',
          }
        },
      },
    },
  },
  plugins: [],
};
export default config;
