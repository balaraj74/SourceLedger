import React from 'react';
import { 
  LayoutDashboard, 
  UploadCloud, 
  Boxes, 
  CheckSquare, 
  ScanLine, 
  ShieldCheck,
  Sliders, 
  FileSpreadsheet,
  HelpCircle,
  LogOut,
  Bot
} from 'lucide-react';
import { ActiveTab } from '../types';
import { useAuth } from '../context/AuthContext';

interface LeftRailProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  reviewQueueCount: number;
}

export const LeftRail: React.FC<LeftRailProps> = ({
  activeTab,
  setActiveTab,
  reviewQueueCount
}) => {
  const navItems = [
    {
      id: 'dashboard' as ActiveTab,
      label: 'Dashboard',
      icon: LayoutDashboard,
      shortcut: '1'
    },
    {
      id: 'quality_dashboard' as ActiveTab,
      label: 'Data Quality & Trust QA',
      icon: ShieldCheck,
      shortcut: 'Q'
    },
    {
      id: 'sources' as ActiveTab,
      label: 'Ingestion & Sources',
      icon: UploadCloud,
      shortcut: '2'
    },
    {
      id: 'catalog' as ActiveTab,
      label: 'Product Catalog',
      icon: Boxes,
      shortcut: '3'
    },
    {
      id: 'review_queue' as ActiveTab,
      label: 'Review Queue',
      icon: CheckSquare,
      badge: reviewQueueCount > 0 ? reviewQueueCount : undefined,
      shortcut: '4'
    },
    {
      id: 'field_inspector' as ActiveTab,
      label: 'Field Inspector',
      icon: ScanLine,
      shortcut: '5'
    },
    {
      id: 'copilot' as ActiveTab,
      label: 'Catalog Copilot & Data Chat',
      icon: Bot,
      shortcut: '7'
    },
    {
      id: 'settings' as ActiveTab,
      label: 'Settings & Model Rules',
      icon: Sliders,
      shortcut: '8'
    }
  ];

  return (
    <aside className="relative z-20 my-auto ml-4 sm:ml-6 w-16 sm:w-18 shrink-0 rounded-[28px] bg-white/70 backdrop-blur-2xl border border-white/80 ring-1 ring-white/50 shadow-[0_12px_36px_rgba(26,23,21,0.08)] flex flex-col items-center py-4 gap-4 transition-all self-center">
      {/* Navigation Dock Items */}
      <div className="flex flex-col items-center gap-3.5 w-full px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <div key={item.id} className="relative group flex items-center justify-center w-full">
              <button
                onClick={() => setActiveTab(item.id)}
                className={`relative w-11 h-11 rounded-2xl flex items-center justify-center transition-all cursor-pointer ${
                  isActive
                    ? 'bg-[#E8622C] text-white shadow-lg shadow-[#E8622C]/30 scale-105 ring-2 ring-white/80'
                    : 'text-[#1A1A1A]/60 hover:text-[#1A1A1A] hover:bg-white/80 hover:scale-105'
                }`}
                aria-label={item.label}
              >
                <Icon className={`w-5 h-5 transition-transform ${isActive ? 'stroke-[2.5]' : 'stroke-[2]'}`} />

                {/* Badge for counts */}
                {item.badge !== undefined && (
                  <span className={`absolute -top-1 -right-1 min-w-[18px] h-[18px] rounded-full text-[10px] font-extrabold flex items-center justify-center px-1 ring-2 ring-white shadow-xs ${
                    isActive ? 'bg-[#191715] text-white' : 'bg-[#E8622C] text-white'
                  }`}>
                    {item.badge}
                  </span>
                )}
              </button>

              {/* Tooltip on hover */}
              <div className="absolute left-full ml-3.5 px-3 py-1.5 bg-[#191715] text-white text-xs font-semibold rounded-xl shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center gap-2 border border-white/10">
                <span>{item.label}</span>
                {item.shortcut && (
                  <span className="text-[10px] text-[#8C8276] px-1.5 py-0.5 bg-white/10 rounded-md font-mono">
                    {item.shortcut}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="w-8 border-t border-[#191715]/10 my-1" />

      {/* Sign Out Button */}
      <SignOutRailButton />
    </aside>
  );
};

const SignOutRailButton: React.FC = () => {
  const { signOut } = useAuth();
  return (
    <div className="relative group flex items-center justify-center w-full px-2">
      <button
        onClick={() => signOut()}
        className="w-11 h-11 rounded-2xl flex items-center justify-center text-[#D45320] hover:bg-[#FFF0ED] hover:scale-105 transition-all cursor-pointer border border-transparent hover:border-[#D45320]/20"
        aria-label="Sign Out"
      >
        <LogOut className="w-5 h-5 stroke-[2]" />
      </button>

      <div className="absolute left-full ml-3.5 px-3 py-1.5 bg-[#191715] text-white text-xs font-semibold rounded-xl shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap border border-white/10">
        <span>Sign Out</span>
      </div>
    </div>
  );
};
