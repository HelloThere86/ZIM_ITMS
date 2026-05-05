import type { AuthUser, Role } from "../context/AuthContext";
import { deleteJson, fetchJson, patchJson, postJson } from "./api";

export interface CreateUserPayload {
  full_name: string;
  email: string;
  badge_number?: string | null;
  role: Role;
  password: string;
}

export interface UpdateUserPayload {
  full_name?: string;
  badge_number?: string | null;
  role?: Role;
  is_active?: boolean;
  password?: string;
}

export function listUsers(): Promise<AuthUser[]> {
  return fetchJson<AuthUser[]>("/auth/users");
}

export function createUser(payload: CreateUserPayload): Promise<AuthUser> {
  return postJson<AuthUser>("/auth/users", payload);
}

export function updateUser(
  userId: number,
  payload: UpdateUserPayload
): Promise<AuthUser> {
  return patchJson<AuthUser>(`/auth/users/${userId}`, payload);
}

export function deactivateUser(userId: number): Promise<void> {
  return deleteJson<void>(`/auth/users/${userId}`);
}
