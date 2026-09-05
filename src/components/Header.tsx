import React from "react";
import {
  ShieldCheck,
  Cpu,
  Radio,
  UserCheck,
  ShieldAlert,
  FileAudio,
  Sliders,
  Activity,
  Search,
  Zap
} from "lucide-react";
import { HealthResponse } from "../types";
import { NavTab } from "./Sidebar";

interface HeaderProps {
  health: HealthResponse | null;
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  enrolledCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  activeTab,
  onTabChange,
  enrolledCount,
}) => {
  const isHealthy = health?.status === "ok";

  const getTabTitle = (tab: NavTab) => {
    switch (tab) {
      case "live":
        return "Live Call Intercept & Real-Time Telemetry";
      case "analysis":
        return "Audio Payload Forensic Inspection";
      case "speakers":
        return "192-D Biometric Voiceprint Registry";
      case "policy":
        return "Organization Anti-Fraud Policy Controls";
    }
  };

  return (
    <header
      id="main-header"
      className="glass-top-nav w-full sticky top-0 z-30 px-4 sm:px-8 h-16 flex items-center justify-between border-b border-white/10"
    >
      {/* Left: Brand Identity & Active Breadcrumb */}
      <div className="flex items-center gap-3">
        <div className="lg:hidden flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shadow-md">
            <ShieldCheck className="w-4 h-4 text-emerald-300" />
          </div>
          <span className="font-bold text-white text-sm">VoiceShield</span>
        </div>

        <div className="hidden lg:flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">
            VOICESHIELD /
          </span>
          <span className="text-sm font-bold text-white font-sans">
            {getTabTitle(activeTab)}
          </span>
        </div>
      </div>

      {/* Center: Navigation Pills (Visible on md/tablet) */}
      <nav className="hidden sm:flex lg:hidden items-center gap-1 bg-slate-900/60 backdrop-blur-md p-1 rounded-xl border border-white/10">
        <button
          onClick={() => onTabChange("live")}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
            activeTab === "live"
              ? "bg-blue-600 text-white shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          Live
        </button>
        <button
          onClick={() => onTabChange("analysis")}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
            activeTab === "analysis"
              ? "bg-blue-600 text-white shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <FileAudio className="w-3.5 h-3.5" />
          Payload
        </button>
        <button
          onClick={() => onTabChange("speakers")}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
            activeTab === "speakers"
              ? "bg-blue-600 text-white shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <UserCheck className="w-3.5 h-3.5" />
          Profiles ({enrolledCount})
        </button>
        <button
          onClick={() => onTabChange("policy")}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold transition-all ${
            activeTab === "policy"
              ? "bg-blue-600 text-white shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          Policy
        </button>
      </nav>

      {/* Right: Engine Telemetry & System Status */}
      <div className="flex items-center gap-3">
        <div
          id="backend-status-badge"
          className="flex items-center gap-2.5 bg-slate-900/80 backdrop-blur-md border border-white/10 rounded-xl px-3 py-1.5 text-xs text-slate-300 shadow-inner"
        >
          <span className="relative flex h-2 w-2">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                isHealthy ? "bg-emerald-400" : "bg-amber-400"
              }`}
            ></span>
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                isHealthy ? "bg-emerald-500" : "bg-amber-500"
              }`}
            ></span>
          </span>
          <span className="font-semibold font-mono text-slate-200 hidden sm:inline">
            {isHealthy ? "TELEMETRY ACTIVE" : "DAEMON CONNECTING"}
          </span>
          <span className="text-slate-600 hidden sm:inline">|</span>
          <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400">
            <Cpu className="w-3 h-3 text-blue-400" />
            <span>ECAPA + Wav2Vec2</span>
          </div>
        </div>

        {/* Mobile Tab Toggle */}
        <div className="flex sm:hidden bg-slate-900/80 rounded-lg p-1 border border-white/10">
          <button
            onClick={() => onTabChange("live")}
            className={`p-1.5 rounded ${activeTab === "live" ? "bg-blue-600 text-white" : "text-slate-400"}`}
            title="Live Call Monitor"
          >
            <Radio className="w-4 h-4" />
          </button>
          <button
            onClick={() => onTabChange("analysis")}
            className={`p-1.5 rounded ${activeTab === "analysis" ? "bg-blue-600 text-white" : "text-slate-400"}`}
            title="Payload Inspection"
          >
            <FileAudio className="w-4 h-4" />
          </button>
          <button
            onClick={() => onTabChange("speakers")}
            className={`p-1.5 rounded ${activeTab === "speakers" ? "bg-blue-600 text-white" : "text-slate-400"}`}
            title="Speaker Profiles"
          >
            <UserCheck className="w-4 h-4" />
          </button>
          <button
            onClick={() => onTabChange("policy")}
            className={`p-1.5 rounded ${activeTab === "policy" ? "bg-blue-600 text-white" : "text-slate-400"}`}
            title="Policy Controls"
          >
            <Sliders className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};



