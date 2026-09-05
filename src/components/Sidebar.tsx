import React from "react";
import {
  ShieldCheck,
  LayoutDashboard,
  UploadCloud,
  Mic,
  FileCheck,
  History,
  CheckCircle2,
} from "lucide-react";
import { NavTab } from "../types";

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  hasActiveResult: boolean;
  historyCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  hasActiveResult,
  historyCount,
}) => {
  const navItems = [
    {
      id: "dashboard" as NavTab,
      label: "Dashboard",
      subtext: "Overview & summary",
      icon: LayoutDashboard,
    },
    {
      id: "upload" as NavTab,
      label: "Upload Audio",
      subtext: "Scan recorded voice file",
      icon: UploadCloud,
    },
    {
      id: "record" as NavTab,
      label: "Record Voice",
      subtext: "Live microphone test",
      icon: Mic,
    },
    ...(hasActiveResult
      ? [
          {
            id: "results" as NavTab,
            label: "Current Result",
            subtext: "Latest authenticity verdict",
            icon: FileCheck,
          },
        ]
      : []),
    {
      id: "history" as NavTab,
      label: "History",
      subtext: "Past voice checks",
      icon: History,
      count: historyCount,
    },
  ];

  return (
    <aside
      id="app-sidebar"
      className="hidden lg:flex flex-col w-64 bg-slate-950/80 backdrop-blur-md h-screen sticky top-0 z-40 border-r border-slate-800/80 select-none justify-between p-5"
    >
      {/* Brand Header */}
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20 shrink-0">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <div className="min-w-0">
            <span className="text-base font-bold text-white tracking-tight font-sans">
              VoiceShield
            </span>
            <p className="text-[11px] text-slate-400">Voice Safety & Verification</p>
          </div>
        </div>

        {/* Engine Status Callout */}
        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-300 font-medium">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            Detection Engine
          </div>
          <span className="text-[11px] font-semibold text-emerald-400">Ready</span>
        </div>

        {/* Navigation List */}
        <nav className="space-y-1.5 pt-2">
          <div className="px-3 pb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Menu
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                id={`sidebar-nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-left transition-all ${
                  isActive
                    ? "bg-blue-600 text-white font-semibold shadow-sm"
                    : "text-slate-300 hover:text-white hover:bg-slate-900/60"
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-white" : "text-slate-400"}`} />
                  <div className="truncate">
                    <div className="text-xs leading-snug">{item.label}</div>
                    <div className={`text-[10px] truncate ${isActive ? "text-blue-100" : "text-slate-400"}`}>
                      {item.subtext}
                    </div>
                  </div>
                </div>

                {item.count !== undefined && item.count > 0 && (
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                      isActive ? "bg-white/20 text-white" : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {item.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="pt-4 border-t border-slate-800/80 space-y-2 text-xs text-slate-400">
        <div className="flex items-center gap-2 text-slate-400">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>Privacy Assured</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-normal">
          Audio is evaluated directly in memory and not retained.
        </p>
      </div>
    </aside>
  );
};
