const API_BASE = "/api";

export type User = { id: number; username: string; name: string; role: string; active: boolean; permissions?: string[] };
export type CandidateTag = { tag: string; score: number; category: string };
export type PaginationMeta = { total: number; limit: number; offset: number; has_more: boolean };
export type Candidate = {
  id: number;
  name_masked: string;
  title: string;
  city: string;
  source: string;
  owner_name: string;
  gender?: string;
  email_masked?: string;
  phone_masked?: string;
  tags: CandidateTag[];
  experience_analysis: { level: string; label: string; years: number; basis: string };
  raw_text?: string;
  resume_json?: Record<string, unknown>;
  parse_status?: string;
  parse_error?: string;
};
export type Job = {
  id: number;
  title: string;
  city: string;
  department: string;
  job_code: string;
  jd_text: string;
  jd_structured: {
    skill_tags_raw: string;
    skills?: { tag: string; weight: number }[];
    years_required?: number | null;
    salary_range?: { min_k: number; max_k: number } | null;
    education?: string | null;
    must_have?: string[];
    nice_to_have?: string[];
  };
  status: string;
  match_count?: number;
  pipeline_count?: number;
};

export type OrganizationUnit = {
  id: number;
  parent_id?: number | null;
  name: string;
  unit_type: string;
  manager_employee_id?: number | null;
  manager_name?: string;
  hrbp_user_id?: number | null;
  hrbp_name?: string;
  city?: string;
  headcount_plan?: number | null;
  employee_count?: number;
  vacancy_count?: number;
  status: string;
  children?: OrganizationUnit[];
};

export type EmployeeCompensation = {
  id: number;
  employee_id: number;
  salary_monthly_k?: number | null;
  salary_annual_k?: number | null;
  salary_months: number;
  bonus_k?: number | null;
  currency: string;
  source: string;
  effective_date?: string | null;
};

export type EmployeeProfile = {
  id: number;
  candidate_id?: number | null;
  organization_unit_id?: number | null;
  organization_unit?: OrganizationUnit | null;
  current_job_id?: number | null;
  current_job?: Job | null;
  employee_no?: string;
  name: string;
  phone?: string;
  email?: string;
  department?: string;
  current_title: string;
  level?: string;
  city?: string;
  employment_status: string;
  hire_date?: string | null;
  birth_date?: string | null;
  age?: number | null;
  seniority_years?: number | null;
  education?: string | null;
  graduation_school?: string | null;
  graduation_date?: string | null;
  manager_name?: string;
  compensation?: EmployeeCompensation | null;
  salary_hidden?: boolean;
  tags: CandidateTag[];
  experience_analysis: { level: string; label: string; years: number; basis: string };
  resume_json?: Record<string, unknown>;
  raw_text?: string;
  candidate?: Candidate | null;
  analyses?: EmployeeAnalysis[];
};

export type EmployeeAnalysis = {
  id: number;
  employee_id: number;
  job_id?: number | null;
  job?: Job | null;
  match_score: number;
  salary_score: number;
  salary_status: string;
  risk_level: string;
  analysis: {
    summary?: string;
    job_fit?: MatchResult["reason"] & { score: number; summary?: string };
    salary?: Record<string, unknown>;
    actions?: string[];
  };
  source: string;
  created_at?: string;
};

export type EmployeeRecommendation = {
  id: number;
  employee_id: number;
  recommendation_type: "transfer" | "replacement";
  target_job_id?: number | null;
  target_job?: Job | null;
  candidate_id?: number | null;
  candidate?: Candidate | null;
  score: number;
  reason: Record<string, unknown>;
};
export type MatchResult = {
  id?: number;
  candidate_id: number;
  candidate: Candidate;
  score: number;
  reason: {
    hits: {
      jd_tag: string;
      job_weight: number;
      candidate_tag: string;
      candidate_score: number;
      match_type: "exact" | "related";
    }[];
    missing_tags: string[];
    match_rate: number;
    capability_rate: number;
  };
};

export type InterviewAssignment = {
  id: number;
  candidate_id: number;
  candidate: Candidate;
  job_id: number;
  job: Job;
  interviewer_id: number;
  interviewer: User;
  round: string;
  scheduled_at: string;
  location?: string;
  note?: string;
  status: string;
  created_by: string;
  created_at: string;
};

export type AiInterviewPlan = {
  avatar: { name: string; role: string; voice: string };
  meeting: { provider: string; location: string; auto_join: boolean; note: string };
  opening: string;
  questions: { type: string; question: string; rubric: string }[];
  rubric: string[];
  closing: string;
  source: string;
};

export type PublicInterviewRoom = { assignment: InterviewAssignment; plan: AiInterviewPlan };
export type InterviewTurnReply = { reply: string; source: string };
export type InterviewMessage = { role: "ai" | "candidate"; text: string };

export type InterviewFeedback = {
  id: number;
  assignment_id: number;
  interviewer_id: number;
  interviewer: User;
  rating: number;
  decision: string;
  strengths?: string;
  risks?: string;
  comment?: string;
  created_at: string;
};

export type AuditLog = {
  id: number;
  user_id: number;
  user_name: string;
  action: string;
  target_type: string;
  target_id?: number | null;
  target_name?: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type BackgroundTask = {
  id: number;
  task_type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error?: string | null;
  attempts: number;
  max_attempts: number;
  creator_name?: string;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type LLMUsageSummary = {
  period_days: number;
  summary: {
    total_calls: number;
    failed_calls: number;
    success_rate: number;
    failure_rate: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    avg_daily_calls: number;
    avg_daily_cost_usd: number;
  };
  limits: { daily_call_limit: number; daily_cost_limit_usd: number; failure_rate_warn_percent: number };
  alerts: { key: string; severity: "error" | "warning"; message: string }[];
};

export type SystemReadiness = {
  ready: boolean;
  environment: string;
  database: string;
  summary: { errors: number; warnings: number; total: number };
  checks: { key: string; ok: boolean; message: string; severity: "error" | "warning" }[];
};

export type DataIntegrity = {
  ready: boolean;
  checked_at: string;
  database: string;
  upload_dir: string;
  summary: { errors: number; warnings: number; total: number };
  counts: Record<string, number>;
  checks: { key: string; ok: boolean; message: string; severity: "error" | "warning"; count: number }[];
  details: {
    orphan_relations: Record<string, number>;
    duplicates: Record<string, { value: string; count: number }[]>;
    missing_uploads: { batch_id: string; filename: string }[];
  };
};

export type NotificationChannel = {
  id: number;
  name: string;
  channel_type: "email" | "webhook" | "wecom" | "sms" | "console";
  enabled: boolean;
  config: Record<string, unknown>;
  creator_name?: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type NotificationEvent = {
  id: number;
  event_type: string;
  name: string;
  enabled: boolean;
  channel_id?: number | null;
  channel?: NotificationChannel | null;
  template_subject?: string | null;
  template_body: string;
};

export type NotificationLog = {
  id: number;
  channel_id?: number | null;
  channel?: NotificationChannel | null;
  event_type: string;
  recipient?: string;
  subject?: string;
  content: string;
  status: string;
  provider_response: Record<string, unknown>;
  error?: string | null;
  creator_name?: string;
  created_at?: string | null;
};

export type BossSyncItem = {
  id: number;
  sync_job_id: number;
  item_type: string;
  external_id?: string | null;
  status: string;
  target_type?: string | null;
  target_id?: number | null;
  error?: string | null;
  raw_summary?: string | null;
  created_at?: string | null;
};

export type BossSyncJob = {
  id: number;
  sync_type: "candidate_batch" | "job_batch" | "screen_resume" | string;
  source: string;
  status: "running" | "succeeded" | "partial" | "failed" | string;
  total_count: number;
  success_count: number;
  failed_count: number;
  result: Record<string, unknown>;
  error?: string | null;
  parent_sync_job_id?: number | null;
  creator_name?: string;
  created_at?: string | null;
  finished_at?: string | null;
  items?: BossSyncItem[];
  payload?: Record<string, unknown>;
};

export type OfferRecord = {
  id: number;
  candidate_id: number;
  candidate: Candidate;
  job_id: number;
  job: Job;
  salary_min_k?: number | null;
  salary_max_k?: number | null;
  salary_months: number;
  city?: string;
  start_date?: string | null;
  status: string;
  note?: string;
  created_by: string;
  created_at: string;
  updated_at?: string;
};

export type AgentResponse = {
  answer: string;
  tool: string;
  result: unknown;
  pending_action?: Record<string, unknown> | null;
  suggestions: string[];
  readonly: boolean;
};

type ApiResponse<T> = { status: "ok"; data: T; message: string };
type FeedbackType = "success" | "error";

let token = localStorage.getItem("hireinsight_token") || "";

export function setToken(value: string) {
  token = value;
  localStorage.setItem("hireinsight_token", value);
}

export function clearToken() {
  token = "";
  localStorage.removeItem("hireinsight_token");
}

export function notify(type: FeedbackType, text: string) {
  const detail = { type, text };
  try {
    window.dispatchEvent(new CustomEvent("hireinsight-feedback", { detail }));
  } catch {
    const event = new Event("hireinsight-feedback") as CustomEvent<typeof detail>;
    Object.defineProperty(event, "detail", { value: detail });
    window.dispatchEvent(event);
  }
}

function shouldNotify(init: RequestInit) {
  return (init.method || "GET").toUpperCase() !== "GET";
}

function queryString(params?: Record<string, string | number | boolean | undefined | null>) {
  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers
      }
    });
    const body = await response.json();
    if (!response.ok) {
      const text = body.error || "请求失败";
      notify("error", text);
      throw new Error(text);
    }
    if (shouldNotify(init) && body.message) notify("success", body.message);
    return (body as ApiResponse<T>).data;
  } catch (error) {
    if (error instanceof TypeError) notify("error", "网络连接失败");
    throw error;
  }
}

async function upload<T>(path: string, formData: FormData): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: formData
    });
    const body = await response.json();
    if (!response.ok) {
      const text = body.error || "请求失败";
      notify("error", text);
      throw new Error(text);
    }
    if (body.message) notify("success", body.message);
    return (body as ApiResponse<T>).data;
  } catch (error) {
    if (error instanceof TypeError) notify("error", "网络连接失败");
    throw error;
  }
}

async function download(path: string, filename: string) {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      }
    });
    if (!response.ok) {
      notify("error", "下载失败");
      throw new Error("下载失败");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    notify("success", "导出已开始下载");
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    if (error instanceof TypeError) notify("error", "网络连接失败");
    throw error;
  }
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),
  me: () => request<User>("/auth/me"),
  users: () => request<{ items: User[] }>("/users"),
  auditLogs: () => request<{ items: AuditLog[] }>("/audit/logs"),
  readiness: () => request<SystemReadiness>("/system/readiness"),
  dataIntegrity: () => request<DataIntegrity>("/system/data-integrity"),
  llmUsage: (days = 30) => request<LLMUsageSummary>(`/system/llm/usage?days=${days}`),
  notificationChannels: () => request<{ items: NotificationChannel[]; channel_types: string[] }>("/notifications/channels"),
  createNotificationChannel: (payload: { name: string; channel_type: string; enabled?: boolean; config?: Record<string, unknown> }) =>
    request<NotificationChannel>("/notifications/channels", { method: "POST", body: JSON.stringify(payload) }),
  updateNotificationChannel: (id: number, payload: Partial<NotificationChannel> & { config?: Record<string, unknown> }) =>
    request<NotificationChannel>(`/notifications/channels/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteNotificationChannel: (id: number) => request<{ deleted: number }>(`/notifications/channels/${id}`, { method: "DELETE" }),
  notificationEvents: () => request<{ items: NotificationEvent[] }>("/notifications/events"),
  saveNotificationEvent: (payload: Partial<NotificationEvent> & { event_type: string; name: string }) =>
    request<NotificationEvent>("/notifications/events", { method: "POST", body: JSON.stringify(payload) }),
  updateNotificationEvent: (id: number, payload: Partial<NotificationEvent>) =>
    request<NotificationEvent>(`/notifications/events/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  notificationLogs: (params?: { status?: string; event_type?: string; channel_id?: number }) => request<{ items: NotificationLog[] }>(`/notifications/logs${queryString(params)}`),
  sendTestNotification: (payload: { channel_id?: number; recipient?: string; subject?: string; content?: string }) =>
    request<{ log: NotificationLog }>("/notifications/send-test", { method: "POST", body: JSON.stringify(payload) }),
  tasks: (status = "all") => request<{ items: BackgroundTask[]; status_counts: Record<string, number> }>(`/tasks?status=${status}`),
  retryTask: (id: number) => request<BackgroundTask>(`/tasks/${id}/retry`, { method: "POST" }),
  interviewers: () => request<{ items: User[] }>("/users/interviewers"),
  createUser: (payload: { username: string; name: string; role: string; password: string }) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: Partial<Pick<User, "name" | "role" | "active">> & { password?: string }) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  candidates: (experience = "all") => request<{ items: Candidate[]; experience_stats: { key: string; label: string; count: number }[] }>(`/candidates?experience_level=${experience}`),
  getCandidate: (id: number) => request<Candidate>(`/candidates/${id}`),
  candidateResume: (id: number) => download(`/candidates/${id}/resume.txt`, `candidate-${id}-resume.txt`),
  updateCandidate: (id: number, payload: Partial<Pick<Candidate, "name_masked" | "email_masked" | "phone_masked" | "title" | "city" | "gender">> & { summary?: string }) =>
    request<Candidate>(`/candidates/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  updateCandidateTags: (id: number, tags: { tag: string; score: number }[]) =>
    request<Candidate>(`/candidates/${id}/tags`, { method: "PUT", body: JSON.stringify({ tags }) }),
  deleteCandidate: (id: number) => request<{ deleted: number }>(`/candidates/${id}`, { method: "DELETE" }),
  retryParseResume: (id: number) => request<{ candidate: Candidate }>(`/resume/${id}/retry-parse`, { method: "POST" }),
  retryParseResumeAsync: (id: number) => request<{ task: BackgroundTask }>(`/resume/${id}/retry-parse?async=1`, { method: "POST" }),
  uploadResume: (files: File | File[]) => {
    const formData = new FormData();
    for (const file of Array.isArray(files) ? files : [files]) {
      formData.append("files", file);
    }
    return upload<{
      candidate: Candidate;
      candidates: Candidate[];
      batch: { id: string; filename: string; status: string } | null;
      batches: { id: string; filename: string; status: string }[];
      errors: { filename: string; error: string }[];
      success_count: number;
      failed_count: number;
    }>("/resume/upload", formData);
  },
  organizationTree: () => request<{ items: OrganizationUnit[] }>("/organization/tree"),
  createOrganizationUnit: (payload: Partial<OrganizationUnit>) =>
    request<OrganizationUnit>("/organization/units", { method: "POST", body: JSON.stringify(payload) }),
  updateOrganizationUnit: (id: number, payload: Partial<OrganizationUnit>) =>
    request<OrganizationUnit>(`/organization/units/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteOrganizationUnit: (id: number) => request<{ deleted: number }>(`/organization/units/${id}`, { method: "DELETE" }),
  importOrganizationExcel: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return upload<{ created: OrganizationUnit[]; tree: OrganizationUnit[] }>("/organization/import-excel", formData);
  },
  uploadOrganizationEmployeeResumes: (unitId: number, files: File | File[]) => {
    const formData = new FormData();
    for (const file of Array.isArray(files) ? files : [files]) {
      formData.append("files", file);
    }
    return upload<{ unit: OrganizationUnit; employees: EmployeeProfile[]; candidates: Candidate[]; errors: { filename: string; error: string }[]; success_count: number; failed_count: number }>(`/organization/units/${unitId}/employee-resumes`, formData);
  },
  organizationEmployees: (unitId: number, params?: { limit?: number; offset?: number; q?: string }) => request<{ unit: OrganizationUnit; items: EmployeeProfile[] } & PaginationMeta>(`/organization/units/${unitId}/employees${queryString(params)}`),
  organizationOverview: (unitId: number) => request<{ total: number; active: number; inactive: number; with_compensation: number; analyzed: number; high_fit: number; salary_risk: number; avg_match_score: number; unit: OrganizationUnit }>(`/organization/units/${unitId}/overview`),
  employees: (organizationUnitId?: number, params?: { limit?: number; offset?: number; q?: string }) => request<{ items: EmployeeProfile[]; overview: { total: number; active: number; inactive: number; with_compensation: number; analyzed: number; high_fit: number; salary_risk: number; avg_match_score: number; avg_seniority_years: number } } & PaginationMeta>(`/employees${queryString({ organization_unit_id: organizationUnitId || undefined, ...params })}`),
  getEmployee: (id: number) => request<EmployeeProfile>(`/employees/${id}`),
  createEmployeeFromCandidate: (payload: { candidate_id: number; organization_unit_id?: number; current_job_id?: number; employee_no?: string; level?: string; salary_monthly_k?: string | number; salary_annual_k?: string | number; salary_months?: string | number; hire_date?: string; birth_date?: string; education?: string; graduation_school?: string; graduation_date?: string; manager_name?: string }) =>
    request<EmployeeProfile>("/employees/from-candidate", { method: "POST", body: JSON.stringify(payload) }),
  updateEmployee: (id: number, payload: Partial<EmployeeProfile> & { salary_monthly_k?: string | number; salary_annual_k?: string | number; salary_months?: string | number; bonus_k?: string | number }) =>
    request<EmployeeProfile>(`/employees/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  importEmployees: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return upload<{ created_count: number; updated_count: number; skipped_count: number; failed_count: number; created: { row: number; employee: EmployeeProfile }[]; updated: { row: number; employee: EmployeeProfile }[]; skipped: { row: number; reason: string }[]; errors: { row: number; error: string }[] }>("/employees/import-excel", formData);
  },
  importEmployeeCompensations: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return upload<{ updated_count: number; skipped_count: number; failed_count: number; updated: { row: number; employee: EmployeeProfile; compensation: EmployeeCompensation }[]; skipped: { row: number; reason: string }[]; errors: { row: number; error: string }[] }>("/employees/compensation-import", formData);
  },
  analyzeEmployeeCurrentJob: (id: number) => request<EmployeeAnalysis>(`/employees/${id}/analyze-current-job`, { method: "POST" }),
  batchAnalyzeEmployees: (payload: { organization_unit_id?: number; employee_ids?: number[]; limit?: number }) =>
    request<{ items: EmployeeAnalysis[]; skipped: { employee_id: number; name: string; reason: string }[]; analyzed_count: number; skipped_count: number }>("/employees/batch-analyze", { method: "POST", body: JSON.stringify(payload) }),
  recommendEmployeeTransfer: (id: number) => request<{ items: EmployeeRecommendation[] }>(`/employees/${id}/recommend-transfer`, { method: "POST" }),
  recommendEmployeeReplacement: (id: number) => request<{ items: EmployeeRecommendation[] }>(`/employees/${id}/recommend-replacement`, { method: "POST" }),
  employeeReport: (id: number) => download(`/employees/${id}/report.txt`, `employee-${id}-report.txt`),
  jobs: () => request<{ items: Job[] }>("/jobs"),
  getJob: (id: number) => request<Job>(`/jobs/${id}`),
  createJob: (payload: Partial<Job> & { skill_tags_raw: string }) =>
    request<Job>("/jobs", { method: "POST", body: JSON.stringify(payload) }),
  generateJobJd: (payload: Partial<Job> & { skill_tags_raw?: string }) =>
    request<{ jd_text: string; skill_tags_raw: string; structured: Job["jd_structured"]; source: string }>("/jobs/ai-generate", { method: "POST", body: JSON.stringify(payload) }),
  calibrateJobJd: (payload: Partial<Job> & { skill_tags_raw?: string }) =>
    request<{ jd_text: string; skill_tags_raw: string; structured: Job["jd_structured"]; source: string }>("/jobs/ai-calibrate", { method: "POST", body: JSON.stringify(payload) }),
  updateJob: (id: number, payload: Partial<Job> & { skill_tags_raw?: string }) =>
    request<Job>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  closeJob: (id: number) => request<Job>(`/jobs/${id}/close`, { method: "POST" }),
  restoreJob: (id: number) => request<Job>(`/jobs/${id}/restore`, { method: "POST" }),
  deleteJob: (id: number) => request<{ deleted: number }>(`/jobs/${id}`, { method: "DELETE" }),
  matchPreview: (jobId: number, limit = 5) => request<{ job: Job; items: MatchResult[] }>(`/jobs/${jobId}/match-preview?limit=${limit}`),
  matchJob: (jobId: number) => request<{ job: Job; items: MatchResult[] }>(`/jobs/${jobId}/match`, { method: "POST" }),
  batchPipeline: (jobId: number, payload: { candidate_ids?: number[]; candidate_id?: number; stage?: string; note?: string }) =>
    request<{ created: PipelineItem[]; skipped: { candidate_id: number; stage: string }[]; missing: number[] }>(`/jobs/${jobId}/batch-pipeline`, { method: "POST", body: JSON.stringify(payload) }),
  pipeline: (jobId: number) => request<{ stages: string[]; columns: Record<string, PipelineItem[]> }>(`/pipeline/${jobId}/board`),
  pipelineHistory: (jobId: number, candidateId: number) => request<{ items: PipelineItem[] }>(`/pipeline/${jobId}/history/${candidateId}`),
  movePipeline: (payload: { candidate_id: number; job_id: number; stage: string; note?: string }) =>
    request<PipelineItem>("/pipeline/move", { method: "POST", body: JSON.stringify(payload) }),
  pipelineOverview: () => request<{ total: number; stages: Record<string, number>; jobs: Record<string, number>; items: PipelineItem[] }>("/pipeline/overview"),
  interviewAssignments: () => request<{ items: InterviewAssignment[] }>("/interview/assignments"),
  getInterviewAssignment: (id: number) => request<InterviewAssignment>(`/interview/assignments/${id}`),
  createInterviewAssignment: (payload: { candidate_id: number; job_id: number; interviewer_id: number; round: string; scheduled_at: string; location?: string; note?: string }) =>
    request<InterviewAssignment>("/interview/assignments", { method: "POST", body: JSON.stringify(payload) }),
  updateInterviewAssignment: (id: number, payload: Partial<Pick<InterviewAssignment, "interviewer_id" | "round" | "scheduled_at" | "location" | "note">>) =>
    request<InterviewAssignment>(`/interview/assignments/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  interviewAiPlan: (id: number) => request<AiInterviewPlan>(`/interview/assignments/${id}/ai-plan`, { method: "POST" }),
  interviewRoomLink: (id: number) => request<{ token: string; path: string; url: string }>(`/interview/assignments/${id}/room-link`, { method: "POST" }),
  publicInterviewRoom: (token: string) => request<PublicInterviewRoom>(`/public/interview-room/${token}`),
  publicInterviewTurn: (token: string, payload: { question: string; answer?: string; intent?: "followup" | "clarify"; candidate_question?: string }) =>
    request<InterviewTurnReply>(`/public/interview-room/${token}/turn`, { method: "POST", body: JSON.stringify(payload) }),
  publicInterviewComplete: (token: string, payload: { answers: string[]; messages: InterviewMessage[]; cheat_events?: string[] }) =>
    request<{ assignment: InterviewAssignment; feedback: InterviewFeedback; closing: string }>(`/public/interview-room/${token}/complete`, { method: "POST", body: JSON.stringify(payload) }),
  cancelInterviewAssignment: (id: number) => request<InterviewAssignment>(`/interview/assignments/${id}/cancel`, { method: "POST" }),
  deleteInterviewAssignment: (id: number) => request<{ deleted: number }>(`/interview/assignments/${id}`, { method: "DELETE" }),
  submitInterviewFeedback: (payload: { assignment_id: number; rating: number; decision: string; strengths?: string; risks?: string; comment?: string }) =>
    request<InterviewFeedback>("/interview/feedback", { method: "POST", body: JSON.stringify(payload) }),
  interviewFeedback: (assignmentId: number) => request<{ items: InterviewFeedback[] }>(`/interview/feedback?assignment_id=${assignmentId}`),
  interviewReport: (assignmentId: number) => download(`/interview/assignments/${assignmentId}/report.txt`, `interview-report-${assignmentId}.txt`),
  offers: (status = "all") => request<{ items: OfferRecord[]; statuses: string[] }>(`/offers?status=${status}`),
  getOffer: (id: number) => request<OfferRecord>(`/offers/${id}`),
  createOffer: (payload: { candidate_id: number; job_id: number; salary_min_k?: number | string; salary_max_k?: number | string; salary_months?: number | string; city?: string; start_date?: string; status?: string; note?: string }) =>
    request<OfferRecord>("/offers", { method: "POST", body: JSON.stringify(payload) }),
  updateOffer: (id: number, payload: Partial<Pick<OfferRecord, "status" | "city" | "note" | "start_date" | "salary_min_k" | "salary_max_k" | "salary_months">>) =>
    request<OfferRecord>(`/offers/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteOffer: (id: number) => request<{ deleted: number }>(`/offers/${id}`, { method: "DELETE" }),
  offerLetter: (id: number) => download(`/offers/${id}/letter.txt`, `offer-${id}.txt`),
  bi: (days = 30) => request<BiOverview>(`/bi/overview?days=${days}`),
  exportCsv: (kind: "candidates" | "jobs" | "interviews" | "offers" | "pipeline" | "employees") => download(`/exports/${kind}.csv`, `${kind}.csv`),
  tags: () => request<{ items: SkillTag[]; categories: string[] }>("/tags"),
  bossStatus: () => request<{
    cookie_bound: boolean;
    account: string;
    mode: string;
    can_auto_send: boolean;
    verified?: boolean;
    account_id?: number | null;
    candidate_count?: number;
    job_count?: number;
    last_candidate_at?: string | null;
    last_job_at?: string | null;
  }>("/boss/status"),
  bossExtension: () => download("/boss/extension.zip", "hireinsight-boss-importer.zip"),
  verifyBossAccount: (id: number) =>
    request<{ account: { id: number; account: string; verified: boolean } }>(`/boss/accounts/${id}/verify`, { method: "POST" }),
  bossJobs: () => request<{ items: Job[] }>("/boss/jobs"),
  bossJobImport: (items: { external_id?: string; title: string; city?: string; jd_text?: string; summary?: string }[]) =>
    request<{ items: Job[]; errors: { title: string; error: string }[]; sync_job?: BossSyncJob }>("/boss/jobs/batch-import", { method: "POST", body: JSON.stringify({ items }) }),
  bossSyncJobs: (params?: { sync_type?: string; status?: string; source?: string; limit?: number; offset?: number }) =>
    request<{ items: BossSyncJob[] } & PaginationMeta>(`/boss/sync/jobs${queryString(params)}`),
  bossSyncJob: (id: number) => request<BossSyncJob>(`/boss/sync/jobs/${id}`),
  retryBossSyncJob: (id: number) =>
    request<{ retried: boolean; source_job: BossSyncJob; retry_result?: { items?: Candidate[] | Job[]; errors?: { error: string }[]; sync_job?: BossSyncJob } }>(`/boss/sync/jobs/${id}/retry`, { method: "POST" }),
  bossJobRecommendations: (jobId: number, limit = 8) => request<{ job: Job; items: MatchResult[] }>(`/boss/jobs/${jobId}/recommendations?limit=${limit}`),
  bossInbox: () => request<{ items: BossInboxItem[] }>("/boss/candidates/inbox"),
  bossImport: (items: BossInboxItem[]) => request<{ items: Candidate[]; errors: { name: string; error: string }[]; sync_job?: BossSyncJob }>("/boss/candidates/batch-import", { method: "POST", body: JSON.stringify({ items }) }),
  bossAiScreen: (payload: { job_id: number; candidate_ids?: number[]; limit?: number }) =>
    request<{ created: PipelineItem[]; skipped: { candidate_id: number; stage: string }[] }>("/boss/candidates/ai-screen", { method: "POST", body: JSON.stringify(payload) }),
  agentTools: () => request<{ items: { name: string; description: string }[]; readonly: boolean }>("/agent/tools"),
  chat: (message: string, pending_action?: Record<string, unknown> | null) =>
    request<AgentResponse>("/agent/chat", { method: "POST", body: JSON.stringify({ message, pending_action }) })
};

export type PipelineItem = {
  id: number;
  candidate_id: number;
  candidate: Candidate;
  job_id: number;
  stage: string;
  note: string;
  updated_by?: string;
  ts?: string;
};

export type BossInboxItem = { external_id: string; name: string; title: string; summary: string; candidate_id?: number; imported?: boolean; created_at?: string };
export type SkillTag = { tag: string; category: string; aliases: string[] };

export type BiOverview = {
  period_days: number;
  total_candidates: number;
  active_jobs: number;
  source_quality: Record<string, number>;
  pipeline_funnel: Record<string, number>;
  experience_stats: { key: string; label: string; count: number }[];
  top_tags: [string, number][];
};
