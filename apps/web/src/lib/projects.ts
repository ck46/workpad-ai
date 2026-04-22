// Thin fetch helpers for the /api/projects/* surface.
// Mirrors the pattern in lib/auth.ts: each call is a small function, errors
// are thrown as Error(detail) so the UI can surface them inline.

import { type ProjectSummary } from "./auth";

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export type ProjectMember = {
  user_id: string;
  email: string;
  name: string;
  role: "owner" | "member";
  created_at: string;
};

export type PendingInvite = {
  id: string;
  email: string;
  invited_by_user_id: string;
  expires_at: string;
  created_at: string;
};

export type ProjectDetail = ProjectSummary & {
  members: ProjectMember[];
  pending_invites: PendingInvite[];
};

export type InviteCreateResponse = {
  id: string;
  project_id: string;
  email: string;
  token: string;
  accept_url: string;
  expires_at: string;
};

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

export async function listProjects(): Promise<ProjectSummary[]> {
  const response = await fetch(`${API_BASE}/api/projects`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ProjectSummary[];
}

export async function createProject(name: string): Promise<ProjectSummary> {
  const response = await fetch(`${API_BASE}/api/projects`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ProjectSummary;
}

export async function getProjectDetail(projectId: string): Promise<ProjectDetail> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ProjectDetail;
}

export async function createInvite(
  projectId: string,
  email: string,
): Promise<InviteCreateResponse> {
  const response = await fetch(
    `${API_BASE}/api/projects/${projectId}/invites`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as InviteCreateResponse;
}
