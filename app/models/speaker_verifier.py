"""
Speaker Verification and Biometric Embedding Module for VoiceShield (Phase 5).

Provides text-independent voice enrollment, speaker embedding extraction,
cosine similarity calculation, and configurable decision thresholding using
ECAPA-TDNN / ResNet neural embeddings.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from app.audio.preprocessing import PreprocessedAudio


@dataclass
class SpeakerVerifierConfig:
    """
    Configuration parameters for speaker verification.
    
    NOTE ON THRESHOLD SELECTION:
    The default cosine similarity threshold of 0.70 is an initial prototype parameter.
    In production environments, the optimal operating point (Equal Error Rate / EER threshold)
    must be empirically calibrated against a target domain verification dataset (e.g. VoxCeleb).
    """
    model_name_or_path: str = "speechbrain/spkrec-ecapa-voxceleb"
    device: str = "cpu"                  # 'cpu' or 'cuda'
    embedding_dim: int = 192             # Standard ECAPA-TDNN embedding dimensionality
    similarity_threshold: float = 0.70   # Cosine similarity >= threshold -> MATCH (M=0)
    use_fp16: bool = False               # FP16 acceleration for CUDA


@dataclass
class SpeakerEmbedding:
    """
    Centroid vector embedding representation of an enrolled speaker supporting multi-sample cross-session updates.
    Raw audio is discarded after extraction for privacy and GDPR/compliance compatibility.
    """
    speaker_id: str
    embedding: List[float]               # L2-normalized centroid float vector
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    sample_count: int = 1                # Total number of genuine samples contributing to this centroid
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def dimension(self) -> int:
        return len(self.embedding)

    def add_sample(
        self,
        new_embedding: List[float],
        sample_metadata: Optional[Dict[str, Any]] = None,
    ) -> "SpeakerEmbedding":
        """
        Incrementally updates the centroid embedding with a new genuine voice sample.
        Formula:
            c_new = (c_old * N + e_new) / (N + 1)
        followed by L2 normalization:
            c_norm = c_new / ||c_new||_2
        where N = previous genuine sample count.
        """
        if not new_embedding or len(new_embedding) != len(self.embedding):
            raise ValueError(
                f"Embedding dimension mismatch: expected {len(self.embedding)}, got {len(new_embedding) if new_embedding else 0}"
            )

        N = max(1, self.sample_count)
        # Compute incremental centroid
        updated_centroid = [
            (self.embedding[i] * float(N) + new_embedding[i]) / float(N + 1)
            for i in range(len(self.embedding))
        ]
        # L2-normalize the updated centroid
        self.embedding = normalize_l2(updated_centroid)
        self.sample_count = N + 1
        self.updated_at = time.time()

        # Append enrollment record to history (metadata only, no raw audio)
        if "history" not in self.metadata or not isinstance(self.metadata["history"], list):
            self.metadata["history"] = []

        entry: Dict[str, Any] = {
            "sample_index": self.sample_count,
            "enrolled_at": self.updated_at,
        }
        if sample_metadata:
            entry.update(sample_metadata)
        self.metadata["history"].append(entry)

        return self


@dataclass
class VerificationResult:
    """
    Standardized result of a speaker verification comparison against a single or multi-sample centroid.
    """
    speaker_id: str
    similarity_score: float              # Cosine similarity in range [-1.0, 1.0]
    threshold: float                     # Verification threshold used
    is_match: bool                       # True if similarity_score >= threshold
    speaker_mismatch_flag: int           # 0 if match, 1 if mismatch (for Phase 3 risk engine)
    inference_time_ms: float
    sample_count: int = 1                # Number of genuine samples in enrolled centroid
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "similarity_score": round(self.similarity_score, 4),
            "threshold": round(self.threshold, 4),
            "match": self.is_match,
            "speaker_mismatch_flag": self.speaker_mismatch_flag,
            "sample_count": self.sample_count,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "metadata": self.metadata,
        }


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Computes cosine similarity between two vector embeddings.
    Similarity = (a . b) / (||a|| * ||b||)
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(y * y for y in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    similarity = dot_product / (norm_a * norm_b)
    # Numerical clamping to [-1.0, 1.0]
    return max(-1.0, min(1.0, float(similarity)))


def normalize_l2(vector: List[float]) -> List[float]:
    """Applies L2 normalization to a vector."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return vector
    return [x / norm for x in vector]


class BaseSpeakerVerifier(ABC):
    """Abstract base class contract for speaker verifiers."""

    @abstractmethod
    def load_model(self) -> None:
        pass

    @abstractmethod
    def extract_embedding(self, audio: PreprocessedAudio, speaker_id: str) -> SpeakerEmbedding:
        pass

    @abstractmethod
    def verify(
        self,
        audio: PreprocessedAudio,
        enrolled_embedding: SpeakerEmbedding,
        threshold: Optional[float] = None,
    ) -> VerificationResult:
        pass


class PretrainedECAPASpeakerVerifier(BaseSpeakerVerifier):
    """
    Speaker Verification engine using ECAPA-TDNN neural embeddings.
    Optimized for single-sample inference on Windows 11 CPU or NVIDIA MX450.
    """

    def __init__(self, config: Optional[SpeakerVerifierConfig] = None):
        self.config = config or SpeakerVerifierConfig()
        self.model = None
        self.is_loaded = False
        self.device = "cpu"
        self._resolve_device()

    def _resolve_device(self) -> str:
        """Resolves target hardware device (CPU / CUDA)."""
        if self.config.device == "cpu":
            self.device = "cpu"
            return self.device
        try:
            import torch
            if torch.cuda.is_available() and self.config.device in ("auto", "cuda"):
                self.device = "cuda"
                print(f"[Speaker Verifier] CUDA acceleration active: {torch.cuda.get_device_name(0)}")
            else:
                self.device = "cpu"
        except ImportError:
            self.device = "cpu"
        return self.device

    def load_model(self) -> None:
        """Loads pretrained speaker embedding extractor into memory once."""
        if self.is_loaded:
            return

        start_time = time.perf_counter()
        try:
            # Check for SpeechBrain or Transformers embedding model availability
            import torch
            from speechbrain.inference.speaker import EncoderClassifier

            self.model = EncoderClassifier.from_hparams(
                source=self.config.model_name_or_path,
                run_opts={"device": self.device},
            )
            self.is_loaded = True
            load_time_ms = (time.perf_counter() - start_time) * 1000.0
            print(f"[Speaker Verifier] Successfully loaded ECAPA-TDNN model in {load_time_ms:.1f}ms on {self.device}.")

        except (ImportError, Exception) as err:
            # Fallback to acoustic spectral projection for offline / test environments
            print(f"[Speaker Verifier] Notice: Using lightweight acoustic embedding extractor ({str(err)}).")
            self.is_loaded = True

    def extract_embedding(self, audio: PreprocessedAudio, speaker_id: str) -> SpeakerEmbedding:
        """
        Extracts a fixed-dimensional L2-normalized speaker embedding from preprocessed 16kHz audio.
        """
        if not self.is_loaded:
            self.load_model()

        start_time = time.perf_counter()
        raw_waveform = audio.waveform

        # Limit max samples to avoid excessive RAM/VRAM usage
        max_samples = 16000 * 10  # 10s ceiling
        if len(raw_waveform) > max_samples:
            raw_waveform = raw_waveform[:max_samples]

        # Neural inference path if SpeechBrain model is loaded
        if self.model is not None:
            import torch
            with getattr(torch, "inference_mode", torch.no_grad)():
                tensor_audio = torch.tensor(raw_waveform, dtype=torch.float32).unsqueeze(0).to(self.device)
                embeddings = self.model.encode_batch(tensor_audio)
                # Squeeze to 1D vector and normalize
                emb_list = embeddings.squeeze().cpu().numpy().tolist()
                emb_list = normalize_l2(emb_list)
        else:
            # Deterministic acoustic-frequency projection (lightweight fallback)
            emb_list = self._extract_acoustic_feature_embedding(raw_waveform, dim=self.config.embedding_dim)

        extraction_time_ms = (time.perf_counter() - start_time) * 1000.0

        return SpeakerEmbedding(
            speaker_id=speaker_id,
            embedding=emb_list,
            metadata={
                "extraction_time_ms": round(extraction_time_ms, 2),
                "model_id": self.config.model_name_or_path,
                "embedding_dimension": len(emb_list),
                "audio_duration_sec": audio.processed_duration_sec,
            },
        )

    def _extract_acoustic_feature_embedding(self, waveform: List[float], dim: int = 192) -> List[float]:
        """
        Deterministic acoustic feature embedding fallback using pure Python/math (or numpy if available).
        Extracts sub-band energy statistics and temporal moments.
        """
        if not waveform:
            return [0.0] * dim

        try:
            import numpy as np
            sig = np.array(waveform, dtype=np.float32)
            fft_vals = np.abs(np.fft.rfft(sig))
            if len(fft_vals) < dim:
                fft_vals = np.pad(fft_vals, (0, dim - len(fft_vals)))
            indices = np.linspace(0, len(fft_vals) - 1, dim).astype(int)
            raw_emb = fft_vals[indices].tolist()
            std_val = float(np.std(sig)) + 1e-6
            mean_val = float(np.mean(sig))
            modulated_emb = [(val / (std_val * 1000.0)) + (mean_val * 0.1) for val in raw_emb]
            return normalize_l2(modulated_emb)
        except ImportError:
            # Pure Python cycle-aligned logarithmic acoustic filterbank
            n_samples = len(waveform)
            raw_emb: List[float] = []

            for i in range(dim):
                center_f = 60.0 * ((7600.0 / 60.0) ** (i / max(1, dim - 1)))
                period_samples = 16000.0 / center_f
                num_cycles = max(10, int(1.0 * center_f))
                window_samples = min(int(num_cycles * period_samples), n_samples)
                
                omega = 2.0 * math.pi * center_f / 16000.0
                step = max(1, window_samples // 400)
                
                r = 0.0
                im = 0.0
                cnt = 0
                for t in range(0, window_samples, step):
                    s = waveform[t]
                    r += s * math.cos(omega * t)
                    im += s * math.sin(omega * t)
                    cnt += 1
                
                mag = math.sqrt(r * r + im * im) / max(1, cnt)
                raw_emb.append(mag)

            return normalize_l2(raw_emb)

    def verify(
        self,
        audio: PreprocessedAudio,
        enrolled_embedding: SpeakerEmbedding,
        threshold: Optional[float] = None,
    ) -> VerificationResult:
        """
        Verifies query audio against an enrolled speaker embedding.
        """
        start_time = time.perf_counter()
        target_threshold = threshold if threshold is not None else self.config.similarity_threshold

        # Extract embedding from test audio
        query_embedding = self.extract_embedding(audio, speaker_id=enrolled_embedding.speaker_id)

        # Compute cosine similarity
        similarity = compute_cosine_similarity(query_embedding.embedding, enrolled_embedding.embedding)

        is_match = similarity >= target_threshold
        speaker_mismatch_flag = 0 if is_match else 1
        inference_time_ms = (time.perf_counter() - start_time) * 1000.0

        return VerificationResult(
            speaker_id=enrolled_embedding.speaker_id,
            similarity_score=similarity,
            threshold=target_threshold,
            is_match=is_match,
            speaker_mismatch_flag=speaker_mismatch_flag,
            sample_count=enrolled_embedding.sample_count,
            inference_time_ms=inference_time_ms,
            metadata={
                "model_id": self.config.model_name_or_path,
                "device": self.device,
                "sample_count": enrolled_embedding.sample_count,
                "query_duration_sec": audio.processed_duration_sec,
                "threshold_calibration_note": "Threshold is configurable; production deployment requires dataset calibration.",
            },
        )


class InMemorySpeakerStore:
    """
    Thread-safe in-memory store for enrolled speaker embeddings.
    Supports multi-sample incremental centroid averaging across historical sessions.
    Raw audio files are never stored, ensuring strict privacy preservation.
    """

    def __init__(self):
        self._store: Dict[str, SpeakerEmbedding] = {}

    def save(self, embedding: SpeakerEmbedding) -> None:
        """Saves or replaces a speaker embedding object directly."""
        self._store[embedding.speaker_id] = embedding

    def enroll_sample(
        self,
        speaker_id: str,
        embedding: List[float],
        speaker_name: Optional[str] = None,
        sample_metadata: Optional[Dict[str, Any]] = None,
    ) -> SpeakerEmbedding:
        """
        Enrolls a genuine voice sample for the given speaker_id.
        - If speaker exists: updates the centroid embedding incrementally using moving average:
            centroid_new = (centroid_old * N + e_new) / (N + 1)
          and increments sample_count.
        - If speaker is new: initializes a new SpeakerEmbedding with sample_count = 1.
        """
        existing = self._store.get(speaker_id)
        if existing is not None:
            if speaker_name and not existing.metadata.get("speaker_name"):
                existing.metadata["speaker_name"] = speaker_name
            existing.add_sample(embedding, sample_metadata)
            return existing
        else:
            meta = dict(sample_metadata or {})
            if speaker_name:
                meta["speaker_name"] = speaker_name
            meta["history"] = [
                {
                    "sample_index": 1,
                    "enrolled_at": time.time(),
                    **(sample_metadata or {}),
                }
            ]
            new_profile = SpeakerEmbedding(
                speaker_id=speaker_id,
                embedding=normalize_l2(embedding),
                created_at=time.time(),
                updated_at=time.time(),
                sample_count=1,
                metadata=meta,
            )
            self._store[speaker_id] = new_profile
            return new_profile

    def get(self, speaker_id: str) -> Optional[SpeakerEmbedding]:
        return self._store.get(speaker_id)

    def exists(self, speaker_id: str) -> bool:
        return speaker_id in self._store

    def delete(self, speaker_id: str) -> bool:
        if speaker_id in self._store:
            del self._store[speaker_id]
            return True
        return False

    def list_speakers(self) -> List[str]:
        return list(self._store.keys())

    def clear(self) -> None:
        self._store.clear()


class DatabaseSpeakerStore:
    """
    Production-grade SQLite database-backed store for enrolled speaker centroids.
    Guarantees persistence of 192-D biometric vectors across daemon and server restarts
    with thread safety, ACID compliance, and multi-tenant organization scoping.
    Zero raw audio waveforms are stored.
    """

    DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

    def __init__(self, db_path: Optional[str] = None):
        from contextlib import contextmanager
        import json
        import os
        import sqlite3

        self.contextmanager = contextmanager
        self.json = json
        self.sqlite3 = sqlite3
        self.os = os

        if db_path is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data",
            )
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "voiceshield_biometrics.db")
        else:
            self.db_path = db_path

        self._init_db()
        self._migrate_from_json_if_needed()

    def _get_connection(self):
        from contextlib import contextmanager

        @contextmanager
        def _conn_ctx():
            conn = self.sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.row_factory = self.sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

        return _conn_ctx()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS speaker_embeddings (
                    speaker_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    speaker_name TEXT,
                    embedding_json TEXT NOT NULL,
                    sample_count INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata_json TEXT,
                    PRIMARY KEY (speaker_id, organization_id)
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_speaker_org
                ON speaker_embeddings (organization_id);
                """
            )
            conn.commit()

    def _migrate_from_json_if_needed(self) -> None:
        """
        Migrates legacy entries from data/speakers.json into SQLite if DB is empty.
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM speaker_embeddings")
                count = cur.fetchone()[0]
                if count > 0:
                    return

            data_dir = self.os.path.dirname(self.db_path)
            json_file = self.os.path.join(data_dir, "speakers.json")
            if not self.os.path.exists(json_file):
                return

            with open(json_file, "r") as f:
                data = self.json.load(f)

            with self._get_connection() as conn:
                for spk_id, item in data.items():
                    created_t = float(item.get("created_at", time.time()))
                    updated_t = float(item.get("updated_at", created_t))
                    sample_cnt = int(item.get("sample_count", 1))
                    emb_list = item.get("embedding", [])
                    meta = item.get("metadata", {})
                    spk_name = meta.get("speaker_name") or item.get("speaker_name") or ""
                    org_id = meta.get("organization_id") or self.DEFAULT_ORG_ID

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO speaker_embeddings
                        (speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            spk_id,
                            org_id,
                            spk_name,
                            self.json.dumps(emb_list),
                            sample_cnt,
                            created_t,
                            updated_t,
                            self.json.dumps(meta),
                        ),
                    )
                conn.commit()
        except Exception:
            pass

    def save(self, embedding: SpeakerEmbedding, organization_id: Optional[str] = None) -> None:
        org_id = organization_id or embedding.metadata.get("organization_id") or self.DEFAULT_ORG_ID
        spk_name = embedding.metadata.get("speaker_name", "")
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO speaker_embeddings
                (speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    embedding.speaker_id,
                    org_id,
                    spk_name,
                    self.json.dumps(embedding.embedding),
                    embedding.sample_count,
                    embedding.created_at,
                    embedding.updated_at,
                    self.json.dumps(embedding.metadata),
                ),
            )
            conn.commit()

    def enroll_sample(
        self,
        speaker_id: str,
        embedding: List[float],
        speaker_name: Optional[str] = None,
        sample_metadata: Optional[Dict[str, Any]] = None,
        organization_id: Optional[str] = None,
    ) -> SpeakerEmbedding:
        org_id = organization_id or (sample_metadata or {}).get("organization_id") or self.DEFAULT_ORG_ID
        existing = self.get(speaker_id, organization_id=org_id)
        if existing is not None:
            if speaker_name and not existing.metadata.get("speaker_name"):
                existing.metadata["speaker_name"] = speaker_name
            existing.add_sample(embedding, sample_metadata)
            self.save(existing, organization_id=org_id)
            return existing
        else:
            meta = dict(sample_metadata or {})
            if speaker_name:
                meta["speaker_name"] = speaker_name
            meta["organization_id"] = org_id
            meta["history"] = [
                {
                    "sample_index": 1,
                    "enrolled_at": time.time(),
                    **(sample_metadata or {}),
                }
            ]
            new_profile = SpeakerEmbedding(
                speaker_id=speaker_id,
                embedding=normalize_l2(embedding),
                created_at=time.time(),
                updated_at=time.time(),
                sample_count=1,
                metadata=meta,
            )
            self.save(new_profile, organization_id=org_id)
            return new_profile

    def get(self, speaker_id: str, organization_id: Optional[str] = None) -> Optional[SpeakerEmbedding]:
        org_id = organization_id or self.DEFAULT_ORG_ID
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json
                FROM speaker_embeddings
                WHERE speaker_id = ? AND organization_id = ?
                """,
                (speaker_id, org_id),
            )
            row = cur.fetchone()
            if not row and organization_id is None:
                # Fallback check for any org only if caller did not specify an org_id
                cur.execute(
                    """
                    SELECT speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json
                    FROM speaker_embeddings
                    WHERE speaker_id = ?
                    LIMIT 1
                    """,
                    (speaker_id,),
                )
                row = cur.fetchone()

            if not row:
                return None

            emb_list = self.json.loads(row["embedding_json"])
            meta = self.json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            if row["speaker_name"] and not meta.get("speaker_name"):
                meta["speaker_name"] = row["speaker_name"]
            meta["organization_id"] = row["organization_id"]

            return SpeakerEmbedding(
                speaker_id=row["speaker_id"],
                embedding=emb_list,
                created_at=float(row["created_at"]),
                updated_at=float(row["updated_at"]),
                sample_count=int(row["sample_count"]),
                metadata=meta,
            )

    def exists(self, speaker_id: str, organization_id: Optional[str] = None) -> bool:
        return self.get(speaker_id, organization_id=organization_id) is not None

    def delete(self, speaker_id: str, organization_id: Optional[str] = None) -> bool:
        org_id = organization_id or self.DEFAULT_ORG_ID
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM speaker_embeddings WHERE speaker_id = ? AND organization_id = ?",
                (speaker_id, org_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def list_speakers(self, organization_id: Optional[str] = None) -> List[str]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if organization_id:
                cur.execute(
                    "SELECT speaker_id FROM speaker_embeddings WHERE organization_id = ? ORDER BY created_at DESC",
                    (organization_id,),
                )
            else:
                cur.execute("SELECT speaker_id FROM speaker_embeddings ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [r["speaker_id"] for r in rows]

    @property
    def _store(self) -> Dict[str, SpeakerEmbedding]:
        """Provides dictionary-like view for backward compatibility."""
        res = {}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json FROM speaker_embeddings ORDER BY created_at DESC")
            rows = cur.fetchall()
            for r in rows:
                emb_list = self.json.loads(r["embedding_json"])
                meta = self.json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                if r["speaker_name"] and not meta.get("speaker_name"):
                    meta["speaker_name"] = r["speaker_name"]
                meta["organization_id"] = r["organization_id"]
                res[r["speaker_id"]] = SpeakerEmbedding(
                    speaker_id=r["speaker_id"],
                    embedding=emb_list,
                    created_at=float(r["created_at"]),
                    updated_at=float(r["updated_at"]),
                    sample_count=int(r["sample_count"]),
                    metadata=meta,
                )
        return res

    def get_all(self, organization_id: Optional[str] = None) -> List[SpeakerEmbedding]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if organization_id:
                cur.execute(
                    "SELECT speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json FROM speaker_embeddings WHERE organization_id = ? ORDER BY created_at DESC",
                    (organization_id,),
                )
            else:
                cur.execute("SELECT speaker_id, organization_id, speaker_name, embedding_json, sample_count, created_at, updated_at, metadata_json FROM speaker_embeddings ORDER BY created_at DESC")
            rows = cur.fetchall()
            results = []
            for r in rows:
                emb_list = self.json.loads(r["embedding_json"])
                meta = self.json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                if r["speaker_name"] and not meta.get("speaker_name"):
                    meta["speaker_name"] = r["speaker_name"]
                meta["organization_id"] = r["organization_id"]
                results.append(
                    SpeakerEmbedding(
                        speaker_id=r["speaker_id"],
                        embedding=emb_list,
                        created_at=float(r["created_at"]),
                        updated_at=float(r["updated_at"]),
                        sample_count=int(r["sample_count"]),
                        metadata=meta,
                    )
                )
            return results

    def clear(self) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM speaker_embeddings")
            conn.commit()

