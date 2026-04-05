export type Severity = "low" | "medium" | "high" | "critical";

export type FairnessGrade = "A" | "B" | "C" | "D" | "F";

export type AnalysisStatus = "pending" | "running" | "completed" | "failed";

export interface UserProfile {
  id: string;
  email: string;
  full_name?: string | null;
  organization?: string | null;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
  organization?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface DatasetRecord {
  id: string;
  name: string;
  description?: string;
  file_path?: string;
  file_size?: number;
  columns?: DatasetProfile | Record<string, unknown>;
  row_count?: number;
  sensitive_columns?: string[];
  status?: string;
  created_at?: string;
}

export interface DatasetProfile {
  columns: string[];
  dtypes: Record<string, string>;
  null_counts: Record<string, number>;
  unique_counts: Record<string, number>;
  row_count: number;
  file_size: number;
  sample_rows: Array<Record<string, unknown>>;
}

export interface DatasetUploadResponse {
  dataset_id: string;
  profile: DatasetProfile;
  detected_sensitive_cols: string[];
  validation: {
    is_valid: boolean;
    errors: string[];
    warnings: string[];
    target_column?: string | null;
    sensitive_columns: string[];
  };
}

export interface MetricResult {
  metric_name: string;
  value: number;
  threshold_min: number;
  threshold_max: number;
  is_fair: boolean;
  severity: Severity;
  plain_english_explanation: string;
}

export interface AnalysisRecord {
  id: string;
  dataset_id: string;
  status: AnalysisStatus;
  progress: number;
  created_at: string;
  completed_at?: string | null;
  swarm_config?: Record<string, unknown>;
}

export interface AnalysisStartRequest {
  dataset_id: string;
  sensitive_columns: string[];
  target_column: string;
  analysis_name?: string;
}

export interface BiasIndicator {
  attribute: string;
  metric_name: string;
  value: number;
  severity: Severity;
  plain_explanation: string;
}

export interface SwarmAgentResult {
  agent_name: string;
  specialty: string;
  confidence_score: number;
  bias_indicators: BiasIndicator[];
  top_finding: string;
  recommended_action: string;
  analysis_reasoning: string;
}

export interface SwarmConsensusResult {
  overall_swarm_score: number;
  fairness_grade: FairnessGrade;
  agreement_score: number;
  agents_completed: number;
  agents_failed: number;
  consensus_findings: BiasIndicator[];
  contested_findings: BiasIndicator[];
  agent_results: SwarmAgentResult[];
  top_recommendation: string;
  executive_summary: string;
  warnings?: string[];
}

export interface AnalysisDetailResponse {
  analysis: AnalysisRecord;
  bias_report: {
    id: string;
    overall_score: number;
    fairness_metrics: {
      metrics_by_sensitive_attribute: Record<
        string,
        {
          metrics: MetricResult[];
          fairness_score: number;
          biased_metrics: string[];
          mitigations: Array<{ metric: string; strategy: string; severity: Severity; description: string }>;
        }
      >;
      intersectional_bias?: {
        top_disparities?: Array<{
          combination: string[];
          disparity: number;
          severity: Severity;
          group_count: number;
          groups: Array<Record<string, unknown>>;
        }>;
      };
    };
    model_recommendations: Array<{
      metric: string;
      severity: Severity;
      strategy: string;
      description: string;
    }>;
    swarm_consensus?: SwarmConsensusResult;
  } | null;
  swarm_results: Array<Record<string, unknown>>;
}

export interface SwarmAnalyzeRequest {
  analysis_id: string;
  dataset_id: string;
  sensitive_columns: string[];
  target_column: string;
}

export interface SwarmStatusResponse {
  analysis_id: string;
  analysis_status: AnalysisStatus;
  analysis_progress: number;
  swarm_status: "pending" | "running" | "completed";
  agents_completed: number;
  partial_results: Array<Record<string, unknown>>;
  swarm_consensus?: SwarmConsensusResult;
}

export interface ReportListItem {
  id: string;
  analysis_id: string;
  overall_score: number;
  sensitive_attribute: string;
  created_at: string;
}
