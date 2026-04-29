import { Maximize2, Minus, X } from "lucide-react";

{/* 顶部系统栏 */}
const WindowHeader = ()=>{
    return <header className="draggable flex items-center justify-between px-3 h-[32px] bg-transparent border-b border-black/5 flex-shrink-0 z-10">
        <div className="flex items-center gap-2 select-none">
          <img 
            src="./useit-logo-no-text.svg" 
            alt="UseIt Logo" 
            className="w-4 h-4"
          />
          <span className="text-xs font-bold text-black/80 tracking-tight">UseIt</span>
        </div>
        <div className="flex items-center gap-1 no-drag">
          <WindowControlButton
            onClick={() => (window.electron as any)?.minimize?.()}
            icon={<Minus className="w-3.5 h-3.5" />}
            title="Minimize"
          />
          <WindowControlButton
            onClick={() => (window.electron as any)?.toggleMaximize?.()}
            icon={<Maximize2 className="w-3.5 h-3.5" />}
            title="Maximize"
          />
          <WindowControlButton
            onClick={() => (window.electron as any)?.close?.()}
            icon={<X className="w-3.5 h-3.5" />}
            title="Close"
            hoverColor="hover:bg-red-600 hover:text-white"
          />
        </div>
      </header>
}

export default WindowHeader

export const WindowControlButton = ({ icon, onClick, hoverColor = 'hover:bg-black/5 hover:text-black', title }: any) => (
  <button
    onClick={onClick}
    title={title}
    className={`w-7 h-[28px] flex items-center justify-center transition-colors rounded-sm text-black/40 ${hoverColor}`}
  >
    {icon}
  </button>
);

