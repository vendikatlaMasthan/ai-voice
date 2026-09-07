#!/usr/bin/env python3
"""
VoiceShield AI — Ground Truth Evaluation Script (Phase 4)
Evaluates model accuracy against audio samples in test_samples/{human,ai,replay,uncertain}.
Evaluates real audio through /api/analyze, outputs a confusion matrix,
and marks unpopulated folders as untested (no fabricated results).
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEST_SAMPLES_DIR = os.path.join(REPO_ROOT, "test_samples")
LABELS_FILE = os.path.join(TEST_SAMPLES_DIR, "labels.json")
API_URLS = [
    "http://localhost:3000/api/analyze",
    "http://localhost:8000/analyze",
]

SUBFOLDER_LABEL_MAP = {
    "human": "GENUINE_LIVE",
    "ai": "SYNTHETIC_AI_GENERATED",
    "replay": "REPLAYED_RECORDED",
    "uncertain": "UNCERTAIN",
}

CLASSES = ["GENUINE_LIVE", "SYNTHETIC_AI_GENERATED", "REPLAYED_RECORDED", "UNCERTAIN"]
AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")


def classify_verdict(data: Dict[str, Any]) -> str:
    """Derive classification from API response."""
    # First check authoritative contract fields
    if "classification" in data and data["classification"] in CLASSES:
        return data["classification"]
    if "verdict" in data and data["verdict"] in CLASSES:
        return data["verdict"]

    fake_prob = data.get("deepfake_detection", {}).get("fake_probability", 0.0)
    anomaly = data.get("prosody_analysis", {}).get("acoustic_anomaly", 0.0)
    audio_meta = data.get("audio_metadata", {})
    snr = audio_meta.get("estimated_snr_db", 15.0)
    features = data.get("prosody_analysis", {}).get("features", {})
    hf_ratio = features.get("hf_energy_ratio", 0.0)

    ai_likelihood = round(fake_prob * 100)
    naturalness = round(max(0.0, min(1.0, 1.0 - anomaly)) * 100)

    if fake_prob >= 0.65:
        return "SYNTHETIC_AI_GENERATED"
    elif snr < 10:
        return "UNCERTAIN"
    elif anomaly >= 0.65 and fake_prob < 0.35 and hf_ratio < 0.60:
        return "REPLAYED_RECORDED"
    elif (
        (35 <= ai_likelihood <= 65) or
        (40 <= naturalness <= 60 and hf_ratio >= 0.60) or
        (40 <= naturalness <= 60 and 40 <= ai_likelihood <= 60)
    ):
        return "UNCERTAIN"
    elif fake_prob < 0.35 and naturalness > 50 and snr >= 12 and hf_ratio < 0.60:
        return "GENUINE_LIVE"
    else:
        return "UNCERTAIN"


def run_api_analysis(file_path: str) -> Dict[str, Any]:
    boundary = "----WebKitFormBoundaryVoiceShieldEval7MA4YWxkTrZu0gW"
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/octet-stream\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    last_err = None
    for api_url in API_URLS:
        req = urllib.request.Request(api_url, data=body)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            continue

    # If HTTP endpoints are not reachable, fall back to in-process pipeline runner
    try:
        sys.path.insert(0, REPO_ROOT)
        from scripts.run_pipeline import PipelineWorker
        if not hasattr(run_api_analysis, "_worker"):
            run_api_analysis._worker = PipelineWorker()
        worker = run_api_analysis._worker
        return worker.handle_analyze({"file": file_path})
    except Exception as e:
        sys.stderr.write(f"Error analyzing {filename} (HTTP: {last_err}, Direct: {e})\n")
        return {}


def discover_test_samples() -> Dict[str, List[Dict[str, Any]]]:
    """
    Discovers all audio files organized in test_samples/{human,ai,replay,uncertain}.
    Returns a dict mapping category name to list of sample metadata items.
    """
    manifest_notes = {}
    if os.path.exists(LABELS_FILE):
        try:
            with open(LABELS_FILE, "r") as f:
                manifest_data = json.load(f)
                for item in manifest_data:
                    manifest_notes[item.get("filename", "")] = item.get("source_note", "")
                    manifest_notes[os.path.basename(item.get("filename", ""))] = item.get("source_note", "")
        except Exception:
            pass

    categories = {cat: [] for cat in SUBFOLDER_LABEL_MAP.keys()}

    for folder_name, true_label in SUBFOLDER_LABEL_MAP.items():
        folder_path = os.path.join(TEST_SAMPLES_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        for root, _, files in os.walk(folder_path):
            for file in sorted(files):
                if file.lower().endswith(AUDIO_EXTENSIONS):
                    rel_path = os.path.relpath(os.path.join(root, file), TEST_SAMPLES_DIR)
                    abs_path = os.path.join(root, file)
                    note = manifest_notes.get(rel_path) or manifest_notes.get(file, "")
                    categories[folder_name].append({
                        "filename": rel_path,
                        "basename": file,
                        "abs_path": abs_path,
                        "category": folder_name,
                        "true_label": true_label,
                        "source_note": note,
                    })

    return categories


def main():
    print("=" * 75)
    print(" VoiceShield AI — Ground Truth Evaluation Report (Phase 4)")
    print("=" * 75)

    categories = discover_test_samples()

    tested_results = []
    untested_categories = []
    confusion_matrix = {t: {p: 0 for p in CLASSES} for t in CLASSES}

    print("\nDataset Discovery Status:")
    for folder, true_label in SUBFOLDER_LABEL_MAP.items():
        samples = categories.get(folder, [])
        if len(samples) > 0:
            print(f"  [{folder}/] ({true_label}): {len(samples)} audio sample(s) discovered")
        else:
            print(f"  [{folder}/] ({true_label}): UNTESTED (0 audio samples available — no fabricated data)")
            untested_categories.append(folder)

    # Evaluate populated categories
    for folder, samples in categories.items():
        if not samples:
            continue

        for item in samples:
            abs_path = item["abs_path"]
            filename = item["filename"]
            true_label = item["true_label"]
            source_note = item["source_note"]

            api_res = run_api_analysis(abs_path)
            if not api_res:
                print(f"[-] Analysis failed for {filename}")
                continue

            predicted_label = classify_verdict(api_res)
            fake_prob = api_res.get("deepfake_detection", {}).get("fake_probability", 0.0)
            anomaly = api_res.get("prosody_analysis", {}).get("acoustic_anomaly", 0.0)
            naturalness = round(max(0.0, min(1.0, 1.0 - anomaly)), 4)
            snr = api_res.get("audio_metadata", {}).get("estimated_snr_db", 0.0)
            lang = api_res.get("speech_profile", {}).get("detected_language", "Unknown")
            detection_source = api_res.get("deepfake_detection", {}).get("model_id", "wav2vec2-deepfake-voice-detector")

            is_match = (predicted_label == true_label)
            confusion_matrix[true_label][predicted_label] += 1

            tested_results.append({
                "filename": filename,
                "true_label": true_label,
                "predicted_label": predicted_label,
                "is_match": is_match,
                "fake_probability": round(fake_prob, 4),
                "naturalness_score": naturalness,
                "snr_db": round(snr, 2),
                "detected_language": lang,
                "detection_source": detection_source,
                "source_note": source_note,
            })

    # Summary table
    print("\n" + "=" * 75)
    print(" SAMPLE EVALUATION RESULTS:")
    print("=" * 75)
    print(f"{'Filename':<38} | {'True Label':<22} | {'Predicted':<22} | {'Fake%':<6} | {'Match':<5}")
    print("-" * 105)
    for r in tested_results:
        status_sym = "✅" if r["is_match"] else "❌"
        print(f"{r['filename']:<38} | {r['true_label']:<22} | {r['predicted_label']:<22} | {r['fake_probability']*100:>5.1f}% | {status_sym}")

    total = len(tested_results)
    correct = sum(1 for r in tested_results if r["is_match"])
    accuracy = (correct / total * 100.0) if total > 0 else 0.0

    print("\n" + "=" * 75)
    print(f" MEASURED ACCURACY: {accuracy:.1f}% ({correct}/{total} correct on populated test sets)")
    print("=" * 75)

    # Confusion Matrix
    print("\nConfusion Matrix (Rows: Ground Truth, Columns: Predicted):")
    header = f"{'True / Pred':<24} | " + " | ".join(f"{c:<14}" for c in CLASSES)
    print(header)
    print("-" * len(header))
    for t in CLASSES:
        row_str = f"{t:<24} | " + " | ".join(f"{confusion_matrix[t][p]:<14}" for p in CLASSES)
        print(row_str)

    # Untested Status Report
    if untested_categories:
        print("\n" + "=" * 75)
        print(" UNTESTED CATEGORIES STATUS (Honest Reporting):")
        print("=" * 75)
        for cat in untested_categories:
            label = SUBFOLDER_LABEL_MAP[cat]
            print(f" • {cat.upper()} ({label}): UNTESTED (Folder 'test_samples/{cat}/' is currently empty).")
            print(f"   No metrics or accuracy numbers are fabricated for this category.")

    # Missed clones specifically
    missed_clones = [
        r for r in tested_results
        if r["true_label"] == "SYNTHETIC_AI_GENERATED" and r["predicted_label"] != "SYNTHETIC_AI_GENERATED"
    ]

    print("\n" + "=" * 75)
    print(" MISSED CLONE ANALYSIS (SYNTHETIC_AI_GENERATED misclassified):")
    print("=" * 75)
    if missed_clones:
        for mc in missed_clones:
            print(f"❌ File: {mc['filename']}")
            print(f"   Note: {mc['source_note']}")
            print(f"   Predicted as: {mc['predicted_label']} (True: {mc['true_label']})")
            print(f"   Sub-scores:")
            print(f"     - fake_probability: {mc['fake_probability']:.4f}")
            print(f"     - naturalness_score: {mc['naturalness_score']:.4f}")
            print(f"     - audio_clarity_snr: {mc['snr_db']} dB")
            print(f"     - detection_source: {mc['detection_source']}")
    else:
        print("None! All synthetic voice samples were correctly identified as SYNTHETIC_AI_GENERATED.")

    print("\n" + "=" * 75)
    print(" EVALUATION TRANSPARENCY NOTICE:")
    print(f" Results reflect {total} samples in active test categories.")
    print(" Empty categories are flagged as Untested without synthetic inflation.")
    print("=" * 75)


if __name__ == "__main__":
    main()
