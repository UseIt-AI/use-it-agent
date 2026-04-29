import React, { useRef, useEffect, useState } from 'react';
import { Settings, LogOut } from 'lucide-react';

interface DropdownMenuProps {
  onLogout: () => void;
  trigger: React.ReactNode;
}

export const DropdownMenu: React.FC<DropdownMenuProps> = ({ onLogout, trigger }) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative z-50" ref={menuRef}>
      <div onClick={() => setIsOpen(!isOpen)}>{trigger}</div>
      
      {isOpen && (
        <div className="absolute right-0 top-full mt-1 w-48 bg-white rounded-md shadow-lg border border-black/10 py-1 animate-in fade-in zoom-in-95 duration-100 origin-top-right">
          <div className="px-3 py-2 border-b border-gray-100">
            <p className="text-xs font-medium text-gray-500">System</p>
          </div>
          <button
            onClick={() => {
              setIsOpen(false);
              // TODO: Open Settings
            }}
            className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Settings</span>
          </button>
          <div className="border-t border-gray-100 my-1"></div>
          <button
            onClick={() => {
              setIsOpen(false);
              onLogout();
            }}
            className="w-full text-left px-3 py-2 text-xs text-red-600 hover:bg-red-50 flex items-center gap-2"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out</span>
          </button>
        </div>
      )}
    </div>
  );
};

