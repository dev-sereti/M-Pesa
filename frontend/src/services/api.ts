/**
 * API Service Layer
 * Handles all HTTP communication with the backend.
 * Implements automatic token refresh, request interceptors,
 * and secure token storage.
 */

const API_BASE_URL =
  process.env.REACT_APP_API_URL || "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface ProcessingJob {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  original_filename: string;
  created_at: string;
  transaction_count?: number;
  error_message?: string;
  download_url?: string;
}

export interface ProcessingStatus {
  job_id: string;
  status: string;
  progress?: number;
  message?: string;
  transaction_count?: number;
  download_url?: string;
}

export interface ApiError {
  error: string;
  detail?: string;
  code?: string;
}

// ─── Token Storage (In-Memory + HttpOnly Cookie approach) ──────────────────────
// Access tokens in memory only (never localStorage for security)
// Refresh tokens sent via httpOnly cookie in production

class TokenStore {
  private accessToken: string | null = null;
  private tokenExpiry: number = 0;

  setTokens(tokens: AuthTokens): void {
    this.accessToken = tokens.access_token;
    this.tokenExpiry = Date.now() + tokens.expires_in * 1000 - 30_000; // 30s buffer

    // Store refresh token in sessionStorage (upgrade to httpOnly cookie in production)
    sessionStorage.setItem("refresh_token", tokens.refresh_token);
  }

  getAccessToken(): string | null {
    if (this.isExpired()) {
      return null;
    }
    return this.accessToken;
  }

  getRefreshToken(): string | null {
    return sessionStorage.getItem("refresh_token");
  }

  isExpired(): boolean {
    return Date.now() >= this.tokenExpiry;
  }

  clear(): void {
    this.accessToken = null;
    this.tokenExpiry = 0;
    sessionStorage.removeItem("refresh_token");
  }
}

const tokenStore = new TokenStore();

// ─── HTTP Client ──────────────────────────────────────────────────────────────

class ApiClient {
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    requiresAuth = true
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;

    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    // Add auth header if required
    if (requiresAuth) {
      const token = await this.getValidToken();
      if (!token) {
        throw new Error("Authentication required");
      }
      headers["Authorization"] = `Bearer ${token}`;
    }

    // Don't set Content-Type for FormData (browser sets it with boundary)
    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include", // Include cookies
    });

    // Handle 401: Try token refresh
    if (response.status === 401 && requiresAuth) {
      return this.handleUnauthorized<T>(endpoint, options);
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        error: `HTTP ${response.status}`,
        detail: response.statusText,
      }));
      throw new ApiError(
        errorData.error || "Request failed",
        errorData.detail,
        response.status
      );
    }

    // Handle empty responses
    const contentType = response.headers.get("content-type");
    if (!contentType || response.status === 204) {
      return {} as T;
    }

    if (contentType.includes("application/json")) {
      return response.json();
    }

    // Binary response (Excel download)
    return response.blob() as unknown as T;
  }

  private async getValidToken(): Promise<string | null> {
    const token = tokenStore.getAccessToken();
    if (token) return token;

    // Token expired, try to refresh
    const refreshToken = tokenStore.getRefreshToken();
    if (!refreshToken) return null;

    return this.refreshAccessToken(refreshToken);
  }

  private async refreshAccessToken(
    refreshToken: string
  ): Promise<string | null> {
    if (this.isRefreshing) {
      // Queue requests during refresh
      return new Promise((resolve) => {
        this.refreshSubscribers.push(resolve);
      });
    }

    this.isRefreshing = true;

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        tokenStore.clear();
        window.dispatchEvent(new CustomEvent("auth:logout"));
        return null;
      }

      const tokens: AuthTokens = await response.json();
      tokenStore.setTokens(tokens);

      // Notify queued requests
      this.refreshSubscribers.forEach((cb) => cb(tokens.access_token));
      this.refreshSubscribers = [];

      return tokens.access_token;
    } catch {
      tokenStore.clear();
      return null;
    } finally {
      this.isRefreshing = false;
    }
  }

  private async handleUnauthorized<T>(
    endpoint: string,
    options: RequestInit
  ): Promise<T> {
    tokenStore.clear();
    window.dispatchEvent(new CustomEvent("auth:logout"));
    throw new ApiError("Session expired. Please log in again.", undefined, 401);
  }

  // ─── Auth Methods ────────────────────────────────────────────────────────────

  async signup(data: {
    email: string;
    username: string;
    password: string;
    confirm_password: string;
    full_name?: string;
  }): Promise<{ message: string; success: boolean }> {
    return this.request("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }, false);
  }

  async login(email: string, password: string): Promise<AuthTokens> {
    const tokens = await this.request<AuthTokens>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }, false);

    tokenStore.setTokens(tokens);
    return tokens;
  }

  async logout(): Promise<void> {
    const refreshToken = tokenStore.getRefreshToken();
    if (refreshToken) {
      await this.request("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => {});
    }
    tokenStore.clear();
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>("/api/users/me");
  }

  async changePassword(data: {
    current_password: string;
    new_password: string;
    confirm_password: string;
  }): Promise<{ message: string }> {
    return this.request("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // ─── Processing Methods ───────────────────────────────────────────────────────

  async uploadStatement(file: File, pin: string): Promise<ProcessingJob> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("pdf_pin", pin);

    return this.request<ProcessingJob>("/api/process/upload", {
      method: "POST",
      body: formData,
    });
  }

  async getJobStatus(jobId: string): Promise<ProcessingStatus> {
    return this.request<ProcessingStatus>(`/api/process/status/${jobId}`);
  }

  async downloadExcel(jobId: string): Promise<Blob> {
    const accessToken = await this.getValidToken();
    const response = await fetch(
      `${API_BASE_URL}/api/process/download/${jobId}`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
        credentials: "include",
      }
    );

    if (!response.ok) {
      throw new ApiError("Download failed", undefined, response.status);
    }

    return response.blob();
  }

  async listJobs(): Promise<ProcessingJob[]> {
    return this.request<ProcessingJob[]>("/api/process/jobs");
  }

  isAuthenticated(): boolean {
    return !!tokenStore.getRefreshToken();
  }
}

// Custom error class
export class ApiError extends Error {
  status?: number;
  detail?: string;

  constructor(message: string, detail?: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
    this.status = status;
  }
}

export const apiClient = new ApiClient();