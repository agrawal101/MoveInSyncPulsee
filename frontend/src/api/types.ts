export type Severity = 'low' | 'medium' | 'high' | 'positive' | 'informational';
export interface Warning { code: string; message: string; affected_rows: number | null }
export interface Metric { metric: string; current_value: number | null; previous_value: number | null; baseline_value: number | null; absolute_change: number | null; relative_change_pct: number | null; unit: string; sample_size: number | null; confidence: string; warnings: Warning[] }
export interface Overview { month: string; previous_month: string | null; baseline_month: string | null; metrics: Record<string, Metric>; data_quality_warnings: Warning[] }
export interface Anomaly { id: string; category: string; entity_type: string; entity_name: string; metric: string; current_value: number; baseline_value: number; absolute_change: number; relative_change_pct: number | null; severity: Severity; confidence: string; sample_size: number; reason: string; supporting_dimensions: Record<string, unknown>; data_quality_warnings: string[] }
export interface VendorResult { vendor: string; month: string; rank: number | null; metrics: Record<string, Metric>; deterioration_score: number; data_quality_warnings: Warning[][] }
export interface VendorAnalysis { current_month: string; baseline_month: string | null; vendors: VendorResult[] }
export interface Shift { month: string; shift_type: string; rider_legs: number; pickup_sample: number; avg_pickup_delay_minutes: number; late_5m: number; late_10m: number; no_shows: number; offices: number; vendors: number; late_5m_rate: number; late_10m_rate: number; no_show_rate: number; risk_score: number }
export interface ShiftReadiness { month: string; shifts: Shift[]; data_quality_warnings: Warning[] }
export interface Distribution { category?: string; vendor?: string; office?: string; count: number }
export interface Safety { month: string; filters: Record<string, string | null>; alert_count: number; trip_count: number; alerts_per_1000_trips: number | null; severity_distribution: Distribution[]; alert_type_distribution: Distribution[]; vendor_concentration: Distribution[]; office_concentration: Distribution[]; acknowledgement_minutes: Record<string, number | null>; repeated_vehicle_patterns: Array<{vehicle: string; count: number}>; data_quality_warnings: Warning[] }
export interface Cost { month: string; vendor: string | null; billed_rows: number; total_billing_amount: number | null; average_billing_amount: number | null; valid_distance_rows: number; excluded_distance_rows: number; distance_metric_coverage_pct: number; total_valid_distance_km: number | null; cost_per_km: number | null; data_quality_warnings: Warning[] }
export interface Experience { month: string; vendor: string | null; feedback_rows: number; dimensions: Record<string, {raw_average: number | null; nonzero_average: number | null; zero_count: number | null}>; data_quality_warnings: Warning[] }
export interface DataQuality { preprocessing: Record<string, unknown>; missing_ride_joins: Record<string, number>; ambiguous_trip_dimensions: number; high_null_fields: Array<{field: string; null_rows: number; total_rows: number}>; warnings: string[] }
export interface AgentFinding { title: string; description: string; metric: string | null; current_value: number | null; baseline_value: number | null; change: number | null; sample_size: number | null }
export interface AgentResponse {
  answer: string;
  summary: string;
  severity: Severity;
  confidence: string;
  synthesis_mode: 'llm' | 'deterministic_fallback';
  findings: AgentFinding[];
  recommended_actions: Array<{title: string; description: string; requires_approval: boolean}>;
  evidence: Array<{tool: string; description: string}>;
  data_quality_warnings: string[];
  execution: {
    request_id: string;
    tools_called: string[];
    tool_durations_ms: Record<string, number>;
    llm_duration_ms: number | null;
    duration_ms: number;
    provider: string | null;
    model: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
    fallback_used: boolean;
    error_category: string | null;
    repair_attempted: boolean;
    validator_rejection: Record<string, string | null> | null;
    validation_result: 'passed' | 'repaired' | 'deterministic_fallback';
  } | null;
}
