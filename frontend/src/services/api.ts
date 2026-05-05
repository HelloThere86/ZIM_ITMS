import { clearStoredAuth, getToken } from "./auth";

export const API_ORIGIN =
  import.meta.env.VITE_API_ORIGIN ?? "http://127.0.0.1:8000";
export const API_BASE_URL = `${API_ORIGIN}/api`;

function buildHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();

  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    clearStoredAuth();
    window.location.href = "/login";
    throw new Error("Session expired. Please login again.");
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `API request failed: ${response.status} ${response.statusText} ${errorText}`
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function fetchJson<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: buildHeaders(),
  });

  return handleResponse<T>(response);
}

export async function postJson<T>(endpoint: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  });

  return handleResponse<T>(response);
}

export async function putJson<T>(endpoint: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "PUT",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  });

  return handleResponse<T>(response);
}

export async function patchJson<T>(endpoint: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "PATCH",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  });

  return handleResponse<T>(response);
}

export async function deleteJson<T = void>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });

  return handleResponse<T>(response);
}

export function buildBackendAssetUrl(path?: string | null): string | null {
  if (!path) return null;

  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  if (path.startsWith("/")) {
    return `${API_ORIGIN}${path}`;
  }

  return `${API_ORIGIN}/${path}`;
}
