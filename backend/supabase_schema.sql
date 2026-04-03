-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    organization VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- 2. Datasets Table
CREATE TABLE datasets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    file_path VARCHAR(512) NOT NULL,
    file_size BIGINT,
    columns JSONB,
    row_count INTEGER,
    sensitive_columns JSONB,
    status VARCHAR(50) DEFAULT 'unprocessed',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Status enum
CREATE TYPE analysis_status AS ENUM ('pending', 'running', 'completed', 'failed');

-- 3. Analyses Table
CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    status analysis_status DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    swarm_config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- 4. Bias Reports Table
CREATE TABLE bias_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    overall_score FLOAT,
    fairness_metrics JSONB,
    sensitive_attribute VARCHAR(255),
    model_recommendations JSONB,
    swarm_consensus JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. AI Swarm Results Table
CREATE TABLE ai_swarm_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    model_name VARCHAR(255),
    model_provider VARCHAR(255),
    bias_findings JSONB,
    confidence_score FLOAT,
    processing_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Audit Logs Table
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(255),
    resource_id UUID,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Triggers for updated_at
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_users
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trigger_update_datasets
    BEFORE UPDATE ON datasets
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- Indexes for performance
CREATE INDEX idx_datasets_user_id ON datasets(user_id);
CREATE INDEX idx_analyses_user_id ON analyses(user_id);
CREATE INDEX idx_analyses_dataset_id ON analyses(dataset_id);
CREATE INDEX idx_bias_reports_analysis_id ON bias_reports(analysis_id);
CREATE INDEX idx_ai_swarm_results_analysis_id ON ai_swarm_results(analysis_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);

-- Row Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE bias_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_swarm_results ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own data" ON users FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own data" ON users FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can manage own datasets" ON datasets FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own analyses" ON analyses FOR ALL USING (auth.uid() = user_id);

-- Since reports and results are tied to analysis which is tied to the user, we join check
CREATE POLICY "Users can view own bias reports" ON bias_reports FOR SELECT 
USING (EXISTS (SELECT 1 FROM analyses WHERE analyses.id = bias_reports.analysis_id AND analyses.user_id = auth.uid()));

CREATE POLICY "Users can view own ai swarm results" ON ai_swarm_results FOR SELECT 
USING (EXISTS (SELECT 1 FROM analyses WHERE analyses.id = ai_swarm_results.analysis_id AND analyses.user_id = auth.uid()));
