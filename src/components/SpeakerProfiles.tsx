import React, { useState, useRef } from "react";
import {
  UserPlus,
  Fingerprint,
  CheckCircle2,
  AlertTriangle,
  Upload,
  Clock,
  Database,
  Layers,
  XCircle,
  FileAudio,
  Shield,
  Loader2,
  RefreshCw,
  UserCheck
} from "lucide-react";
import { EnrolledSpeaker, EnrollmentResponse, VerifySpeakerResponse } from "../types";
import { enrollSpeaker, verifySpeakerApi } from "../api";

interface SpeakerProfilesProps {
  speakers: EnrolledSpeaker[];
  onRefreshSpeakers: () => void;
}

export const SpeakerProfiles: React.FC<SpeakerProfilesProps> = ({
  speakers,
  onRefreshSpeakers,
}) => {
  // Enrollment Form State
  const [enrollId, setEnrollId] = useState("");
  const [enrollName, setEnrollName] = useState("");
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [isEnrolling, setIsEnrolling] = useState(false);
  const [enrollResult, setEnrollResult] = useState<EnrollmentResponse | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const enrollInputRef = useRef<HTMLInputElement | null>(null);

  // Standalone Verification State
  const [verifySpeakerId, setVerifySpeakerId] = useState("");
  const [verifyFile, setVerifyFile] = useState<File | null>(null);
  const [verifyThreshold, setVerifyThreshold] = useState(0.70);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifySpeakerResponse | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const verifyInputRef = useRef<HTMLInputElement | null>(null);

  const handleEnrollSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enrollId.trim()) {
      setEnrollError("Speaker ID is required.");
      return;
    }
    if (!enrollFile) {
      setEnrollError("Reference voice audio file (.wav, .flac) is required.");
      return;
    }

    setIsEnrolling(true);
    setEnrollError(null);
    setEnrollResult(null);

    try {
      const res = await enrollSpeaker(enrollFile, enrollFile.name, enrollId.trim(), enrollName.trim() || undefined);
      setEnrollResult(res);
      setEnrollFile(null);
      setEnrollId("");
      setEnrollName("");
      onRefreshSpeakers();
    } catch (err: any) {
      setEnrollError(err.message || "Failed to enroll speaker.");
    } finally {
      setIsEnrolling(false);
    }
  };

  const handleVerifySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!verifySpeakerId.trim()) {
      setVerifyError("Please select or enter an enrolled Speaker ID.");
      return;
    }
    if (!verifyFile) {
      setVerifyError("Query audio sample file is required.");
      return;
    }

    setIsVerifying(true);
    setVerifyError(null);
    setVerifyResult(null);

    try {
      const res = await verifySpeakerApi(verifyFile, verifyFile.name, verifySpeakerId.trim(), verifyThreshold);
      setVerifyResult(res);
    } catch (err: any) {
      setVerifyError(err.message || "Speaker verification failed.");
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div id="speaker-profiles-view" className="space-y-6">
      
      {/* Privacy Guarantee Header Banner */}
      <div className="glass-card rounded-2xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 border border-white/10 shadow-xl">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shrink-0 mt-0.5 shadow-sm">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-white">
                Biometric Speaker Verification Registry (Phase 5)
              </h2>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                ECAPA-TDNN
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Extracts 192-dimensional L2-normalized vector embeddings. 
              <strong className="text-slate-200"> Zero raw audio is stored:</strong> reference audio arrays are discarded immediately after embedding computation to protect privacy.
            </p>
          </div>
        </div>

        <button
          onClick={onRefreshSpeakers}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-semibold font-mono transition-all shadow-sm self-start md:self-center shrink-0 squish-btn"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh Store ({speakers.length})
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Card 1: Enroll Genuine Speaker */}
        <div id="enrollment-card" className="glass-card rounded-2xl p-6 space-y-5 shadow-xl border border-white/10">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <UserPlus className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-bold text-white">
                Enroll Genuine Voice Profile
              </h3>
            </div>
            <span className="text-[11px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">POST /enroll</span>
          </div>

          <form onSubmit={handleEnrollSubmit} className="space-y-4 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300 font-mono">
                  Speaker Identifier *
                </label>
                <input
                  id="enroll-speaker-id-input"
                  type="text"
                  placeholder="e.g. EMP-9001, CEO-JANE"
                  value={enrollId}
                  onChange={(e) => setEnrollId(e.target.value)}
                  disabled={isEnrolling}
                  className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 shadow-inner font-mono"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300 font-mono">
                  Display / Role Name (Optional)
                </label>
                <input
                  id="enroll-speaker-name-input"
                  type="text"
                  placeholder="e.g. Jane Doe (CEO)"
                  value={enrollName}
                  onChange={(e) => setEnrollName(e.target.value)}
                  disabled={isEnrolling}
                  className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 shadow-inner font-mono"
                />
              </div>
            </div>

            {/* Audio Upload for Enrollment */}
            <div className="space-y-1.5">
              <label className="font-semibold text-slate-300 font-mono">
                Reference Audio Sample (.wav, .flac) *
              </label>
              <input
                ref={enrollInputRef}
                type="file"
                accept="audio/*,.wav,.flac"
                onChange={(e) => e.target.files?.[0] && setEnrollFile(e.target.files[0])}
                disabled={isEnrolling}
                className="hidden"
                id="enroll-file-input"
              />

              {!enrollFile ? (
                <div
                  onClick={() => !isEnrolling && enrollInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-700 hover:border-purple-500 rounded-2xl p-5 text-center cursor-pointer transition-all bg-black/40 hover:bg-black/60 shadow-inner"
                >
                  <Upload className="w-6 h-6 text-purple-400 mx-auto mb-1.5" />
                  <div className="text-slate-200 font-bold font-mono">Select Reference Voice Audio</div>
                  <div className="text-[11px] text-slate-400 mt-0.5 font-mono">1.0s – 30.0s clean speech for 192-D biometric extraction</div>
                </div>
              ) : (
                <div className="flex items-center justify-between p-3.5 rounded-xl bg-black/40 border border-white/10 shadow-sm">
                  <div className="flex items-center gap-2.5 min-w-0 font-mono">
                    <FileAudio className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className="text-white font-semibold truncate">{enrollFile.name}</span>
                    <span className="text-slate-400 text-[11px]">({(enrollFile.size / 1024).toFixed(1)} KB)</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setEnrollFile(null)}
                    className="text-slate-400 hover:text-white font-semibold text-xs px-2 py-1 font-mono"
                  >
                    Change
                  </button>
                </div>
              )}
            </div>

            {enrollError && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-start gap-2 font-mono">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <span>{enrollError}</span>
              </div>
            )}

            {enrollResult && (
              <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300 space-y-1.5 font-mono">
                <div className="font-bold flex items-center gap-1.5 text-emerald-300">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Enrollment Successful!
                </div>
                <div className="text-slate-300 text-[11px] space-y-0.5">
                  <div>Speaker: <strong className="text-white">{enrollResult.speaker_id}</strong> {enrollResult.speaker_name ? `(${enrollResult.speaker_name})` : ""}</div>
                  <div>Embedding Dimension: <strong className="text-white">{enrollResult.embedding_dimension}-D</strong> Vector</div>
                  <div>Inference Latency: <strong className="text-white">{enrollResult.inference_time_ms} ms</strong></div>
                  <div>Sample Rate Verified: <strong className="text-white">{enrollResult.sample_rate_verified} Hz</strong></div>
                </div>
              </div>
            )}

            <button
              id="submit-enroll-btn"
              type="submit"
              disabled={isEnrolling || !enrollId.trim() || !enrollFile}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg squish-btn font-mono"
            >
              {isEnrolling ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Extracting 192-D Embedding...
                </>
              ) : (
                <>
                  <Fingerprint className="w-4 h-4" />
                  Enroll Speaker Profile
                </>
              )}
            </button>
          </form>
        </div>

        {/* Card 2: Standalone Biometric Verifier */}
        <div id="verify-card" className="glass-card rounded-2xl p-6 space-y-5 shadow-xl border border-white/10">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                <Fingerprint className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-bold text-white">
                Standalone Biometric Verifier
              </h3>
            </div>
            <span className="text-[11px] font-mono font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">POST /verify-speaker</span>
          </div>

          <form onSubmit={handleVerifySubmit} className="space-y-4 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-300 font-mono">
                  Select Enrolled Speaker *
                </label>
                <select
                  id="verify-speaker-select"
                  value={verifySpeakerId}
                  onChange={(e) => setVerifySpeakerId(e.target.value)}
                  disabled={isVerifying}
                  className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-white text-xs focus:outline-none focus:border-blue-500 shadow-inner font-mono"
                  required
                >
                  <option value="" disabled className="bg-slate-900">-- Choose Speaker --</option>
                  {speakers.map((s) => (
                    <option key={s.speaker_id} value={s.speaker_id} className="bg-slate-900">
                      {s.speaker_id} {s.speaker_name ? `(${s.speaker_name})` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between font-mono">
                  <label className="font-semibold text-slate-300">
                    Threshold (τ):
                  </label>
                  <span className="text-blue-400 font-bold bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">{verifyThreshold.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.50"
                  max="0.95"
                  step="0.01"
                  value={verifyThreshold}
                  onChange={(e) => setVerifyThreshold(parseFloat(e.target.value))}
                  disabled={isVerifying}
                  className="w-full accent-blue-500 mt-1"
                />
              </div>
            </div>

            {/* Query Audio Upload */}
            <div className="space-y-1.5">
              <label className="font-semibold text-slate-300 font-mono">
                Query Audio File to Compare *
              </label>
              <input
                ref={verifyInputRef}
                type="file"
                accept="audio/*,.wav,.flac,.mp3"
                onChange={(e) => e.target.files?.[0] && setVerifyFile(e.target.files[0])}
                disabled={isVerifying}
                className="hidden"
                id="verify-file-input"
              />

              {!verifyFile ? (
                <div
                  onClick={() => !isVerifying && verifyInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-700 hover:border-blue-500 rounded-2xl p-5 text-center cursor-pointer transition-all bg-black/40 hover:bg-black/60 shadow-inner"
                >
                  <Upload className="w-6 h-6 text-blue-400 mx-auto mb-1.5" />
                  <div className="text-slate-200 font-bold font-mono">Select Test Audio Stream</div>
                  <div className="text-[11px] text-slate-400 mt-0.5 font-mono">Computes cosine similarity against enrolled 192-D vector</div>
                </div>
              ) : (
                <div className="flex items-center justify-between p-3.5 rounded-xl bg-black/40 border border-white/10 shadow-sm font-mono">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <FileAudio className="w-4 h-4 text-blue-400 shrink-0" />
                    <span className="text-white font-semibold truncate">{verifyFile.name}</span>
                    <span className="text-slate-400 text-[11px]">({(verifyFile.size / 1024).toFixed(1)} KB)</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setVerifyFile(null)}
                    className="text-slate-400 hover:text-white font-semibold text-xs px-2 py-1 font-mono"
                  >
                    Change
                  </button>
                </div>
              )}
            </div>

            {verifyError && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-start gap-2 font-mono">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <span>{verifyError}</span>
              </div>
            )}

            {verifyResult && (
              <div
                className={`p-3.5 rounded-xl border text-xs space-y-2 font-mono ${
                  verifyResult.match
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                    : "bg-red-500/10 border-red-500/30 text-red-300"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-bold flex items-center gap-1.5">
                    {verifyResult.match ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-400" />
                    )}
                    {verifyResult.match ? "BIOMETRIC MATCH (VERIFIED)" : "BIOMETRIC MISMATCH (DISCREPANCY)"}
                  </div>
                  <span className="text-[11px]">
                    Latency: {verifyResult.inference_time_ms} ms
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] bg-black/40 p-2.5 rounded-lg border border-white/5 font-mono">
                  <div>Cosine Similarity: <strong className="text-white">{verifyResult.similarity_score}</strong></div>
                  <div>Decision Threshold: <strong className="text-white">{verifyResult.threshold}</strong></div>
                  <div>Centroid Samples: <strong className="text-cyan-300">{verifyResult.sample_count || 1}</strong></div>
                  <div>Mismatch Flag (M): <strong className="text-white">{verifyResult.speaker_mismatch_flag}</strong></div>
                  <div>Status: <strong className="text-white">{verifyResult.status}</strong></div>
                  <div>Inference Time: <strong className="text-white">{verifyResult.inference_time_ms} ms</strong></div>
                </div>
              </div>
            )}

            <button
              id="submit-verify-btn"
              type="submit"
              disabled={isVerifying || !verifySpeakerId || !verifyFile}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg squish-btn font-mono"
            >
              {isVerifying ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Comparing Acoustic Embeddings...
                </>
              ) : (
                <>
                  <Fingerprint className="w-4 h-4" />
                  Verify Biometric Similarity
                </>
              )}
            </button>
          </form>
        </div>

      </div>

      {/* Card 3: Active Registered Profiles Table */}
      <div id="enrolled-speakers-table" className="glass-card rounded-2xl p-6 space-y-4 shadow-xl border border-white/10">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-bold text-white">
              Active Registered Speaker Profiles ({speakers.length})
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">Multi-Sample Centroid Store (192-D)</span>
        </div>

        {speakers.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-black/30 border border-white/5 space-y-2">
            <Layers className="w-8 h-8 text-slate-500 mx-auto" />
            <div className="text-sm font-bold text-slate-300">No Speakers Enrolled Yet</div>
            <p className="text-xs text-slate-400 max-w-sm mx-auto font-mono">
              Enroll genuine executives, callers, or authorized users above to enable biometric mismatch fraud defense.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="text-slate-400 border-b border-white/10 bg-white/5 font-mono">
                <tr>
                  <th className="py-2.5 px-3 font-bold">Speaker ID</th>
                  <th className="py-2.5 px-3 font-bold">Display Name</th>
                  <th className="py-2.5 px-3 font-bold">Genuine Samples</th>
                  <th className="py-2.5 px-3 font-bold">Embedding Centroid</th>
                  <th className="py-2.5 px-3 font-bold">Last Updated</th>
                  <th className="py-2.5 px-3 text-right font-bold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-mono text-slate-300">
                {speakers.map((s) => (
                  <tr key={s.speaker_id} className="hover:bg-white/5 transition-colors">
                    <td className="py-3 px-3 font-bold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      {s.speaker_id}
                    </td>
                    <td className="py-3 px-3 text-slate-200">
                      {s.speaker_name || "—"}
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                        {s.sample_count || 1} {s.sample_count === 1 ? "Sample" : "Samples (Centroid)"}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-purple-400 font-bold">
                      192-D (L2 Norm)
                    </td>
                    <td className="py-3 px-3 text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      {new Date((s.updated_at || s.created_at) * 1000).toLocaleTimeString()}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => {
                          setVerifySpeakerId(s.speaker_id);
                        }}
                        className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-[11px] text-white font-mono font-semibold transition-colors squish-btn"
                      >
                        Test Verify
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
};


