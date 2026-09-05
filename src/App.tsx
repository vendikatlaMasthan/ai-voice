import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { Sidebar, NavTab } from "./components/Sidebar";
import { AudioUpload } from "./components/AudioUpload";
import { ContextForm } from "./components/ContextForm";
import { ProcessingView } from "./components/ProcessingView";
import { AnalysisResult } from "./components/AnalysisResult";
import { ErrorAlert } from "./components/ErrorAlert";
import { SpeakerProfiles } from "./components/SpeakerProfiles";
import { LiveAnalysisView } from "./components/LiveAnalysisView";
import { PolicyConfigView } from "./components/PolicyConfigView";
import {
  AnalyzeResponse,
  CallContextState,
  EnrolledSpeaker,
  HealthResponse,
  SampleAudio,
} from "./types";
import {
  analyzeAudio,
  fetchHealth,
  fetchSamples,
  fetchSpeakers,
} from "./api";
import { ShieldCheck, ArrowRight, Activity } from "lucide-react";

export default function App() {
  // Global Navigation
  const [activeTab, setActiveTab] = useState<NavTab>("analysis");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Health & Catalog Data
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [speakers, setSpeakers] = useState<EnrolledSpeaker[]>([]);
  const [samples, setSamples] = useState<SampleAudio[]>([]);

  // Selected Audio State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sampleName, setSampleName] = useState<string | null>(null);

  // Contextual Parameters
  const [context, setContext] = useState<CallContextState>({
    speaker_id: "",
    verification_threshold: 0.70,
    caller_id: "",
    is_caller_recognized: false,
    is_previously_flagged: false,
    claimed_role: "",
    requested_transaction_amount: "",
    normal_transaction_amount: "",
    is_urgent: false,
    urgency_reason: "",
    transcript_text: "",
  });

  // Pipeline Status & Results
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<{ message: string; error_type?: string; status?: number } | null>(null);

  // Load initial backend health, enrolled speakers, and test samples
  const loadInitialData = async () => {
    try {
      const [hData, spkData, sampleData] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchSpeakers(),
        fetchSamples(),
      ]);
      if (hData) setHealth(hData);
      setSpeakers(spkData);
      setSamples(sampleData);
    } catch (e) {
      console.error("Failed to load initial data", e);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const handleFileSelected = (file: File, name: string) => {
    setSelectedFile(file);
    setSampleName(name);
    setResult(null);
    setError(null);
  };

  const handleSelectSample = async (sample: SampleAudio) => {
    try {
      const res = await fetch(sample.url);
      const blob = await res.blob();
      const file = new File([blob], sample.filename, { type: "audio/wav" });
      setSelectedFile(file);
      setSampleName(sample.filename);
      setResult(null);
      setError(null);
    } catch (e) {
      console.error("Failed to load sample audio", e);
    }
  };

  const handleClear = () => {
    setSelectedFile(null);
    setSampleName(null);
    setResult(null);
    setError(null);
  };

  const handleContextChange = (updated: Partial<CallContextState>) => {
    setContext((prev) => ({ ...prev, ...updated }));
  };

  const handleRunAnalysis = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);
    setError(null);
    setResult(null);

    try {
      const analysisResult = await analyzeAudio(selectedFile, sampleName || selectedFile.name, context);
      setResult(analysisResult);
    } catch (err: any) {
      setError({
        message: err.message || "An unexpected error occurred during audio processing.",
        error_type: err.error_type || "AnalysisError",
        status: err.status || 500,
      });
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div id="voiceshield-root" className="min-h-screen relative overflow-x-hidden font-sans text-slate-100 bg-[#070913] flex flex-col selection:bg-purple-500 selection:text-white">
      {/* Dynamic Ambient Blur Blobs */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
        <div className="ambient-blob bg-purple-900/20 w-[650px] h-[650px] -top-40 -left-20 animate-pulse" />
        <div className="ambient-blob bg-indigo-900/25 w-[550px] h-[550px] top-1/3 -right-32 animate-pulse" style={{ animationDelay: "2s" }} />
        <div className="ambient-blob bg-cyan-900/15 w-[700px] h-[700px] -bottom-40 left-1/4 animate-pulse" style={{ animationDelay: "4s" }} />
      </div>

      {/* Top Navigation Bar */}
      <Header
        health={health}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        enrolledCount={speakers.length}
      />

      {/* Main Layout Area with Responsive Sidebar + Content */}
      <div className="flex-1 flex w-full relative z-10">
        {/* Desktop Collapsible Sidebar */}
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          enrolledCount={speakers.length}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        />

        {/* Main Content Container */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6 overflow-y-auto">
          
          {/* Tab 1: Threat Analysis Dashboard */}
          {activeTab === "analysis" && (
            <div className="space-y-6">
              
              {/* 1. Audio Upload & Selection Card */}
              <div className="space-y-4">
                <AudioUpload
                  selectedFile={selectedFile}
                  sampleName={sampleName}
                  onFileSelected={handleFileSelected}
                  onClear={handleClear}
                  samples={samples}
                  onSelectSample={handleSelectSample}
                  isProcessing={isProcessing}
                />
              </div>

              {/* 2. Audio Selected Controls & Fraud Context Configurator */}
              {selectedFile && !result && !error && (
                <div id="analysis-controls-section" className="space-y-4">
                  
                  {/* Optional Anti-Fraud Context & Biometric Threshold */}
                  <ContextForm
                    context={context}
                    onChange={handleContextChange}
                    enrolledSpeakers={speakers}
                    disabled={isProcessing}
                  />

                  {/* Primary Analyze CTA Button */}
                  {!isProcessing && (
                    <div className="flex justify-end pt-2">
                      <button
                        id="btn-analyze-audio"
                        onClick={handleRunAnalysis}
                        disabled={isProcessing}
                        className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-sm flex items-center justify-center gap-2.5 shadow-lg shadow-purple-500/25 transition-all squish-btn font-mono"
                      >
                        <ShieldCheck className="w-5 h-5 text-cyan-300" />
                        Execute Threat Analysis
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  )}

                </div>
              )}

              {/* 3. Processing State View */}
              {isProcessing && <ProcessingView />}

              {/* 4. Analysis Results (Low-Risk, High-Risk, Suspicious) */}
              {result && !isProcessing && (
                <AnalysisResult result={result} onReset={handleClear} />
              )}

              {/* 5. Error State Container */}
              {error && !isProcessing && (
                <ErrorAlert error={error} onReset={handleClear} />
              )}

              {/* 6. Empty Dashboard Placeholder State (When no audio is selected yet) */}
              {!selectedFile && !isProcessing && !result && !error && (
                <div
                  id="empty-dashboard-guide"
                  className="glass-card rounded-2xl p-8 sm:p-10 text-center space-y-4 shadow-xl border border-white/10"
                >
                  <div className="w-14 h-14 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 mx-auto shadow-inner">
                    <Activity className="w-7 h-7" />
                  </div>
                  <div className="space-y-1.5 font-mono">
                    <h3 className="text-base font-bold text-white">
                      Real-Time Pipeline Standing By
                    </h3>
                    <p className="text-xs text-slate-400 max-w-xl mx-auto leading-relaxed">
                      Upload an audio stream recording or select one of the curated test samples above to evaluate synthetic voice likelihood, 192-D biometric voiceprint match, and multi-signal financial fraud risk.
                    </p>
                  </div>
                </div>
              )}

            </div>
          )}

          {/* Tab 2: Live Real-Time Call Monitor */}
          {activeTab === "live" && (
            <LiveAnalysisView
              speakers={speakers}
              samples={samples}
              context={context}
              onContextChange={handleContextChange}
            />
          )}

          {/* Tab 3: Speaker Biometric Profiles Registry */}
          {activeTab === "speakers" && (
            <SpeakerProfiles
              speakers={speakers}
              onRefreshSpeakers={() => fetchSpeakers().then(setSpeakers)}
            />
          )}

          {/* Tab 4: Policy Engine Configuration */}
          {activeTab === "policy" && (
            <PolicyConfigView />
          )}

        </main>
      </div>

      {/* Footer */}
      <footer className="w-full relative z-10 border-t border-white/10 bg-black/40 backdrop-blur-md py-4 text-center text-xs text-slate-400">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2 font-mono">
          <span>VoiceShield &bull; Multi-Signal Anti-Spoofing & Biometric Verification</span>
          <span className="text-[11px] text-purple-400">Wav2Vec2 Deepfake + ECAPA-TDNN Biometrics + Acoustic Prosody</span>
        </div>
      </footer>
    </div>
  );
}

