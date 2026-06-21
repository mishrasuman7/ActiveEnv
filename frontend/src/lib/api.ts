// Typed client for the ActiveEnv backend API.

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type Classification =
  | "correct"
  | "suspect"
  | "silently_wrong"
  | "unknown";

export interface UsageSite {
  file_path: string;
  line_number: number;
  usage_kind: string;
  snippet: string;
}

export interface Intent {
  expected_environment: string;
  expected_properties: Record<string, unknown>;
  gates: string;
  rationale: string;
  confidence: number;
  grounded: boolean;
  model: string;
}

export interface Finding {
  id: number;
  key_name: string;
  kind: string;
  classification: Classification;
  expected: Record<string, unknown>;
  reality: Record<string, unknown>;
  evidence: string;
  blast_radius: string;
  proposed_fix: string;
  confidence: number;
  resolved: boolean;
  fixed: boolean;
}

export interface ConfigKey {
  id: number;
  name: string;
  masked_value: string;
  value_hint: string;
  kind: string;
  is_secret: boolean;
  is_probeable: boolean;
  usage_count: number;
  usage_sites: UsageSite[];
  intent: Intent | null;
  finding: Finding | null;
}

export interface AuditEntry {
  id: number;
  action: string;
  detail: Record<string, unknown>;
  undone: boolean;
  created_at: string;
}

export interface Run {
  id: string;
  created_at: string;
  updated_at: string;
  status: string;
  source_type: string;
  target_environment: string;
  config_format: string;
  key_count: number;
  findings_summary: Record<Classification, number>;
  keys: ConfigKey[];
  audit?: AuditEntry[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    const err = new Error(`${res.status} ${res.statusText}: ${body}`);
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

export function createRun(payload: {
  config_text: string;
  files: Record<string, string>;
  target_environment: string;
}): Promise<Run> {
  return req<Run>("/api/runs/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function inferRun(id: string): Promise<Run> {
  return req<Run>(`/api/runs/${id}/infer/`, { method: "POST" });
}

export function probeRun(id: string): Promise<Run> {
  return req<Run>(`/api/runs/${id}/probe/`, { method: "POST" });
}

export function getRun(id: string): Promise<Run> {
  return req<Run>(`/api/runs/${id}/`);
}

export function approveFix(
  findingId: number,
  correctedValue: string,
): Promise<Finding> {
  return req<Finding>(`/api/findings/${findingId}/approve/`, {
    method: "POST",
    body: JSON.stringify({ corrected_value: correctedValue }),
  });
}

export function undoFix(findingId: number): Promise<Finding> {
  return req<Finding>(`/api/findings/${findingId}/undo/`, { method: "POST" });
}
