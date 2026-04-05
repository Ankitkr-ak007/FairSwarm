import axios, { type AxiosError } from "axios";

import type {
  AnalysisDetailResponse,
  AnalysisRecord,
  AnalysisStartRequest,
  DatasetRecord,
  DatasetUploadResponse,
  LoginRequest,
  ReportListItem,
  RegisterRequest,
  SwarmAnalyzeRequest,
  SwarmConsensusResult,
  SwarmStatusResponse,
} from "@/types";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
  timeout: 30_000,
});

api.interceptors.request.use((config) => {
  if (process.env.NODE_ENV === "development") {
    console.info("[api:request]", config.method?.toUpperCase(), config.url);
  }

  if (typeof window !== "undefined") {
    const token = localStorage.getItem("fairswarm_access_token");
    const csrfToken = localStorage.getItem("fairswarm_csrf_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    if (csrfToken) {
      config.headers["x-csrf-token"] = csrfToken;
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => {
    if (process.env.NODE_ENV === "development") {
      console.info(
        "[api:response]",
        response.config.method?.toUpperCase(),
        response.config.url,
        response.status
      );
    }
    return response;
  },
  (error: AxiosError) => {
    if (process.env.NODE_ENV === "development") {
      console.error("[api:error]", error.config?.url, error.response?.status);
    }

    if (typeof window !== "undefined" && error.response?.status === 401) {
      localStorage.removeItem("fairswarm_access_token");
      localStorage.removeItem("fairswarm_csrf_token");
      localStorage.removeItem("fairswarm_user");
      const target = `/login?reason=session-expired`;
      if (window.location.pathname !== "/login") {
        window.location.assign(target);
      }
    }

    return Promise.reject(error);
  }
);

export function normalizeApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string }>;
    return axiosError.response?.data?.detail ?? axiosError.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error occurred.";
}

export const authApi = {
  register: (payload: RegisterRequest) => api.post("/auth/register", payload),
  login: (payload: LoginRequest) => api.post("/auth/login", payload),
  me: () => api.get("/auth/me"),
  refresh: (refreshToken: string) => api.post("/auth/refresh", { refresh_token: refreshToken }),
  logout: () => api.post("/auth/logout"),
};

export const datasetsApi = {
  upload: (formData: FormData) =>
    api.post<DatasetUploadResponse>("/datasets/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  list: () => api.get<{ items: DatasetRecord[]; page: number; total: number }>("/datasets"),
  details: (datasetId: string) => api.get<DatasetRecord>(`/datasets/${datasetId}`),
  preview: (datasetId: string) => api.get<{ rows: Array<Record<string, unknown>> }>(`/datasets/${datasetId}/preview`),
  remove: (datasetId: string) => api.delete(`/datasets/${datasetId}`),
};

export const analysisApi = {
  list: () => api.get<{ items: AnalysisRecord[]; page: number; total: number }>("/analysis"),
  details: (analysisId: string) => api.get<AnalysisDetailResponse>(`/analysis/${analysisId}`),
  start: (payload: AnalysisStartRequest) => api.post<{ analysis_id: string; status: string }>(`/analysis/start`, payload),
  remove: (analysisId: string) => api.delete(`/analysis/${analysisId}`),
};

export const swarmApi = {
  analyze: (payload: SwarmAnalyzeRequest) => api.post<SwarmConsensusResult>("/ai/analyze", payload),
  status: (analysisId: string) => api.get<SwarmStatusResponse>(`/ai/status/${analysisId}`),
};

export const reportsApi = {
  list: () => api.get<{ items: ReportListItem[] }>("/reports"),
  json: (analysisId: string) => api.get(`/reports/${analysisId}/json`),
  pdf: (analysisId: string) => api.get<Blob>(`/reports/${analysisId}/pdf`, { responseType: "blob" }),
};

export async function uploadDataset(formData: FormData): Promise<DatasetUploadResponse> {
  const response = await datasetsApi.upload(formData);
  return response.data;
}

export async function startAnalysis(payload: AnalysisStartRequest): Promise<{ analysis_id: string; status: string }> {
  const response = await analysisApi.start(payload);
  return response.data;
}

export async function getAnalysis(analysisId: string): Promise<AnalysisDetailResponse> {
  const response = await analysisApi.details(analysisId);
  return response.data;
}

export async function downloadReport(analysisId: string): Promise<Blob> {
  const response = await reportsApi.pdf(analysisId);
  return response.data;
}

export async function getDatasets(): Promise<DatasetRecord[]> {
  const response = await datasetsApi.list();
  return response.data.items;
}

export default api;
