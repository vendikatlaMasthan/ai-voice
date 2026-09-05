import React from "react";
import {
  ShieldCheck,
  LayoutDashboard,
  UploadCloud,
  Mic,
  FileCheck,
  History,
} from "lucide-react";
import { NavTab } from "../types";

interface HeaderProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  hasActiveResult: boolean;
  historyCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onTabChange,
  hasActiveResult,
  historyCount,
}) => {
  const tabs = [
    { id: "dashboard" as NavTab, label: "Dashboard", icon: LayoutDashboard },
    { id: "upload" as NavTab, label: "Upload", icon: UploadCloud },
    { id: "record" as NavTab, label: "Record", icon: Mic },
    ...(hasActiveResult
      ? [{ id: "results" as NavTab, label: "Results", icon: FileCheck }]
      : []),
    { id: "history" as NavTab, label: "History", icon: History, count: historyCount },
  ];

  return (
    <header className="w-full bg-slate-950/80 backdrop-blur-md border-b border-slate-800/80 sticky top-0 z-30 px-4 sm:px-6 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Mobile Brand */}
        <div className="flex items-center gap-2.5 lg:hidden">
          <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <span className="text-base font-bold text-white tracking-tight">VoiceShield</span>
        </div>

        {/* Status Indicator */}
        <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Deepfake Voice Detection Online</span>
        </div>

        {/* Mobile Navigation Tabs */}
        <nav className="flex lg:hidden items-center gap-1 overflow-x-auto py-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;

            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors shrink-0 ${
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-slate-400 hover:text-white hover:bg-slate-900"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
                {tab.count !== undefined && tab.count > 0 && (
                  <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300">
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
