-- ============================================================================
-- VoiceShield Enterprise Database Schema Migration (Phase 1 Fully Hardened)
-- Problem Statement: SIH 26104 (AI Voice Cloning & Telephony Fraud Mitigation)
-- Migration: migrations/001_sih26104_schema.sql
-- Architecture: Non-destructive, Idempotent, Strict Sequential Backfill, Granular RLS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. EXTENSIONS & SECURITY INITIALIZATION
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA extensions;

-- Function: update_updated_at_column (Secured search_path)
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- 1. ORGANIZATIONS (Multi-Tenant Root)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    organization_type VARCHAR(64) NOT NULL DEFAULT 'ENTERPRISE', -- 'BANK', 'FINTECH', 'TELECOM', 'ENTERPRISE', 'GOVERNMENT'
    slug VARCHAR(128) UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed default compatibility root organization
INSERT INTO public.organizations (id, name, organization_type, slug, is_active)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Organization (Legacy Dev)', 'ENTERPRISE', 'default-legacy-org', TRUE)
ON CONFLICT (id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. ORGANIZATION MEMBERS (Role-Based Access Control)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    auth_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(32) NOT NULL DEFAULT 'ANALYST', -- 'ORG_ADMIN', 'SECURITY_OFFICER', 'ANALYST', 'AUDITOR'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(organization_id, email)
);

-- ----------------------------------------------------------------------------
-- 3. CONTACTS (Ensure Base Table + Sequential Column Alter & Backfill)
-- ----------------------------------------------------------------------------
-- Ensure base table exists if fresh database
CREATE TABLE IF NOT EXISTS public.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step 3.1: Add organization_id first (nullable with default)
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS organization_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

-- Step 3.2: Backfill organization_id for all existing rows
UPDATE public.contacts 
SET organization_id = '00000000-0000-0000-0000-000000000001' 
WHERE organization_id IS NULL;

-- Step 3.3: Add and backfill phone columns (Hashing & Masking)
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS phone_number VARCHAR(32);
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS phone_hash VARCHAR(64);
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS phone_masked VARCHAR(32);

-- Backfill phone_hash using pgcrypto digest (SHA-256)
UPDATE public.contacts
SET phone_hash = encode(digest(COALESCE(phone_number, id::text), 'sha256'), 'hex')
WHERE phone_hash IS NULL;

-- Backfill phone_masked safely
UPDATE public.contacts
SET phone_masked = CASE 
    WHEN phone_number IS NOT NULL AND length(phone_number) > 4 THEN 
        substring(phone_number from 1 for 3) || '******' || substring(phone_number from length(phone_number)-3 for 4)
    WHEN phone_number IS NOT NULL THEN 
        phone_number
    ELSE 
        'UNKNOWN'
END
WHERE phone_masked IS NULL;

-- Step 3.4: Add and backfill identity & directory columns
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS claimed_role VARCHAR(128);
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS department VARCHAR(128);
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS risk_tier VARCHAR(32) DEFAULT 'STANDARD';
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS is_flagged BOOLEAN DEFAULT FALSE;
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS flag_reason TEXT;
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS historical_call_count INT DEFAULT 0;
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS last_call_at TIMESTAMPTZ;
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- Backfill full_name from existing 'name' column if present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'contacts' AND column_name = 'name'
    ) THEN
        EXECUTE 'UPDATE public.contacts SET full_name = name WHERE full_name IS NULL AND name IS NOT NULL;';
    END IF;
END $$;

-- Backfill claimed_role from existing 'role' column if present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'contacts' AND column_name = 'role'
    ) THEN
        EXECUTE 'UPDATE public.contacts SET claimed_role = role WHERE claimed_role IS NULL AND role IS NOT NULL;';
    END IF;
END $$;

-- Backfill is_flagged from existing 'is_previously_flagged' column if present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'contacts' AND column_name = 'is_previously_flagged'
    ) THEN
        EXECUTE 'UPDATE public.contacts SET is_flagged = is_previously_flagged WHERE is_previously_flagged IS NOT NULL;';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 4. SPEAKERS (Ensure Base Table + Sequential Column Alter & Backfill)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.speakers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    speaker_id VARCHAR(128) NOT NULL UNIQUE,
    speaker_name VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step 4.1: Add organization_id first and backfill
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS organization_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';
UPDATE public.speakers SET organization_id = '00000000-0000-0000-0000-000000000001' WHERE organization_id IS NULL;

-- Step 4.2: Add additional metadata columns
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES public.contacts(id) ON DELETE SET NULL;
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS department VARCHAR(128);
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS role VARCHAR(128);
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS verification_threshold NUMERIC(4, 3) NOT NULL DEFAULT 0.650;
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS voice_sample_hash VARCHAR(64);
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS enrollment_duration_sec NUMERIC(6, 2);
ALTER TABLE public.speakers ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- ----------------------------------------------------------------------------
-- 5. SPEAKER BIOMETRIC EMBEDDINGS (ECAPA-TDNN 192-dim Vector)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.speaker_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    speaker_ref_id UUID NOT NULL REFERENCES public.speakers(id) ON DELETE CASCADE,
    speaker_id VARCHAR(128) NOT NULL,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
    model_version VARCHAR(64) NOT NULL DEFAULT 'speechbrain/spkrec-ecapa-voxceleb',
    embedding_dimension INT NOT NULL DEFAULT 192,
    embedding_vec extensions.vector(192),
    embedding_fallback FLOAT8[],
    sample_rate INT NOT NULL DEFAULT 16000,
    audio_snr_db NUMERIC(6, 2),
    rms_energy_db NUMERIC(6, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(speaker_ref_id, model_version)
);

-- ----------------------------------------------------------------------------
-- 6. CALLS (Ensure Base Table + Sequential Column Alter & Backfill)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id VARCHAR(64) NOT NULL UNIQUE,
    speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    contact_id UUID REFERENCES public.contacts(id) ON DELETE SET NULL,
    caller_id VARCHAR(64),
    claimed_role VARCHAR(128),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    duration_seconds NUMERIC(8, 2)
);

-- Step 6.1: Add organization_id first and backfill
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS organization_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';
UPDATE public.calls SET organization_id = '00000000-0000-0000-0000-000000000001' WHERE organization_id IS NULL;

-- Step 6.2: Add additional session metadata columns
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS session_type VARCHAR(32) NOT NULL DEFAULT 'REST_BATCH';
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) NOT NULL DEFAULT 'FILE_UPLOAD';
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS client_session_id VARCHAR(128);
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED';
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS final_risk_score INT;
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS final_risk_level VARCHAR(16);
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- ----------------------------------------------------------------------------
-- 7. RISK EVENTS (Ensure Base Table + Sequential Column Alter & Backfill)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.risk_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID REFERENCES public.calls(id) ON DELETE CASCADE,
    risk_score INT NOT NULL,
    risk_level VARCHAR(16) NOT NULL,
    recommended_action VARCHAR(32) NOT NULL,
    deepfake_prediction VARCHAR(16) NOT NULL,
    fake_probability NUMERIC(6, 4) NOT NULL,
    speaker_similarity NUMERIC(6, 4),
    speaker_match BOOLEAN,
    speaker_verification_status VARCHAR(64),
    speaker_mismatch_flag INT NOT NULL DEFAULT 0,
    acoustic_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    caller_recognized BOOLEAN NOT NULL DEFAULT FALSE,
    previously_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    transaction_amount NUMERIC(14, 2),
    normal_transaction_amount NUMERIC(14, 2),
    is_urgent BOOLEAN NOT NULL DEFAULT FALSE,
    urgency_reason TEXT,
    model_id VARCHAR(128),
    inference_time_ms NUMERIC(8, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step 7.1: Add organization_id first
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS organization_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';

-- Step 7.2: Backfill organization_id through related calls
UPDATE public.risk_events re
SET organization_id = c.organization_id
FROM public.calls c
WHERE re.call_id = c.id
  AND c.organization_id IS NOT NULL;

-- Step 7.3: Fallback backfill for any unlinked risk event rows
UPDATE public.risk_events
SET organization_id = '00000000-0000-0000-0000-000000000001'
WHERE organization_id IS NULL;

-- Step 7.4: Add additional signal, prosody, and latency columns
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS window_index INT DEFAULT 0;
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS prosody_anomaly_score NUMERIC(6, 4) DEFAULT 0.0;
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS prosody_reasons TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS prosody_features JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS flags TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS estimated_snr_db NUMERIC(6, 2);
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS rms_energy_db NUMERIC(6, 2);
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS model_type VARCHAR(64) DEFAULT 'Wav2Vec2';
ALTER TABLE public.risk_events ADD COLUMN IF NOT EXISTS pipeline_latency_ms NUMERIC(8, 2);

-- ----------------------------------------------------------------------------
-- 8. STREAM WINDOWS (Granular Live WebSocket Audio Slices)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.stream_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL REFERENCES public.calls(id) ON DELETE CASCADE,
    session_id VARCHAR(128) NOT NULL,
    window_index INT NOT NULL,
    window_duration_sec NUMERIC(4, 2) NOT NULL DEFAULT 1.50,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    vad_status VARCHAR(32) NOT NULL DEFAULT 'SPEECH_DETECTED',
    deepfake_prediction VARCHAR(16) NOT NULL,
    fake_probability NUMERIC(6, 4) NOT NULL,
    real_probability NUMERIC(6, 4) NOT NULL,
    acoustic_anomaly NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    speaker_similarity NUMERIC(6, 4),
    is_speaker_match BOOLEAN,
    speaker_mismatch_flag INT NOT NULL DEFAULT 0,
    risk_score INT NOT NULL,
    risk_level VARCHAR(16) NOT NULL,
    recommended_action VARCHAR(32) NOT NULL,
    flags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    prosody_reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    prosody_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    server_latency_ms NUMERIC(8, 2) NOT NULL,
    estimated_snr_db NUMERIC(6, 2),
    rms_db NUMERIC(6, 2),
    UNIQUE(call_id, window_index)
);

-- ----------------------------------------------------------------------------
-- 9. TRANSACTIONS (Financial Authorization Context)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
    call_id UUID REFERENCES public.calls(id) ON DELETE SET NULL,
    contact_id UUID REFERENCES public.contacts(id) ON DELETE SET NULL,
    speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    transaction_reference VARCHAR(128) UNIQUE,
    amount NUMERIC(16, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
    normal_historical_amount NUMERIC(16, 2),
    transaction_type VARCHAR(64) NOT NULL DEFAULT 'WIRE_TRANSFER',
    is_urgent BOOLEAN NOT NULL DEFAULT FALSE,
    urgency_reason TEXT,
    beneficiary_account_masked VARCHAR(64),
    beneficiary_name VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING_VERIFICATION',
    risk_score_at_request INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Secure Analyst View for Transactions (Sanitized PII)
CREATE OR REPLACE VIEW public.transactions_analyst_view
WITH (security_invoker = true)
AS
SELECT
    t.id,
    t.organization_id,
    t.call_id,
    t.contact_id,
    t.amount,
    t.currency,
    t.transaction_type,
    t.is_urgent,
    t.urgency_reason,
    t.beneficiary_account_masked,
    t.status,
    t.risk_score_at_request,
    t.created_at
FROM public.transactions t;

-- ----------------------------------------------------------------------------
-- 10. FRAUD INDICATORS (Threat Intelligence & Historical Signatures)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.fraud_indicators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
    indicator_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'HIGH',
    source VARCHAR(64) NOT NULL DEFAULT 'VOICESHIELD_CORE',
    related_contact_id UUID REFERENCES public.contacts(id) ON DELETE SET NULL,
    related_speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    related_call_id UUID REFERENCES public.calls(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    raw_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES public.organization_members(id) ON DELETE SET NULL,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 11. ALERTS (Security Operations Incident Dispatch)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
    call_id UUID REFERENCES public.calls(id) ON DELETE CASCADE,
    risk_event_id UUID REFERENCES public.risk_events(id) ON DELETE SET NULL,
    alert_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    recipient_role VARCHAR(64) DEFAULT 'SECURITY_OFFICER',
    channel VARCHAR(32) NOT NULL DEFAULT 'IN_APP_DASHBOARD',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES public.organization_members(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- ----------------------------------------------------------------------------
-- 12. VERIFICATION EVENTS (Step-Up MFA & Out-of-Band Callbacks)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.verification_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
    call_id UUID REFERENCES public.calls(id) ON DELETE CASCADE,
    transaction_id UUID REFERENCES public.transactions(id) ON DELETE SET NULL,
    verification_type VARCHAR(64) NOT NULL,
    target_phone_masked VARCHAR(32),
    initiated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM_AUTOMATION',
    result VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    challenge_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    actor_id UUID REFERENCES public.organization_members(id) ON DELETE SET NULL,
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 13. ORGANIZATION POLICIES (Configurable Risk & Escalation Matrices)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.organization_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE UNIQUE,
    fake_prob_critical_threshold NUMERIC(4, 2) NOT NULL DEFAULT 0.85,
    fake_prob_warn_threshold NUMERIC(4, 2) NOT NULL DEFAULT 0.50,
    speaker_verification_strictness NUMERIC(4, 2) NOT NULL DEFAULT 0.65,
    acoustic_anomaly_sensitivity NUMERIC(4, 2) NOT NULL DEFAULT 0.70,
    transaction_auto_hold_amount NUMERIC(16, 2) NOT NULL DEFAULT 500000.00,
    step_up_verification_required BOOLEAN NOT NULL DEFAULT TRUE,
    auto_block_on_critical_deepfake BOOLEAN NOT NULL DEFAULT TRUE,
    stream_window_retention_days INT NOT NULL DEFAULT 14,
    notification_webhook_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 14. AUDIT LOGS (Immutable Compliance & Forensic Audit Trail)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
    actor_id UUID REFERENCES public.organization_members(id) ON DELETE SET NULL,
    actor_email VARCHAR(255) DEFAULT 'system@voiceshield.local',
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    ip_address INET,
    user_agent TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 15. PERFORMANCE INDEXES (All Columns Guaranteed to Exist)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_speakers_org ON public.speakers(organization_id);
CREATE INDEX IF NOT EXISTS idx_speakers_spk_id ON public.speakers(speaker_id);
CREATE INDEX IF NOT EXISTS idx_contacts_org_phone_hash ON public.contacts(organization_id, phone_hash);

CREATE INDEX IF NOT EXISTS idx_calls_call_id ON public.calls(call_id);
CREATE INDEX IF NOT EXISTS idx_calls_org_started ON public.calls(organization_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_calls_status ON public.calls(status);

CREATE INDEX IF NOT EXISTS idx_risk_events_org ON public.risk_events(organization_id);
CREATE INDEX IF NOT EXISTS idx_risk_events_call ON public.risk_events(call_id);
CREATE INDEX IF NOT EXISTS idx_risk_events_created ON public.risk_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_level ON public.risk_events(risk_level);

CREATE INDEX IF NOT EXISTS idx_stream_windows_call_win ON public.stream_windows(call_id, window_index);
CREATE INDEX IF NOT EXISTS idx_stream_windows_timestamp ON public.stream_windows(timestamp);

CREATE INDEX IF NOT EXISTS idx_transactions_org_created ON public.transactions(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_call ON public.transactions(call_id);

CREATE INDEX IF NOT EXISTS idx_fraud_ind_org ON public.fraud_indicators(organization_id);
CREATE INDEX IF NOT EXISTS idx_alerts_org_status ON public.alerts(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created ON public.audit_logs(organization_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 16. ROW LEVEL SECURITY (RLS) & HELPER FUNCTIONS
-- ----------------------------------------------------------------------------
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.speakers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.speaker_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stream_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fraud_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verification_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- Helper: Resolves authenticated user's organization memberships
CREATE OR REPLACE FUNCTION public.get_auth_user_org_ids()
RETURNS TABLE(org_id UUID)
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN QUERY
    SELECT om.organization_id
    FROM public.organization_members om
    WHERE om.auth_user_id = auth.uid()
      AND om.is_active = TRUE;
END;
$$;

-- Helper: Checks ORG_ADMIN status
CREATE OR REPLACE FUNCTION public.is_org_admin(target_org_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM public.organization_members om
        WHERE om.auth_user_id = auth.uid()
          AND om.organization_id = target_org_id
          AND om.role = 'ORG_ADMIN'
          AND om.is_active = TRUE
    );
END;
$$;

-- ----------------------------------------------------------------------------
-- 17. GRANULAR RLS POLICIES
-- ----------------------------------------------------------------------------

-- A. Service Role Policies (Backend Express / Python Workers have full access)
DO $$
DECLARE
    t TEXT;
    table_list TEXT[] := ARRAY[
        'organizations', 'organization_members', 'contacts', 'speakers',
        'speaker_embeddings', 'calls', 'risk_events', 'stream_windows',
        'transactions', 'fraud_indicators', 'alerts', 'verification_events',
        'organization_policies', 'audit_logs'
    ];
BEGIN
    FOREACH t IN ARRAY table_list LOOP
        EXECUTE format('DROP POLICY IF EXISTS service_role_all_%I ON public.%I;', t, t);
        EXECUTE format(
            'CREATE POLICY service_role_all_%I ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true);',
            t, t
        );
    END LOOP;
END $$;

-- B. Biometric Embeddings (Restricted: Service Role Only, normal authenticated users CANNOT SELECT)
-- (No SELECT policies granted to 'authenticated' on speaker_embeddings)

-- C. Organizations & Members
DROP POLICY IF EXISTS org_member_select_org ON public.organizations;
CREATE POLICY org_member_select_org ON public.organizations FOR SELECT TO authenticated
USING (id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_member_select_members ON public.organization_members;
CREATE POLICY org_member_select_members ON public.organization_members FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_admin_manage_members ON public.organization_members;
CREATE POLICY org_admin_manage_members ON public.organization_members FOR ALL TO authenticated
USING (public.is_org_admin(organization_id))
WITH CHECK (public.is_org_admin(organization_id));

-- D. Contacts
DROP POLICY IF EXISTS org_member_select_contacts ON public.contacts;
CREATE POLICY org_member_select_contacts ON public.contacts FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_admin_manage_contacts ON public.contacts;
CREATE POLICY org_admin_manage_contacts ON public.contacts FOR ALL TO authenticated
USING (public.is_org_admin(organization_id))
WITH CHECK (public.is_org_admin(organization_id));

-- E. Speakers
DROP POLICY IF EXISTS org_member_select_speakers ON public.speakers;
CREATE POLICY org_member_select_speakers ON public.speakers FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_admin_manage_speakers ON public.speakers;
CREATE POLICY org_admin_manage_speakers ON public.speakers FOR ALL TO authenticated
USING (public.is_org_admin(organization_id))
WITH CHECK (public.is_org_admin(organization_id));

-- F. Calls & Session Telemetry
DROP POLICY IF EXISTS org_member_select_calls ON public.calls;
CREATE POLICY org_member_select_calls ON public.calls FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

-- G. Risk Events & Stream Windows
DROP POLICY IF EXISTS org_member_select_risk_events ON public.risk_events;
CREATE POLICY org_member_select_risk_events ON public.risk_events FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_member_select_stream_windows ON public.stream_windows;
CREATE POLICY org_member_select_stream_windows ON public.stream_windows FOR SELECT TO authenticated
USING (call_id IN (SELECT c.id FROM public.calls c WHERE c.organization_id IN (SELECT public.get_auth_user_org_ids())));

-- H. Transactions (Direct SELECT restricted to ORG_ADMIN; Analysts use public.transactions_analyst_view)
DROP POLICY IF EXISTS org_admin_select_transactions ON public.transactions;
CREATE POLICY org_admin_select_transactions ON public.transactions FOR SELECT TO authenticated
USING (public.is_org_admin(organization_id));

-- I. Fraud Indicators
DROP POLICY IF EXISTS org_member_select_fraud_indicators ON public.fraud_indicators;
CREATE POLICY org_member_select_fraud_indicators ON public.fraud_indicators FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_member_update_fraud_indicators ON public.fraud_indicators;
CREATE POLICY org_member_update_fraud_indicators ON public.fraud_indicators FOR UPDATE TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()))
WITH CHECK (organization_id IN (SELECT public.get_auth_user_org_ids()));

-- J. Alerts
DROP POLICY IF EXISTS org_member_select_alerts ON public.alerts;
CREATE POLICY org_member_select_alerts ON public.alerts FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_member_update_alerts ON public.alerts;
CREATE POLICY org_member_update_alerts ON public.alerts FOR UPDATE TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()))
WITH CHECK (organization_id IN (SELECT public.get_auth_user_org_ids()));

-- K. Verification Events
DROP POLICY IF EXISTS org_member_select_verifications ON public.verification_events;
CREATE POLICY org_member_select_verifications ON public.verification_events FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

-- L. Organization Policies
DROP POLICY IF EXISTS org_member_select_policies ON public.organization_policies;
CREATE POLICY org_member_select_policies ON public.organization_policies FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

DROP POLICY IF EXISTS org_admin_manage_policies ON public.organization_policies;
CREATE POLICY org_admin_manage_policies ON public.organization_policies FOR ALL TO authenticated
USING (public.is_org_admin(organization_id))
WITH CHECK (public.is_org_admin(organization_id));

-- M. Audit Logs
DROP POLICY IF EXISTS org_member_select_audit_logs ON public.audit_logs;
CREATE POLICY org_member_select_audit_logs ON public.audit_logs FOR SELECT TO authenticated
USING (organization_id IN (SELECT public.get_auth_user_org_ids()));
