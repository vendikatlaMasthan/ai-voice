import React from "react";
import {
  ShieldCheck,
  Radio,
  FileAudio,
  UserCheck,
  ShieldAlert,
  Sliders,
  Activity,
  Terminal,
  ChevronRight,
  Zap,
  Lock,
  Cpu,
  HelpCircle,
  ExternalLink
} from "lucide-react";

export type NavTab = "live" | "analysis" | "speakers" | "policy";

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  enrolledCount: number;
  threatCount?: number;
  isStreaming?: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  enrolledCount,
  threatCount = 0,
  isStreaming = false,
}) => {
  const navItems = [
    {
      id: "live" as NavTab,
      label: "Live Call Intercept",
      subtext: "Real-time stream & biometrics",
      icon: Radio,
      badge: isStreaming ? "STREAMING" : "LIVE",
      badgeColor: isStreaming
        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
        : "bg-blue-500/20 text-blue-300 border-blue-500/30",
    },
    {
      id: "analysis" as NavTab,
      label: "Payload Inspection",
      subtext: "Single audio file deep scan",
      icon: FileAudio,
    },
    {
      id: "speakers" as NavTab,
      label: "Voice Biometrics",
      subtext: "192-D ECAPA profile store",
      icon: UserCheck,
      count: enrolledCount,
    },
    {
      id: "policy" as NavTab,
      label: "Policy Engine",
      subtext: "Thresholds & step-up routing",
      icon: Sliders,
    },
  ];

  return (
    <aside
      id="stitch-sidebar"
      className="hidden lg:flex flex-col w-64 glass-nav h-screen sticky top-0 z-40 border-r border-white/10 select-none justify-between p-4 overflow-y-auto"
    >
      {/* Brand Header */}
      <div className="space-y-6">
        <div className="flex items-center gap-3 px-2 py-1">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white flex items-center justify-center shadow-lg shadow-blue-500/20 border border-white/20 shrink-0">
            <ShieldCheck className="w-6 h-6 text-emerald-300" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-base font-extrabold text-white tracking-tight font-sans">
                VoiceShield
              </span>
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-400/30">
                PRO
              </span>
            </div>
            <p className="text-[10px] text-slate-400 font-mono truncate">
              SIH 2026 #26104 &bull; SOC Tier-1
            </p>
          </div>
        </div>

        {/* Status Callout Pill */}
        <div className="glass-panel-darker rounded-xl p-3 border border-white/10 space-y-1.5">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400 font-mono flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              Engine Online
            </span>
            <span className="text-[10px] font-mono text-emerald-400 font-bold">FP16 CUDA</span>
          </div>
          <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
            <span>Wav2Vec2 + ECAPA</span>
            <span>&lt; 350ms</span>
          </div>
        </div>

        {/* Navigation Item List */}
        <nav className="space-y-1">
          <div className="px-3 pb-2 text-[10px] font-bold font-mono uppercase tracking-wider text-slate-400">
            Navigation & Analytics
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                id={`sidebar-nav-${item.id}`}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-left transition-all group squish-btn ${
                  isActive
                    ? "bg-gradient-to-r from-blue-600/30 to-indigo-600/20 border border-blue-400/40 text-white shadow-md"
                    : "text-slate-300 hover:text-white hover:bg-white/5 border border-transparent"
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                      isActive
                        ? "bg-blue-500 text-white shadow-sm shadow-blue-500/50"
                        : "bg-white/5 text-slate-400 group-hover:text-blue-400 group-hover:bg-white/10"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="truncate">
                    <div className="text-xs font-semibold leading-snug">{item.label}</div>
                    <div className="text-[10px] text-slate-400 truncate">{item.subtext}</div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0 pl-1">
                  {item.badge && (
                    <span
                      className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-full border ${item.badgeColor}`}
                    >
                      {item.badge}
                    </span>
                  )}
                  {item.count !== undefined && (
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                        isActive
                          ? "bg-blue-400/30 text-blue-200"
                          : "bg-slate-800 text-slate-400 group-hover:text-slate-200"
                      }`}
                    >
                      {item.count}
                    </span>
                  )}
                  {isActive && <ChevronRight className="w-3.5 h-3.5 text-blue-400" />}
                </div>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer Profile & Security Specs */}
      <div className="pt-4 border-t border-white/10 space-y-3">
        <div className="glass-card rounded-xl p-3 flex items-center justify-between border border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center text-slate-950 font-bold text-xs shadow-sm">
              SO
            </div>
            <div>
              <div className="text-xs font-bold text-slate-200">Security Analyst</div>
              <div className="text-[10px] text-slate-400 font-mono">Org: voice-shield-core</div>
            </div>
          </div>
          <div className="w-2 h-2 rounded-full bg-emerald-400" title="Active Tenant Isolated" />
        </div>

        <div className="flex items-center justify-between px-2 text-[10px] text-slate-500 font-mono">
          <span>v2.4.0 &bull; Auth-Enforced</span>
          <span className="text-blue-400/80 hover:text-blue-300 cursor-pointer flex items-center gap-0.5">
            Docs <ExternalLink className="w-2.5 h-2.5" />
          </span>
        </div>
      </div>
    </aside>
  );
};
