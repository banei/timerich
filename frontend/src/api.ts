const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8051";

export type ApiResponse<T> = {
  data: T | null;
  error: string | null;
  meta?: Record<string, unknown>;
};

function getToken(): string | null {
  return localStorage.getItem("token");
}

export function setAuth(token: string, username: string, role: string) {
  localStorage.setItem("token", token);
  localStorage.setItem("username", username);
  localStorage.setItem("role", role);
}

export function clearAuth() {
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  localStorage.removeItem("role");
}

export function getRole(): string | null {
  return localStorage.getItem("role");
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearAuth();
    window.location.href = "/login";
    throw new Error("未登录");
  }
  return res.json();
}
