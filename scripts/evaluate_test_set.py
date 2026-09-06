#!/usr/bin/env python3
"""
VoiceShield AI — Standalone Evaluation Script
Evaluates model accuracy against labeled ground truth in test_samples/labels.json.
Produces overall accuracy, confusion matrix, missed clone analysis, and sub-score metrics.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from typing import Dict, List, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEST_SAMPLES_DIR = os.path.join(REPO_ROOT, "test_samples")
LABELS_FILE = os.path.join(TEST_SAMPLES_DIR, "labels.json")
API_URL = "http://localhost:3000/api/analyze"


def classify_verdict(data: Dict[str, Any]) -> str:
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

    req = urllib.request.Request(API_URL, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write(f"Error calling /api/analyze for {filename}: {e}\n")
        return {}


def main():
    if not os.path.exists(LABELS_FILE):
        print(f"Error: Manifest file {LABELS_FILE} does not exist.")
        sys.exit(1)

    with open(LABELS_FILE, "r") as f:
        manifest = json.load(f)

    print("=" * 70)
    print(" VoiceShield AI — Ground Truth Evaluation Report")
    print("=" * 70)
    print(f"Total labeled samples in manifest: {len(manifest)}\n")

    results = []
    classes = ["GENUINE_LIVE", "SYNTHETIC_AI_GENERATED", "REPLAYED_RECORDED", "UNCERTAIN"]
    confusion_matrix = {t: {p: 0 for p in classes} for t in classes}

    for item in manifest:
        filename = item["filename"]
        true_label = item["true_label"]
        source_note = item.get("source_note", "")
        file_path = os.path.join(TEST_SAMPLES_DIR, filename)

        if not os.path.exists(file_path):
            print(f"[-] File not found: {filename} (skipping)")
            continue

        api_res = run_api_analysis(file_path)
        if not api_res:
            print(f"[-] Analysis failed for {filename}")
            continue

        predicted_label = classify_verdict(api_res)
        fake_prob = api_res.get("deepfake_detection", {}).get("fake_probability", 0.0)
        anomaly = api_res.get("prosody_analysis", {}).get("acoustic_anomaly", 0.0)
        naturalness = round(max(0.0, min(1.0, 1.0 - anomaly)), 4)
        snr = api_res.get("audio_metadata", {}).get("estimated_snr_db", 0.0)
        lang = api_res.get("speech_profile", {}).get("detected_language", "Unknown")

        # Reality defender check or local fallback
        detection_source = api_res.get("deepfake_detection", {}).get("model_id", "local_wav2vec2_pipeline")

        is_match = (predicted_label == true_label)
        confusion_matrix[true_label][predicted_label] += 1

        results.append({
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
    print(f"{'Filename':<35} | {'True Label':<22} | {'Predicted':<22} | {'Fake%':<6} | {'Match':<5}")
    print("-" * 100)
    for r in results:
        status_sym = "✅" if r["is_match"] else "❌"
        print(f"{r['filename']:<35} | {r['true_label']:<22} | {r['predicted_label']:<22} | {r['fake_probability']*100:>5.1f}% | {status_sym}")

    total = len(results)
    correct = sum(1 for r in results if r["is_match"])
    accuracy = (correct / total * 100.0) if total > 0 else 0.0

    print("\n" + "=" * 70)
    print(f" MEASURED ACCURACY: {accuracy:.1f}% ({correct}/{total} correct on internal test set)")
    print("=" * 70)

    # Confusion Matrix
    print("\nConfusion Matrix (Rows: True, Columns: Predicted):")
    header = f"{'True / Pred':<24} | " + " | ".join(f"{c:<14}" for c in classes)
    print(header)
    print("-" * len(header))
    for t in classes:
        row_str = f"{t:<24} | " + " | ".join(f"{confusion_matrix[t][p]:<14}" for p in classes)
        print(row_str)

    # Missed clones specifically:
    missed_clones = [
        r for r in results
        if r["true_label"] == "SYNTHETIC_AI_GENERATED" and r["predicted_label"] != "SYNTHETIC_AI_GENERATED"
    ]

    print("\n" + "=" * 70)
    print(" MISSED CLONE ANALYSIS (SYNTHETIC_AI_GENERATED misclassified):")
    print("=" * 70)
    if missed_clones:
        for mc in missed_clones:
            print(f"❌ File: {mc['filename']}")
            print(f"   Note: {mc['source_note']}")
            print(f"   Predicted as: {mc['predicted_label']} (True: {mc['true_label']})")
            print(f"   Sub-scores:")
            print(f"     - synthetic_voice_score (fake_probability): {mc['fake_probability']:.4f}")
            print(f"     - naturalness_score: {mc['naturalness_score']:.4f}")
            print(f"     - audio_clarity_snr: {mc['snr_db']} dB")
            print(f"     - detection_source: {mc['detection_source']}")
            print(f"     - detected_language: {mc['detected_language']}")
    else:
        print("None! All synthetic voice samples were correctly identified as SYNTHETIC_AI_GENERATED.")

    print("\n" + "=" * 70)
    print(" HONEST EVALUATION STATEMENT:")
    print(f" Note: Measured on an internal test set of {total} samples. This is NOT a generalized claim.")
    print("=" * 70)


if __name__ == "__main__":
    main()
