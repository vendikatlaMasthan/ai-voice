import React, { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { DashboardView } from "./components/DashboardView";
import { UploadView } from "./components/UploadView";
import { RecordView } from "./components/RecordView";
import { AnalysisResult } from "./components/AnalysisResult";
import { HistoryView } from "./components/HistoryView";
import { AnalysisRecord, NavTab, SampleAudio } from "./types";
import { analyzeAudio, fetchSamples } from "./api";

const STORAGE_KEY = "voiceshield_history_v1";

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [samples, setSamples] = useState<SampleAudio[]>([]);
  const [history, setHistory] = useState<AnalysisRecord[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [currentResult, setCurrentResult] = useState<AnalysisRecord | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSamples().then((data) => setSamples(data));
  }, []);

  const saveToHistory = (record: AnalysisRecord) => {
    setHistory((prev) => {
      const updated = [record, ...prev];
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (err) {
        console.error("Failed to save history:", err);
      }
      return updated;
    });
  };

  const handleClearHistory = () => {
    setHistory([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error("Failed to clear history:", err);
    }
  };

  const handleAnalyze = async (file: File | Blob, name: string) => {
    setIsProcessing(true);
    setError(null);

    try {
      const result = await analyzeAudio(file, name);
      setCurrentResult(result);
      saveToHistory(result);
      setActiveTab("results");
    } catch (err: any) {
      console.error("Analysis failed:", err);
      setError(err.message || "Failed to analyze audio sample.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSelectRecord = (record: AnalysisRecord) => {
    setCurrentResult(record);
    setActiveTab("results");
  };

  return (
    <div className="min-h-screen bg-[#070913] text-slate-100 flex flex-col font-sans selection:bg-blue-500 selection:text-white">
      {/* Dynamic Ambient Blur Blobs */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
        <div className="ambient-blob bg-blue-900/15 w-[600px] h-[600px] -top-40 -left-20" />
        <div className="ambient-blob bg-indigo-900/15 w-[500px] h-[500px] top-1/2 -right-32" />
      </div>

      <div className="flex-1 flex w-full relative z-10">
        {/* Desktop Sidebar */}
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          hasActiveResult={currentResult !== null}
          historyCount={history.length}
        />

        {/* Content Area */}
        <div className="flex-1 flex flex-col min-w-0">
          <Header
            activeTab={activeTab}
            onTabChange={setActiveTab}
            hasActiveResult={currentResult !== null}
            historyCount={history.length}
          />

          <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-8 py-8 overflow-y-auto">
            {activeTab === "dashboard" && (
              <DashboardView
                history={history}
                onNavigate={setActiveTab}
                onSelectRecord={handleSelectRecord}
              />
            )}

            {activeTab === "upload" && (
              <UploadView
                samples={samples}
                onAnalyze={handleAnalyze}
                isProcessing={isProcessing}
                error={error}
              />
            )}

            {activeTab === "record" && (
              <RecordView
                onAnalyze={handleAnalyze}
                isProcessing={isProcessing}
                error={error}
              />
            )}

            {activeTab === "results" && currentResult && (
              <AnalysisResult
                record={currentResult}
                onAnalyzeAnother={() => setActiveTab("upload")}
              />
            )}

            {activeTab === "history" && (
              <HistoryView
                history={history}
                onSelectRecord={handleSelectRecord}
                onClearHistory={handleClearHistory}
                onNavigate={setActiveTab}
              />
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
