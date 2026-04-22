// Thin fetch helpers for the /api/auth/* endpoints and a shared
// AuthContext so any component in the tree can read the current user
// or trigger sign-out.

import { createContext, useContext } from "react";

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  created_at: string;
};

export type AuthContextValue = {
  user: AuthUser | null;
  setUser: (user: AuthUser | null) => void;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  setUser: () => {},
  signOut: async () => {},
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body === "object" && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // fall through
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const response = await fetch(`${API_BASE}/api/auth/me`, {
    credentials: "include",
  });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as AuthUser;
}

export async function signIn(email: string, password: string): Promise<AuthUser> {
  const response = await fetch(`${API_BASE}/api/auth/signin`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as AuthUser;
}

export async function signUp(
  email: string,
  password: string,
  name: string,
): Promise<AuthUser> {
  const response = await fetch(`${API_BASE}/api/auth/signup`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as AuthUser;
}

export async function signOut(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/signout`, {
    method: "POST",
    credentials: "include",
  });
}
