export type UserRole = "student" | "teacher" | "coordinator" | "admin";

export type ApiErrorCode =
  | "validation_error"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "service_not_configured"
  | "internal_error";

export interface ApiErrorEnvelope {
  error: {
    code: ApiErrorCode;
    message: string;
    request_id: string;
    details?: Array<{ field: string; message: string }>;
  };
}

export interface HealthResponse {
  status: "ok";
  request_id: string;
}

export interface ReadinessResponse {
  status: "ready";
  checks: { database: "ok" };
  request_id: string;
}

export type AudioJobStatus = "queued" | "processing" | "retrying" | "succeeded" | "failed";

export interface AudioJobRequest {
  session_id: string;
  storage_object_path: string;
  idempotency_key: string;
}

export interface AudioJobResponse {
  id: string;
  status: AudioJobStatus;
  attempt_count: number;
  max_attempts: number;
  request_id: string;
}
