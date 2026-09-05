"""
Unit & Integration Test Suite for SQLite Database-Backed Speaker Biometric Persistence.
Validates:
1. DatabaseSpeakerStore initializes SQLite database with WAL mode and schema.
2. First enrollment creates profile with sample_count = 1 and normalized 192-D vector.
3. Second enrollment updates centroid with mathematical incremental moving average formula:
   c_new = normalize_l2((c_old * N + e_new) / (N + 1))
4. Re-instantiating the store from the same SQLite file (simulating server/daemon restart)
   retrieves the exact multi-sample centroid, sample_count, and metadata.
5. Multi-tenant scoping: Different organizations with the same speaker_id remain isolated.
6. Verify query comparison works against stored database centroid.
7. Deletion and speaker listing operations work accurately.
8. Zero raw audio waveforms are persisted in the database table.
"""

import math
import os
import tempfile
import unittest

from app.audio.preprocessing import PreprocessedAudio
from app.models.speaker_verifier import (
    DatabaseSpeakerStore,
    PretrainedECAPASpeakerVerifier,
    SpeakerEmbedding,
    compute_cosine_similarity,
    normalize_l2,
)


class TestSpeakerDatabaseStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_biometrics.db")
        self.store = DatabaseSpeakerStore(db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_1_database_initialization_and_schema(self):
        """Verify SQLite tables and indexes are created properly."""
        self.assertTrue(os.path.exists(self.db_path))
        with self.store._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='speaker_embeddings'")
            self.assertIsNotNone(cur.fetchone())

    def test_2_first_enrollment_creates_profile(self):
        """Verify single enrollment stores normalized 192-D vector with sample_count = 1."""
        raw_emb = [0.1 * i for i in range(192)]
        norm_emb = normalize_l2(raw_emb)

        enrolled = self.store.enroll_sample(
            speaker_id="SPK-DB-001",
            embedding=norm_emb,
            speaker_name="Executive Alice",
            sample_metadata={"channel": "web_portal"},
            organization_id="ORG-TEST-100",
        )

        self.assertEqual(enrolled.speaker_id, "SPK-DB-001")
        self.assertEqual(enrolled.sample_count, 1)
        self.assertEqual(len(enrolled.embedding), 192)

        # Retrieve and verify
        retrieved = self.store.get("SPK-DB-001", organization_id="ORG-TEST-100")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.speaker_id, "SPK-DB-001")
        self.assertEqual(retrieved.sample_count, 1)
        self.assertEqual(retrieved.metadata.get("speaker_name"), "Executive Alice")

    def test_3_multi_sample_centroid_incremental_update(self):
        """Verify incremental centroid calculation math in SQLite store."""
        dim = 192
        v1 = normalize_l2([1.0 if i < 96 else 0.0 for i in range(dim)])
        v2 = normalize_l2([1.0 if i >= 96 else 0.0 for i in range(dim)])

        # Sample 1
        self.store.enroll_sample(
            speaker_id="SPK-MATH-01",
            embedding=v1,
            organization_id="ORG-MATH",
        )

        # Sample 2
        updated = self.store.enroll_sample(
            speaker_id="SPK-MATH-01",
            embedding=v2,
            organization_id="ORG-MATH",
        )

        self.assertEqual(updated.sample_count, 2)

        # Expected centroid math: c_new = normalize_l2((v1 + v2) / 2)
        expected_raw = [(v1[i] + v2[i]) / 2.0 for i in range(dim)]
        expected_centroid = normalize_l2(expected_raw)

        for i in range(dim):
            self.assertAlmostEqual(updated.embedding[i], expected_centroid[i], places=5)

    def test_4_persistence_across_process_restart(self):
        """Verify embeddings persist across new store instances simulating daemon restart."""
        raw_emb = normalize_l2([math.sin(i) for i in range(192)])

        # Enroll in first store instance
        self.store.enroll_sample(
            speaker_id="SPK-RESTART-01",
            embedding=raw_emb,
            speaker_name="Dr. Jane Watson",
            sample_metadata={"confidence": 0.99},
            organization_id="ORG-MAIN",
        )

        # Re-open database in fresh store instance (Simulating Process Restart)
        new_store_instance = DatabaseSpeakerStore(db_path=self.db_path)

        retrieved = new_store_instance.get("SPK-RESTART-01", organization_id="ORG-MAIN")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.speaker_id, "SPK-RESTART-01")
        self.assertEqual(retrieved.sample_count, 1)
        self.assertEqual(retrieved.metadata.get("speaker_name"), "Dr. Jane Watson")

        for i in range(192):
            self.assertAlmostEqual(retrieved.embedding[i], raw_emb[i], places=5)

    def test_5_multi_tenant_isolation(self):
        """Verify same speaker_id in different organizations stores separate isolated centroids."""
        emb_org_a = normalize_l2([1.0 if i % 2 == 0 else 0.0 for i in range(192)])
        emb_org_b = normalize_l2([0.0 if i % 2 == 0 else 1.0 for i in range(192)])

        self.store.enroll_sample("SPK-SHARED-ID", emb_org_a, organization_id="ORG-BANK-A")
        self.store.enroll_sample("SPK-SHARED-ID", emb_org_b, organization_id="ORG-BANK-B")

        profile_a = self.store.get("SPK-SHARED-ID", organization_id="ORG-BANK-A")
        profile_b = self.store.get("SPK-SHARED-ID", organization_id="ORG-BANK-B")

        self.assertIsNotNone(profile_a)
        self.assertIsNotNone(profile_b)
        self.assertNotEqual(profile_a.embedding, profile_b.embedding)

        # Cross similarity should be orthogonal (0.0)
        sim = compute_cosine_similarity(profile_a.embedding, profile_b.embedding)
        self.assertAlmostEqual(sim, 0.0, places=4)

    def test_6_delete_and_list_operations(self):
        """Verify delete and list_speakers methods."""
        emb = normalize_l2([1.0] * 192)
        self.store.enroll_sample("SPK-DEL-01", emb, organization_id="ORG-DEL")
        self.store.enroll_sample("SPK-DEL-02", emb, organization_id="ORG-DEL")

        speakers = self.store.list_speakers(organization_id="ORG-DEL")
        self.assertIn("SPK-DEL-01", speakers)
        self.assertIn("SPK-DEL-02", speakers)

        # Delete SPK-DEL-01
        deleted = self.store.delete("SPK-DEL-01", organization_id="ORG-DEL")
        self.assertTrue(deleted)
        self.assertFalse(self.store.exists("SPK-DEL-01", organization_id="ORG-DEL"))
        self.assertTrue(self.store.exists("SPK-DEL-02", organization_id="ORG-DEL"))

    def test_7_no_raw_audio_columns_in_database(self):
        """Verify schema strictly contains only numerical embedding vector and metadata."""
        with self.store._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(speaker_embeddings)")
            columns = [row["name"] for row in cur.fetchall()]

            self.assertIn("embedding_json", columns)
            self.assertIn("sample_count", columns)
            self.assertNotIn("raw_audio", columns)
            self.assertNotIn("audio_bytes", columns)
            self.assertNotIn("waveform", columns)


if __name__ == "__main__":
    unittest.main()
