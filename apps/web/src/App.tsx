import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { create } from "zustand";
import { useAuth } from "./lib/auth";
import { useSystemTheme, type SystemTheme } from "./lib/systemTheme";
import { LibraryHome, type ArtifactListItem } from "./components/LibraryHome";
import { ArtifactDiffView } from "./components/ArtifactDiffView";
import { Editor as MonacoEditor } from "@monaco-editor/react";
import type { editor as MonacoEditorNS } from "monaco-editor";
import {
  EditorContent,
  NodeViewWrapper,
  ReactNodeViewRenderer,
  type Editor as TiptapEditorType,
  type NodeViewProps,
  useEditor,
} from "@tiptap/react";
import { Node as TiptapNode, mergeAttributes, nodePasteRule } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import { marked } from "marked";
import { markedHighlight } from "marked-highlight";
import markedKatex from "marked-katex-extension";
import hljs from "highlight.js";
import mermaid from "mermaid";
import TurndownService from "turndown";
import DOMPurify from "dompurify";

import "katex/dist/katex.min.css";
import "highlight.js/styles/github.css";

mermaid.initialize({
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "strict",
  fontFamily: "inherit",
});
// Kept in sync with MERMAID_PREVIEW_CONFIG below (the export path flips
// config temporarily; we restore back to these values).

marked.use(
  markedHighlight({
    langPrefix: "hljs language-",
    highlight(code, lang) {
      if (!lang || lang === "mermaid") {
        return code;
      }
      const language = hljs.getLanguage(lang) ? lang : "plaintext";
      try {
        return hljs.highlight(code, { language, ignoreIllegals: true }).value;
      } catch {
        return code;
      }
    },
  }),
  markedKatex({ throwOnError: false, nonStandard: true }),
);
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  Copy,
  FileCode2,
  FileDown,
  LoaderCircle,
  Archive,
  ArchiveRestore,
  FileText,
  GitCommit,
  GitPullRequest,
  Github,
  History,
  LogOut,
  MessageSquareText,
  Mic,
  Moon,
  MoreHorizontal,
  NotebookPen,
  X,
  Trash2,
  User,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Redo2,
  RefreshCcw,
  Settings,
  Share2,
  Sparkles,
  Sun,
  Undo2,
} from "lucide-react";

const SIDEBAR_COLLAPSED_STORAGE_KEY = "workpad-sidebar-collapsed";

function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "1";
  });

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  return [collapsed, () => setCollapsed((value) => !value)];
}

type CanvasTheme = "light" | "dark";
type CanvasMode = "edit" | "preview" | "diff";

const CANVAS_THEME_STORAGE_KEY = "workpad-canvas-theme";
const CANVAS_MODE_STORAGE_KEY = "workpad-canvas-mode";

const CANVAS_ON_LEFT_STORAGE_KEY = "workpad-canvas-on-left";

function useCanvasOnLeft(): [boolean, () => void] {
  // Design v2 locks the layout as: sidebar | chat | paper. Chat is always the
  // middle column; the paper editor is the dominant right column. The hook
  // remains only so older stored preferences don't break existing call sites.
  const [canvasOnLeft, setCanvasOnLeft] = useState<boolean>(false);
  useEffect(() => {
    window.localStorage.setItem(CANVAS_ON_LEFT_STORAGE_KEY, "0");
  }, []);
  return [canvasOnLeft, () => setCanvasOnLeft((value) => !value)];
}

function useCanvasMode(): [CanvasMode, (mode: CanvasMode) => void] {
  const [mode, setMode] = useState<CanvasMode>(() => {
    if (typeof window === "undefined") {
      return "edit";
    }
    return window.localStorage.getItem(CANVAS_MODE_STORAGE_KEY) === "preview" ? "preview" : "edit";
  });

  useEffect(() => {
    window.localStorage.setItem(CANVAS_MODE_STORAGE_KEY, mode);
  }, [mode]);

  return [mode, setMode];
}

function useCanvasTheme(): [CanvasTheme, () => void] {
  const [theme, setTheme] = useState<CanvasTheme>(() => {
    if (typeof window === "undefined") {
      return "dark";
    }
    const stored = window.localStorage.getItem(CANVAS_THEME_STORAGE_KEY);
    return stored === "light" ? "light" : "dark";
  });

  useEffect(() => {
    window.localStorage.setItem(CANVAS_THEME_STORAGE_KEY, theme);
  }, [theme]);

  return [theme, () => setTheme((current) => (current === "light" ? "dark" : "light"))];
}

function canvasEditorClasses(theme: CanvasTheme) {
  if (theme === "light") {
    return {
      monacoWrap: "overflow-hidden rounded-[24px] border border-paper-border bg-paper-0",
      monacoTheme: "vs" as const,
    };
  }
  return {
    monacoWrap: "overflow-hidden rounded-[24px] border border-shell-border bg-shell-1",
    monacoTheme: "vs-dark" as const,
  };
}

type ContentType = "markdown" | "python" | "typescript" | "javascript" | "html" | "json" | "text";
type Role = "user" | "assistant" | "system";
type Status = "idle" | "loading" | "streaming" | "error";

type ModelInfo = {
  id: string;
  label: string;
  provider: "openai" | "anthropic";
  available: boolean;
};

const SELECTED_MODEL_STORAGE_KEY = "workpad-selected-model";
const FALLBACK_MODELS: ModelInfo[] = [
  { id: "gpt-5.4", label: "GPT-5.4", provider: "openai", available: true },
  { id: "gpt-5.4-mini", label: "GPT-5.4 mini", provider: "openai", available: true },
  { id: "claude-opus-4-7", label: "Claude Opus 4.7", provider: "anthropic", available: true },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", provider: "anthropic", available: true },
];

type Message = {
  id: string;
  role: Role;
  content: string;
  created_at: string;
  isDraft?: boolean;
};

type SpecType = "rfc";

type CitationKind = "repo_range" | "repo_pr" | "repo_commit" | "transcript_range";
type ResolvedState = "live" | "stale" | "missing" | "unknown";

type Citation = {
  id: string;
  artifact_id: string;
  anchor: string;
  kind: CitationKind;
  target: Record<string, unknown>;
  resolved_state: ResolvedState;
  last_checked_at?: string | null;
  last_observed?: Record<string, unknown> | null;
};

type Artifact = {
  id: string;
  conversation_id: string;
  title: string;
  content: string;
  content_type: ContentType;
  version: number;
  updated_at: string;
  spec_type?: SpecType | null;
  citations?: Citation[];
  dirty?: boolean;
};

type DraftSpecPayload = {
  conversation_id?: string | null;
  transcript: string;
  repo: string;
  github_token?: string;
};

type DraftPhase = "idle" | "pass1" | "pass2" | "finalizing" | "completed" | "error";

type DraftState = {
  phase: DraftPhase;
  pickedPaths: string[];
  citationSummary: { valid: number; dropped: number; reasons: string[] } | null;
  artifactId: string | null;
  conversationId: string | null;
  error: { code: string; message: string } | null;
  startedAt: number | null;
};

const INITIAL_DRAFT_STATE: DraftState = {
  phase: "idle",
  pickedPaths: [],
  citationSummary: null,
  artifactId: null,
  conversationId: null,
  error: null,
  startedAt: null,
};

type VerifyPhase = "idle" | "verifying" | "success" | "error";

type VerifyState = {
  phase: VerifyPhase;
  counts: { live: number; stale: number; missing: number; unknown: number };
  truncated: boolean;
  remaining: number;
  error: { code: string; message: string } | null;
  lastArtifactId: string | null;
  lastRunAt: number | null;
};

const INITIAL_VERIFY_STATE: VerifyState = {
  phase: "idle",
  counts: { live: 0, stale: 0, missing: 0, unknown: 0 },
  truncated: false,
  remaining: 0,
  error: null,
  lastArtifactId: null,
  lastRunAt: null,
};

type ToastKind = "error" | "info" | "success";

type Toast = {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
};

type VerifyCitationsResponse = {
  artifact_id: string;
  counts: Partial<Record<"live" | "stale" | "missing" | "unknown", number>>;
  truncated: boolean;
  remaining: number;
  citations: Citation[];
};

type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string | null;
  artifact_count: number;
  archived_at?: string | null;
};

type ConversationDetail = {
  conversation: ConversationSummary;
  messages: Message[];
  artifacts: Artifact[];
  active_artifact_id?: string | null;
};

type WorkbenchStore = {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  messages: Message[];
  artifacts: Artifact[];
  activeArtifact: Artifact | null;
  composer: string;
  status: Status;
  error: string | null;
  bootstrapped: boolean;
  models: ModelInfo[];
  selectedModelId: string;
  showArchived: boolean;
  bootstrap: () => Promise<void>;
  startNewConversation: () => Promise<void>;
  selectConversation: (conversationId: string) => Promise<void>;
  setShowArchived: (value: boolean) => void;
  archiveConversation: (conversationId: string) => Promise<void>;
  unarchiveConversation: (conversationId: string) => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  setComposer: (value: string) => void;
  setSelectedModel: (modelId: string) => void;
  setActiveArtifactContent: (content: string) => void;
  setActiveArtifactTitle: (title: string) => void;
  persistActiveArtifact: () => Promise<void>;
  refreshActiveArtifact: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  regenerateLastAssistant: () => Promise<void>;
  editLastUserMessage: (message: string) => Promise<void>;
  draft: DraftState;
  draftSpec: (payload: DraftSpecPayload) => Promise<void>;
  resetDraft: () => void;
  verify: VerifyState;
  verifyActiveCitations: (options?: { force?: boolean }) => Promise<void>;
  toasts: Toast[];
  pushToast: (toast: Omit<Toast, "id"> & { id?: string }) => string;
  dismissToast: (id: string) => void;
};

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const turndown = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced" });
let artifactSaveRequestCounter = 0;

marked.setOptions({
  breaks: true,
  gfm: true,
});

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

function upsertConversation(list: ConversationSummary[], conversation: ConversationSummary): ConversationSummary[] {
  const next = [conversation, ...list.filter((item) => item.id !== conversation.id)];
  return next.sort((a, b) => new Date(b.updated_at).valueOf() - new Date(a.updated_at).valueOf());
}

function updateArtifactCollection(artifacts: Artifact[], artifact: Artifact): Artifact[] {
  return [artifact, ...artifacts.filter((item) => item.id !== artifact.id)];
}

function normalizeArtifact(artifact: Artifact): Artifact {
  return {
    ...artifact,
    citations: artifact.citations ?? [],
    spec_type: artifact.spec_type ?? null,
  };
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) {
    return fallback;
  }
  const match = header.match(/filename="?([^"]+)"?/i);
  return match?.[1] ?? fallback;
}

async function copyTextToClipboard(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

async function readSseStream(response: Response, onEvent: (event: Record<string, unknown>) => void): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming is not available in this browser.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const segments = buffer.split("\n\n");
    buffer = segments.pop() ?? "";

    for (const segment of segments) {
      const dataLine = segment
        .split("\n")
        .find((line) => line.startsWith("data: "));

      if (!dataLine) {
        continue;
      }

      const jsonPayload = dataLine.slice(6);
      if (!jsonPayload) {
        continue;
      }

      onEvent(JSON.parse(jsonPayload));
    }
  }
}

function loadStoredModelId(): string {
  if (typeof window === "undefined") {
    return FALLBACK_MODELS[0].id;
  }
  return window.localStorage.getItem(SELECTED_MODEL_STORAGE_KEY) ?? FALLBACK_MODELS[0].id;
}

type StoreGetter = () => WorkbenchStore;
type StoreSetter = (
  partial:
    | Partial<WorkbenchStore>
    | ((state: WorkbenchStore) => Partial<WorkbenchStore>),
) => void;

function upsertMessageInPlace(messages: Message[], incoming: Message): Message[] {
  const exists = messages.some((item) => item.id === incoming.id);
  if (exists) {
    return messages.map((item) => (item.id === incoming.id ? incoming : item));
  }
  return [...messages, incoming];
}

function buildStreamEventHandler(
  draftAssistantId: string,
  get: StoreGetter,
  set: StoreSetter,
) {
  return (event: Record<string, unknown>) => {
    const type = event.type as string;

    if (type === "conversation.created" && event.conversation) {
      const conversation = event.conversation as ConversationSummary;
      set({
        activeConversationId: conversation.id,
        conversations: upsertConversation(get().conversations, conversation),
      });
    }

    if (type === "user.message" && event.message) {
      const incoming = event.message as Message;
      set({ messages: upsertMessageInPlace(get().messages, incoming) });
    }

    if (type === "assistant.message.started") {
      const hasDraft = get().messages.some((item) => item.id === draftAssistantId);
      if (!hasDraft) {
        set({
          messages: [
            ...get().messages,
            {
              id: draftAssistantId,
              role: "assistant",
              content: "",
              created_at: new Date().toISOString(),
              isDraft: true,
            },
          ],
        });
      }
    }

    if (type === "assistant.message.delta") {
      const delta = String(event.delta ?? "");
      set({
        messages: get().messages.map((item) =>
          item.id === draftAssistantId ? { ...item, content: item.content + delta } : item,
        ),
      });
    }

    if (type === "artifact.started" && event.artifact) {
      const artifact = event.artifact as Artifact;
      set({
        activeArtifact: { ...artifact, content: "", dirty: false },
        artifacts: updateArtifactCollection(get().artifacts, { ...artifact, content: "", dirty: false }),
      });
    }

    if (type === "artifact.delta") {
      const delta = String(event.delta ?? "");
      const artifact = get().activeArtifact;
      if (!artifact) {
        return;
      }
      set({
        activeArtifact: { ...artifact, content: artifact.content + delta, dirty: false },
        artifacts: updateArtifactCollection(get().artifacts, { ...artifact, content: artifact.content + delta, dirty: false }),
      });
    }

    if (type === "artifact.completed" && event.artifact) {
      const artifact = event.artifact as Artifact;
      set({
        activeArtifact: { ...artifact, dirty: false },
        artifacts: updateArtifactCollection(get().artifacts, { ...artifact, dirty: false }),
      });
    }

    if (type === "artifact.draft.started" && event.draftId) {
      const draftId = String(event.draftId);
      const draft: Artifact = {
        id: draftId,
        conversation_id: get().activeConversationId ?? "",
        title: String(event.title ?? "Drafting…"),
        content: "",
        content_type: (event.content_type as ContentType) ?? "markdown",
        version: 0,
        updated_at: new Date().toISOString(),
        dirty: false,
      };
      set({ activeArtifact: draft });
    }

    if (type === "artifact.draft.delta" && event.draftId) {
      const draftId = String(event.draftId);
      const delta = String(event.delta ?? "");
      const artifact = get().activeArtifact;
      if (!artifact || artifact.id !== draftId) {
        return;
      }
      set({ activeArtifact: { ...artifact, content: artifact.content + delta, dirty: false } });
    }

    if (type === "artifact.draft.completed" && event.artifact) {
      const finalArtifact = event.artifact as Artifact;
      set({
        activeArtifact: { ...finalArtifact, dirty: false },
        artifacts: updateArtifactCollection(get().artifacts, { ...finalArtifact, dirty: false }),
      });
    }

    if (type === "assistant.message.completed" && event.message) {
      const messagePayload = event.message as Message;
      set({
        messages: [
          ...get().messages.filter((item) => item.id !== draftAssistantId && item.id !== messagePayload.id),
          messagePayload,
        ],
      });
    }

    if (type === "conversation.updated" && event.conversation) {
      const conversation = event.conversation as ConversationSummary;
      set({ conversations: upsertConversation(get().conversations, conversation) });
    }

    if (type === "error") {
      set({ status: "error", error: String(event.message ?? "An unknown error occurred.") });
    }
  };
}

function currentArtifactRequestPayload(artifact: Artifact | null) {
  if (!artifact) {
    return null;
  }
  return {
    id: artifact.id,
    title: artifact.title,
    content: artifact.content,
    content_type: artifact.content_type,
    version: artifact.version,
  };
}

const useWorkbenchStore = create<WorkbenchStore>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  artifacts: [],
  activeArtifact: null,
  composer: "",
  status: "loading",
  error: null,
  bootstrapped: false,
  models: FALLBACK_MODELS,
  selectedModelId: loadStoredModelId(),
  showArchived: false,

  async bootstrap() {
    set({ status: "loading", error: null });
    try {
      const includeArchived = get().showArchived;
      const [conversations, models] = await Promise.all([
        requestJson<ConversationSummary[]>(`/api/conversations?include_archived=${includeArchived}`),
        requestJson<ModelInfo[]>("/api/models").catch(() => FALLBACK_MODELS),
      ]);
      const resolvedModels = models.length > 0 ? models : FALLBACK_MODELS;
      const current = get().selectedModelId;
      const preferred = resolvedModels.find((item) => item.id === current && item.available);
      const fallback = preferred ?? resolvedModels.find((item) => item.available) ?? resolvedModels[0];
      set({
        conversations,
        models: resolvedModels,
        selectedModelId: fallback.id,
        bootstrapped: true,
        status: "idle",
      });
      if (typeof window !== "undefined") {
        window.localStorage.setItem(SELECTED_MODEL_STORAGE_KEY, fallback.id);
      }
      if (conversations[0]) {
        await get().selectConversation(conversations[0].id);
      }
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "Could not load the workspace.",
        bootstrapped: true,
      });
    }
  },

  async startNewConversation() {
    const conversation = await requestJson<ConversationSummary>("/api/conversations", { method: "POST" });
    set({
      conversations: upsertConversation(get().conversations, conversation),
      activeConversationId: conversation.id,
      messages: [],
      artifacts: [],
      activeArtifact: null,
      composer: "",
      status: "idle",
      error: null,
    });
  },

  async selectConversation(conversationId: string) {
    set({ status: "loading", error: null });
    try {
      const detail = await requestJson<ConversationDetail>(`/api/conversations/${conversationId}`);
      const normalizedArtifacts = detail.artifacts.map(normalizeArtifact);
      const activeArtifact =
        normalizedArtifacts.find((artifact) => artifact.id === detail.active_artifact_id) ??
        normalizedArtifacts[0] ??
        null;
      set({
        activeConversationId: conversationId,
        conversations: upsertConversation(get().conversations, detail.conversation),
        messages: detail.messages,
        artifacts: normalizedArtifacts,
        activeArtifact,
        status: "idle",
      });
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "Could not load that conversation.",
      });
    }
  },

  async setShowArchived(value) {
    set({ showArchived: value });
    try {
      const conversations = await requestJson<ConversationSummary[]>(
        `/api/conversations?include_archived=${value}`,
      );
      set({ conversations });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not load conversations." });
    }
  },

  async archiveConversation(conversationId) {
    try {
      const updated = await requestJson<ConversationSummary>(
        `/api/conversations/${conversationId}/archive`,
        { method: "POST" },
      );
      const keep = get().showArchived;
      set((state) => ({
        conversations: keep
          ? upsertConversation(state.conversations, updated)
          : state.conversations.filter((item) => item.id !== conversationId),
        activeConversationId: state.activeConversationId === conversationId && !keep ? null : state.activeConversationId,
        messages: state.activeConversationId === conversationId && !keep ? [] : state.messages,
        artifacts: state.activeConversationId === conversationId && !keep ? [] : state.artifacts,
        activeArtifact: state.activeConversationId === conversationId && !keep ? null : state.activeArtifact,
        error: null,
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not archive conversation." });
    }
  },

  async unarchiveConversation(conversationId) {
    try {
      const updated = await requestJson<ConversationSummary>(
        `/api/conversations/${conversationId}/unarchive`,
        { method: "POST" },
      );
      set((state) => ({
        conversations: upsertConversation(state.conversations, updated),
        error: null,
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not unarchive conversation." });
    }
  },

  async deleteConversation(conversationId) {
    try {
      const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      set((state) => {
        const isActive = state.activeConversationId === conversationId;
        return {
          conversations: state.conversations.filter((item) => item.id !== conversationId),
          activeConversationId: isActive ? null : state.activeConversationId,
          messages: isActive ? [] : state.messages,
          artifacts: isActive ? [] : state.artifacts,
          activeArtifact: isActive ? null : state.activeArtifact,
          error: null,
        };
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not delete conversation." });
    }
  },

  setComposer(value) {
    set({ composer: value });
  },

  setSelectedModel(modelId) {
    set({ selectedModelId: modelId });
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SELECTED_MODEL_STORAGE_KEY, modelId);
    }
  },

  setActiveArtifactContent(content) {
    const current = get().activeArtifact;
    if (!current || current.content === content) {
      return;
    }
    set({
      activeArtifact: { ...current, content, dirty: true },
      artifacts: get().artifacts.map((artifact) =>
        artifact.id === current.id ? { ...artifact, content, dirty: true } : artifact,
      ),
    });
  },

  setActiveArtifactTitle(title) {
    const current = get().activeArtifact;
    if (!current || current.title === title) {
      return;
    }
    set({
      activeArtifact: { ...current, title, dirty: true },
      artifacts: get().artifacts.map((artifact) =>
        artifact.id === current.id ? { ...artifact, title, dirty: true } : artifact,
      ),
    });
  },

  async persistActiveArtifact() {
    const artifact = get().activeArtifact;
    if (!artifact?.dirty) {
      return;
    }

    const snapshot = {
      id: artifact.id,
      title: artifact.title,
      content: artifact.content,
      content_type: artifact.content_type,
      version: artifact.version,
    };
    const saveRequestId = ++artifactSaveRequestCounter;

    try {
      const next = normalizeArtifact(
        await requestJson<Artifact>(`/api/artifacts/${snapshot.id}`, {
          method: "PUT",
          body: JSON.stringify({
            title: snapshot.title,
            content: snapshot.content,
            content_type: snapshot.content_type,
            expected_version: snapshot.version,
          }),
        }),
      );

      set((state) => {
        const current = state.activeArtifact;
        if (!current || current.id !== next.id) {
          return {};
        }

        const isLatestSave = saveRequestId === artifactSaveRequestCounter;
        const snapshotStillCurrent =
          current.title === snapshot.title &&
          current.content === snapshot.content &&
          current.content_type === snapshot.content_type;

        const mergedActiveArtifact = snapshotStillCurrent
          ? { ...next, dirty: false }
          : {
              ...current,
              version: next.version,
              updated_at: next.updated_at,
              conversation_id: next.conversation_id,
              dirty: true,
            };

        return {
          activeArtifact: mergedActiveArtifact,
          artifacts: updateArtifactCollection(
            state.artifacts,
            snapshotStillCurrent
              ? { ...next, dirty: false }
              : {
                  ...current,
                  version: next.version,
                  updated_at: next.updated_at,
                  conversation_id: next.conversation_id,
                  dirty: true,
                },
          ),
          conversations: isLatestSave
            ? state.conversations.map((item) =>
                item.id === next.conversation_id ? { ...item, updated_at: next.updated_at } : item,
              )
            : state.conversations,
          error: null,
        };
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Autosave failed.",
      });
    }
  },

  async refreshActiveArtifact() {
    const current = get().activeArtifact;
    if (!current) {
      return;
    }
    try {
      const next = normalizeArtifact(await requestJson<Artifact>(`/api/artifacts/${current.id}`));
      set({
        activeArtifact: { ...next, dirty: false },
        artifacts: updateArtifactCollection(get().artifacts, { ...next, dirty: false }),
        error: null,
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not refresh the workpad." });
    }
  },

  async sendMessage(message) {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }

    set({ composer: "", status: "streaming", error: null });
    const draftAssistantId = `draft-${crypto.randomUUID()}`;

    try {
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: get().activeConversationId,
          message: trimmed,
          model: get().selectedModelId,
          current_artifact: currentArtifactRequestPayload(get().activeArtifact),
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      await readSseStream(response, buildStreamEventHandler(draftAssistantId, get, set));

      if (get().status !== "error") {
        set({ status: "idle" });
      }
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "The request failed.",
      });
    }
  },

  async regenerateLastAssistant() {
    const conversationId = get().activeConversationId;
    if (!conversationId) {
      return;
    }
    const messages = get().messages;
    const lastUserIdx = findLastIndex(messages, (m) => m.role === "user");
    if (lastUserIdx < 0) {
      return;
    }

    set({
      messages: messages.slice(0, lastUserIdx + 1),
      status: "streaming",
      error: null,
    });
    const draftAssistantId = `draft-${crypto.randomUUID()}`;

    try {
      const response = await fetch(`${API_BASE}/api/chat/regenerate`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          model: get().selectedModelId,
          current_artifact: currentArtifactRequestPayload(get().activeArtifact),
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      await readSseStream(response, buildStreamEventHandler(draftAssistantId, get, set));

      if (get().status !== "error") {
        set({ status: "idle" });
      }
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "Could not regenerate.",
      });
    }
  },

  async editLastUserMessage(message) {
    const trimmed = message.trim();
    const conversationId = get().activeConversationId;
    if (!trimmed || !conversationId) {
      return;
    }
    const messages = get().messages;
    const lastUserIdx = findLastIndex(messages, (m) => m.role === "user");
    if (lastUserIdx < 0) {
      return;
    }

    const trimmedMessages = messages
      .slice(0, lastUserIdx + 1)
      .map((item, index) => (index === lastUserIdx ? { ...item, content: trimmed } : item));
    set({ messages: trimmedMessages, status: "streaming", error: null });
    const draftAssistantId = `draft-${crypto.randomUUID()}`;

    try {
      const response = await fetch(`${API_BASE}/api/chat/edit-last-user`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: trimmed,
          model: get().selectedModelId,
          current_artifact: currentArtifactRequestPayload(get().activeArtifact),
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      await readSseStream(response, buildStreamEventHandler(draftAssistantId, get, set));

      if (get().status !== "error") {
        set({ status: "idle" });
      }
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "Could not rerun the edited message.",
      });
    }
  },

  draft: INITIAL_DRAFT_STATE,

  resetDraft() {
    set({ draft: INITIAL_DRAFT_STATE });
  },

  async draftSpec(payload: DraftSpecPayload) {
    set({
      draft: {
        ...INITIAL_DRAFT_STATE,
        phase: "pass1",
        startedAt: Date.now(),
      },
    });

    try {
      const response = await fetch(`${API_BASE}/api/specs/draft`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Draft request failed with status ${response.status}`);
      }

      let lastArtifactId: string | null = null;
      let lastConversationId: string | null = null;

      await readSseStream(response, (event) => {
        const type = event.type as string | undefined;
        switch (type) {
          case "draft.pass1.started":
            set((state) => ({ draft: { ...state.draft, phase: "pass1" } }));
            break;
          case "draft.pass1.completed": {
            const paths = Array.isArray(event.picked_paths) ? (event.picked_paths as string[]) : [];
            set((state) => ({ draft: { ...state.draft, pickedPaths: paths } }));
            break;
          }
          case "draft.pass2.started":
            set((state) => ({ draft: { ...state.draft, phase: "pass2" } }));
            break;
          case "draft.citations":
            set((state) => ({
              draft: {
                ...state.draft,
                phase: "finalizing",
                citationSummary: {
                  valid: Number(event.valid ?? 0),
                  dropped: Number(event.dropped ?? 0),
                  reasons: Array.isArray(event.dropped_reasons)
                    ? (event.dropped_reasons as string[])
                    : [],
                },
              },
            }));
            break;
          case "artifact.created": {
            lastArtifactId = typeof event.artifact_id === "string" ? event.artifact_id : null;
            lastConversationId =
              typeof event.conversation_id === "string" ? event.conversation_id : null;
            set((state) => ({
              draft: {
                ...state.draft,
                artifactId: lastArtifactId,
                conversationId: lastConversationId,
              },
            }));
            break;
          }
          case "stream.completed":
            set((state) => ({ draft: { ...state.draft, phase: "completed" } }));
            break;
          case "error": {
            const code = typeof event.code === "string" ? event.code : "unexpected";
            const message = typeof event.message === "string" ? event.message : "Draft failed";
            set((state) => ({
              draft: { ...state.draft, phase: "error", error: { code, message } },
            }));
            break;
          }
          default:
            break;
        }
      });

      if (lastConversationId) {
        await get().selectConversation(lastConversationId);
      }
    } catch (error) {
      set((state) => ({
        draft: {
          ...state.draft,
          phase: "error",
          error: {
            code: "network",
            message: error instanceof Error ? error.message : "Draft request failed.",
          },
        },
      }));
    }
  },

  verify: INITIAL_VERIFY_STATE,

  async verifyActiveCitations(options?: { force?: boolean }) {
    const artifact = get().activeArtifact;
    if (!artifact) {
      return;
    }
    const query = options?.force ? "?force=true" : "";
    set((state) => ({
      verify: { ...state.verify, phase: "verifying", error: null },
    }));

    try {
      const result = await requestJson<VerifyCitationsResponse>(
        `/api/artifacts/${artifact.id}/verify-citations${query}`,
        { method: "POST" },
      );

      set((state) => {
        const counts = {
          live: Number(result.counts.live ?? 0),
          stale: Number(result.counts.stale ?? 0),
          missing: Number(result.counts.missing ?? 0),
          unknown: Number(result.counts.unknown ?? 0),
        };
        const verify: VerifyState = {
          phase: "success",
          counts,
          truncated: Boolean(result.truncated),
          remaining: Number(result.remaining ?? 0),
          error: null,
          lastArtifactId: result.artifact_id,
          lastRunAt: Date.now(),
        };

        if (!state.activeArtifact || state.activeArtifact.id !== result.artifact_id) {
          return { verify };
        }

        const nextArtifact: Artifact = {
          ...state.activeArtifact,
          citations: result.citations,
        };
        return {
          verify,
          activeArtifact: nextArtifact,
          artifacts: updateArtifactCollection(state.artifacts, nextArtifact),
        };
      });
    } catch (error) {
      set((state) => ({
        verify: {
          ...state.verify,
          phase: "error",
          error: {
            code: "network",
            message: error instanceof Error ? error.message : "Verify request failed.",
          },
        },
      }));
    }
  },

  toasts: [],

  pushToast(toast) {
    const id = toast.id ?? `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const item: Toast = {
      id,
      kind: toast.kind,
      title: toast.title,
      description: toast.description,
    };
    set((state) => ({
      toasts: [
        ...state.toasts.filter((existing) => existing.id !== id),
        item,
      ],
    }));
    return id;
  },

  dismissToast(id) {
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    }));
  },
}));

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) {
      return index;
    }
  }
  return -1;
}

type StickyScrollController = {
  containerRef: React.MutableRefObject<HTMLDivElement | null>;
  contentRef: React.MutableRefObject<HTMLDivElement | null>;
  onScroll: (event: React.UIEvent<HTMLDivElement>) => void;
  scrollToBottom: () => void;
  scrollToTop: () => void;
  showJump: boolean;
  showJumpTop: boolean;
};

/**
 * Keep a scrollable <div> pinned to its own bottom while new content arrives —
 * the classic "stick to bottom unless the user scrolled up" chat pattern.
 *
 * Consumers attach ``containerRef`` to the scrolling element and
 * ``contentRef`` to the growing child inside it. The hook watches the content
 * via ``ResizeObserver`` so layout shifts that happen *after* render (syntax
 * highlighting, katex, image loads) still keep us pinned. ``onScroll`` reads
 * distance-from-bottom to decide whether the user has scrolled away; a
 * ``programmaticScrollRef`` guard ignores scroll events that come from our own
 * ``scrollToBottom`` call so we never self-toggle the sticky flag.
 */
function useStickyScroll(threshold: number = 96): StickyScrollController {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const stickyRef = useRef(true);
  const programmaticScrollRef = useRef(false);
  const [showJump, setShowJump] = useState(false);
  const [showJumpTop, setShowJumpTop] = useState(false);

  const syncJumpButtons = useCallback(
    (element: HTMLElement) => {
      const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
      const distanceFromTop = element.scrollTop;
      const canScroll = element.scrollHeight > element.clientHeight;
      const farFromBottom = canScroll && distanceFromBottom > threshold;
      const farFromTop = canScroll && distanceFromTop > threshold;
      setShowJump((previous) => (previous === farFromBottom ? previous : farFromBottom));
      setShowJumpTop((previous) => (previous === farFromTop ? previous : farFromTop));
    },
    [threshold],
  );

  const pinToBottom = useCallback(() => {
    const element = containerRef.current;
    if (!element) return;
    // Skip when there's nothing to scroll; prevents spurious scroll events
    // from our own write while content is still mounting.
    if (element.scrollHeight <= element.clientHeight) return;
    programmaticScrollRef.current = true;
    element.scrollTop = element.scrollHeight;
    // Release the guard on the next frame — the native "scroll" event from
    // our write is delivered before the frame ends.
    window.requestAnimationFrame(() => {
      programmaticScrollRef.current = false;
    });
  }, []);

  // Pin after every React render when the sticky flag is engaged. This
  // catches new messages, deltas, and any DOM structure changes driven by
  // state updates.
  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    if (stickyRef.current) pinToBottom();
    syncJumpButtons(element);
  });

  // Also pin when the content grows without a React re-render — things like
  // highlight.js applying classes, katex laying out math, images loading.
  useEffect(() => {
    const node = contentRef.current;
    const container = containerRef.current;
    if (!node || !container) return;
    const observer = new ResizeObserver(() => {
      if (stickyRef.current) pinToBottom();
      syncJumpButtons(container);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [pinToBottom, syncJumpButtons]);

  const onScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (programmaticScrollRef.current) return;
      const element = event.currentTarget;
      const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
      const near = distanceFromBottom < threshold;
      stickyRef.current = near;
      syncJumpButtons(element);
    },
    [syncJumpButtons, threshold],
  );

  const scrollToBottom = useCallback(() => {
    stickyRef.current = true;
    pinToBottom();
    const element = containerRef.current;
    if (element) syncJumpButtons(element);
  }, [pinToBottom, syncJumpButtons]);

  const scrollToTop = useCallback(() => {
    const element = containerRef.current;
    if (!element) return;
    // Disengage sticky so streaming deltas don't yank us back down while
    // the user is reading the top of the document.
    stickyRef.current = false;
    programmaticScrollRef.current = true;
    element.scrollTop = 0;
    window.requestAnimationFrame(() => {
      programmaticScrollRef.current = false;
    });
    syncJumpButtons(element);
  }, [syncJumpButtons]);

  return {
    containerRef,
    contentRef,
    onScroll,
    scrollToBottom,
    scrollToTop,
    showJump,
    showJumpTop,
  };
}

function ScrollJumpButton({
  direction,
  onClick,
  label,
  className = "",
}: {
  direction: "up" | "down";
  onClick: () => void;
  label?: string;
  className?: string;
}) {
  const defaultLabel = direction === "up" ? "Jump to top" : "Jump to latest";
  const finalLabel = label ?? defaultLabel;
  const Icon = direction === "up" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={finalLabel}
      title={finalLabel}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-full border border-shell-border bg-shell-1 text-slate-100 shadow-panel backdrop-blur transition hover:border-shell-border-strong hover:bg-shell-2 ${className}`}
    >
      <Icon size={16} />
    </button>
  );
}

function ChatScrollRegion({ emptyState }: { emptyState?: React.ReactNode }) {
  const messages = useWorkbenchStore((state) => state.messages);
  const sticky = useStickyScroll();

  if (messages.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={sticky.containerRef}
        onScroll={sticky.onScroll}
        className="h-full overflow-auto pr-2"
      >
        <div ref={sticky.contentRef} className="mx-auto max-w-4xl space-y-6">
          {renderMessageList(messages)}
        </div>
      </div>
      {sticky.showJump ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
          <ScrollJumpButton
            direction="down"
            onClick={sticky.scrollToBottom}
            className="pointer-events-auto"
          />
        </div>
      ) : null}
    </div>
  );
}

function renderMessageList(messages: Message[]) {
  const lastUserIdx = findLastIndex(messages, (m) => m.role === "user");
  const lastAssistantIdx = findLastIndex(messages, (m) => m.role === "assistant" && !m.isDraft);
  return messages.map((message, index) => (
    <MessageRow
      key={message.id}
      message={message}
      isLastUser={index === lastUserIdx}
      isLastAssistant={index === lastAssistantIdx}
    />
  ));
}

function useAutosave() {
  const artifact = useWorkbenchStore((state) => state.activeArtifact);
  const status = useWorkbenchStore((state) => state.status);
  const persistActiveArtifact = useWorkbenchStore((state) => state.persistActiveArtifact);

  useEffect(() => {
    if (!artifact?.dirty || status === "streaming") {
      return;
    }
    const timer = window.setTimeout(() => {
      void persistActiveArtifact();
    }, 900);
    return () => window.clearTimeout(timer);
  }, [artifact?.id, artifact?.title, artifact?.content, artifact?.content_type, artifact?.version, artifact?.dirty, status, persistActiveArtifact]);
}

function useErrorToasts() {
  const draftError = useWorkbenchStore((state) => state.draft.error);
  const verifyError = useWorkbenchStore((state) => state.verify.error);
  const pushToast = useWorkbenchStore((state) => state.pushToast);
  const lastDraftRef = useRef<string | null>(null);
  const lastVerifyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!draftError) {
      lastDraftRef.current = null;
      return;
    }
    const key = `${draftError.code}::${draftError.message}`;
    if (lastDraftRef.current === key) return;
    lastDraftRef.current = key;
    pushToast({
      id: "draft-error",
      kind: "error",
      title: `Draft failed · ${draftError.code}`,
      description: draftError.message,
    });
  }, [draftError, pushToast]);

  useEffect(() => {
    if (!verifyError) {
      lastVerifyRef.current = null;
      return;
    }
    const key = `${verifyError.code}::${verifyError.message}`;
    if (lastVerifyRef.current === key) return;
    lastVerifyRef.current = key;
    pushToast({
      id: "verify-error",
      kind: "error",
      title: `Verify failed · ${verifyError.code}`,
      description: verifyError.message,
    });
  }, [verifyError, pushToast]);
}

function Toaster() {
  const toasts = useWorkbenchStore((state) => state.toasts);
  const dismissToast = useWorkbenchStore((state) => state.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-full max-w-sm flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto rounded-2xl border px-4 py-3 text-sm shadow-panel backdrop-blur-xl ${
            toast.kind === "error"
              ? "border-rose-400/30 bg-rose-500/15 text-rose-50"
              : toast.kind === "success"
                ? "border-emerald-400/30 bg-emerald-500/15 text-emerald-50"
                : "border-shell-border bg-shell-1 text-slate-100"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium">{toast.title}</div>
              {toast.description ? (
                <div className="mt-1 text-xs opacity-80">{toast.description}</div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="-mr-1 -mt-1 rounded-full p-1 opacity-60 transition hover:opacity-100"
              aria-label="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function useAutoVerifyCitations() {
  const activeArtifactId = useWorkbenchStore((state) => state.activeArtifact?.id ?? null);
  const specType = useWorkbenchStore((state) => state.activeArtifact?.spec_type ?? null);
  const citationCount = useWorkbenchStore(
    (state) => state.activeArtifact?.citations?.length ?? 0,
  );
  const lastVerifiedId = useWorkbenchStore((state) => state.verify.lastArtifactId);
  const verifyActiveCitations = useWorkbenchStore((state) => state.verifyActiveCitations);

  useEffect(() => {
    if (!activeArtifactId) return;
    if (!specType || citationCount === 0) return;
    if (lastVerifiedId === activeArtifactId) return;
    void verifyActiveCitations();
  }, [activeArtifactId, specType, citationCount, lastVerifiedId, verifyActiveCitations]);
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

const CITATION_TOKEN_RE = /\[\[cite:([a-z0-9_-]{2,32})\]\]/gi;

function replaceCitationTokensWithSpans(markdown: string): string {
  return markdown.replace(
    CITATION_TOKEN_RE,
    (_match, anchor) => `<span data-cite="${String(anchor).toLowerCase()}"></span>`,
  );
}

function markdownToHtml(value: string): string {
  const withSpans = replaceCitationTokensWithSpans(value || "");
  const parsed = marked.parse(withSpans);
  const raw = typeof parsed === "string" ? parsed : "";
  return DOMPurify.sanitize(raw, { ADD_ATTR: ["data-cite"] });
}

// TipTap's TaskList / TaskItem extensions parse a very specific HTML shape
// (<ul data-type="taskList"><li data-type="taskItem" data-checked="…">). The
// GFM task list HTML that `marked` produces is a plain <ul><li> with an
// <input type="checkbox"> child. This helper walks the sanitized preview
// HTML and rewrites any list containing checkbox inputs into TipTap's shape
// so the editor can render real task items instead of silently dropping the
// inputs through its strict schema.
function rewriteTaskListsForTiptap(html: string): string {
  if (typeof window === "undefined" || !html.includes('type="checkbox"')) {
    return html;
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div id="__root">${html}</div>`, "text/html");
  const root = doc.getElementById("__root");
  if (!root) return html;

  root.querySelectorAll("ul").forEach((ul) => {
    const items = Array.from(ul.children).filter(
      (child): child is HTMLLIElement => child.tagName === "LI",
    );
    const hasCheckbox = items.some((li) => li.querySelector('input[type="checkbox"]'));
    if (!hasCheckbox) return;

    ul.setAttribute("data-type", "taskList");
    items.forEach((li) => {
      const checkbox = li.querySelector('input[type="checkbox"]');
      if (!checkbox) {
        // Mixed list — leave non-task bullets as regular list items.
        return;
      }
      const checked = checkbox.hasAttribute("checked");
      checkbox.remove();
      li.setAttribute("data-type", "taskItem");
      li.setAttribute("data-checked", checked ? "true" : "false");

      // TipTap's task item expects block content inside. Wrap trailing
      // inline content in a <p> if it isn't already a block.
      const hasBlockChild = Array.from(li.children).some((child) =>
        ["P", "UL", "OL", "PRE", "BLOCKQUOTE", "H1", "H2", "H3", "H4", "H5", "H6"].includes(
          child.tagName,
        ),
      );
      if (!hasBlockChild) {
        const paragraph = doc.createElement("p");
        // Move trailing whitespace/text/inline nodes into <p>.
        while (li.firstChild) {
          paragraph.appendChild(li.firstChild);
        }
        li.appendChild(paragraph);
      }
    });
  });

  return root.innerHTML;
}

function markdownToTiptapHtml(value: string): string {
  return rewriteTaskListsForTiptap(markdownToHtml(value));
}

turndown.addRule("workpad-citation", {
  filter: (node) =>
    node.nodeName === "SPAN" &&
    (node as HTMLElement).hasAttribute?.("data-cite"),
  replacement: (_content, node) => {
    const anchor = (node as HTMLElement).getAttribute("data-cite") ?? "";
    return anchor ? `[[cite:${anchor}]]` : "";
  },
});

// TipTap emits task items as <li data-type="taskItem" data-checked="…"> with
// a <p> inside. Turndown's default list rule renders them as plain bullets;
// override so round-tripped markdown keeps the checkbox syntax.
turndown.addRule("workpad-task-item", {
  filter: (node) =>
    node.nodeName === "LI" &&
    (node as HTMLElement).getAttribute?.("data-type") === "taskItem",
  replacement: (content, node) => {
    const checked = (node as HTMLElement).getAttribute("data-checked") === "true";
    const body = content.replace(/^\n+|\n+$/g, "").replace(/\n+/g, " ");
    return `- [${checked ? "x" : " "}] ${body}\n`;
  },
});

function iconForCitationKind(kind: CitationKind) {
  switch (kind) {
    case "repo_pr":
      return <GitPullRequest size={12} />;
    case "repo_commit":
      return <GitCommit size={12} />;
    case "transcript_range":
      return <Mic size={12} />;
    case "repo_range":
    default:
      return <FileText size={12} />;
  }
}

function citationPillLabel(citation: Citation | null, anchor: string): string {
  if (!citation) {
    return anchor;
  }
  const target = citation.target ?? {};
  switch (citation.kind) {
    case "repo_range": {
      const path = String(target.path ?? "");
      const start = target.line_start;
      const end = target.line_end;
      const basename = path.split("/").pop() || path;
      if (typeof start === "number" && typeof end === "number") {
        return start === end ? `${basename}:${start}` : `${basename}:${start}-${end}`;
      }
      return basename || anchor;
    }
    case "repo_pr": {
      const number = target.number;
      return typeof number === "number" ? `PR #${number}` : anchor;
    }
    case "repo_commit": {
      const sha = String(target.sha ?? "");
      return sha ? `commit ${sha.slice(0, 7)}` : anchor;
    }
    case "transcript_range": {
      const start = String(target.start ?? "");
      return start ? `transcript ${start}` : anchor;
    }
    default:
      return anchor;
  }
}

function citationStateModifier(state: ResolvedState | null): string {
  switch (state) {
    case "stale":
      return "workpad-citation--stale";
    case "missing":
      return "workpad-citation--missing";
    default:
      return "";
  }
}

function githubUrlForCitation(citation: Citation): string | null {
  const target = citation.target ?? {};
  const observed = citation.last_observed ?? {};
  switch (citation.kind) {
    case "repo_range": {
      const repo = String(target.repo ?? "");
      const path = String(target.path ?? "");
      const ref =
        (observed.at_ref as string | undefined) ||
        (target.ref_at_draft as string | undefined) ||
        "";
      const suggested = observed.suggested_range as
        | { line_start?: number; line_end?: number }
        | undefined;
      const ls = suggested?.line_start ?? (target.line_start as number | undefined);
      const le = suggested?.line_end ?? (target.line_end as number | undefined);
      if (!repo || !path || !ref) return null;
      const anchor = ls && le ? `#L${ls}-L${le}` : "";
      return `https://github.com/${repo}/blob/${ref}/${path}${anchor}`;
    }
    case "repo_pr": {
      const url = observed.html_url as string | undefined;
      if (url) return url;
      const repo = String(target.repo ?? "");
      const number = target.number as number | undefined;
      return repo && number ? `https://github.com/${repo}/pull/${number}` : null;
    }
    case "repo_commit": {
      const url = observed.html_url as string | undefined;
      if (url) return url;
      const repo = String(target.repo ?? "");
      const sha = String(target.sha ?? "");
      return repo && sha ? `https://github.com/${repo}/commit/${sha}` : null;
    }
    default:
      return null;
  }
}

type PreviewLine = { line: number; text: string; highlighted: boolean };
type PreviewData =
  | {
      kind: "repo_range";
      at_ref: string;
      path: string;
      target_start: number;
      target_end: number;
      context_start: number;
      context_end: number;
      lines: PreviewLine[];
    }
  | { kind: "repo_pr"; repo: string; number: number; title: string; state: string; merged: boolean; html_url: string }
  | { kind: "repo_commit"; repo: string; sha: string; message: string; html_url: string }
  | { kind: "transcript_range"; start: string | null; end: string | null };

// Session-level cache so reopening a popover doesn't refetch and repeated
// hovers across the same spec are instant. Cleared on reload by design.
const citationPreviewCache = new Map<string, PreviewData>();
const citationPreviewInflight = new Map<string, Promise<PreviewData | null>>();

async function fetchCitationPreview(citationId: string): Promise<PreviewData | null> {
  const cached = citationPreviewCache.get(citationId);
  if (cached) return cached;
  const inflight = citationPreviewInflight.get(citationId);
  if (inflight) return inflight;

  const promise = (async () => {
    try {
      const data = await requestJson<PreviewData>(`/api/citations/${citationId}/preview`);
      citationPreviewCache.set(citationId, data);
      return data;
    } catch {
      return null;
    } finally {
      citationPreviewInflight.delete(citationId);
    }
  })();

  citationPreviewInflight.set(citationId, promise);
  return promise;
}

function useCitationPreview(citationId: string | null | undefined, enabled: boolean) {
  const [state, setState] = useState<{
    data: PreviewData | null;
    loading: boolean;
    error: string | null;
  }>({ data: null, loading: false, error: null });

  useEffect(() => {
    if (!enabled || !citationId) return;
    const cached = citationPreviewCache.get(citationId);
    if (cached) {
      setState({ data: cached, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    fetchCitationPreview(citationId)
      .then((data) => {
        if (cancelled) return;
        if (data) {
          setState({ data, loading: false, error: null });
        } else {
          setState({ data: null, loading: false, error: "Preview unavailable." });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : "Preview failed.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, citationId]);

  return state;
}

type DiffData = {
  citation_id: string;
  kind: "repo_range";
  path: string;
  pinned_ref: string;
  head_ref: string;
  pinned_range: { line_start: number; line_end: number };
  head_range: { line_start: number; line_end: number };
  pinned_lines: { line: number; text: string }[];
  head_lines: { line: number; text: string }[];
  unified_diff: string;
};

const citationDiffCache = new Map<string, DiffData>();
const citationDiffInflight = new Map<string, Promise<DiffData | null>>();

async function fetchCitationDiff(citationId: string): Promise<DiffData | null> {
  const cached = citationDiffCache.get(citationId);
  if (cached) return cached;
  const inflight = citationDiffInflight.get(citationId);
  if (inflight) return inflight;
  const promise = (async () => {
    try {
      const data = await requestJson<DiffData>(`/api/citations/${citationId}/diff`);
      citationDiffCache.set(citationId, data);
      return data;
    } catch {
      return null;
    } finally {
      citationDiffInflight.delete(citationId);
    }
  })();
  citationDiffInflight.set(citationId, promise);
  return promise;
}

function CitationDiffPane({ citationId }: { citationId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [state, setState] = useState<{
    data: DiffData | null;
    loading: boolean;
    error: string | null;
  }>({ data: null, loading: false, error: null });

  useEffect(() => {
    if (!expanded) return;
    const cached = citationDiffCache.get(citationId);
    if (cached) {
      setState({ data: cached, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ data: null, loading: true, error: null });
    fetchCitationDiff(citationId)
      .then((data) => {
        if (cancelled) return;
        if (data) {
          setState({ data, loading: false, error: null });
        } else {
          setState({ data: null, loading: false, error: "Diff unavailable." });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : "Diff failed.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [expanded, citationId]);

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="inline-flex items-center gap-1 rounded-full border border-amber-400/20 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-100 hover:border-amber-300/40 hover:bg-amber-500/20"
      >
        <ChevronDown
          size={12}
          className={`transition-transform ${expanded ? "rotate-180" : ""}`}
        />
        {expanded ? "Hide diff" : "View diff"}
      </button>
      {expanded ? (
        <div className="mt-2 rounded-xl border border-shell-border bg-shell-1 p-2">
          {state.loading ? (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <LoaderCircle size={12} className="animate-spin" /> Loading diff…
            </div>
          ) : state.error ? (
            <div className="text-xs text-rose-200">{state.error}</div>
          ) : state.data && state.data.unified_diff ? (
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px]">
              {state.data.unified_diff.split("\n").map((line, index) => {
                const color = line.startsWith("+")
                  ? "text-emerald-200"
                  : line.startsWith("-")
                    ? "text-rose-200"
                    : line.startsWith("@@")
                      ? "text-sky-200"
                      : "text-slate-300";
                return (
                  <div key={index} className={color}>
                    {line || " "}
                  </div>
                );
              })}
            </pre>
          ) : (
            <div className="text-xs text-slate-400">
              No textual diff produced (content moved but slice is identical).
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function CitationPreviewPane({ citationId }: { citationId: string }) {
  const { data, loading, error } = useCitationPreview(citationId, true);

  if (loading) {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-xl border border-shell-border bg-shell-1 px-3 py-2 text-xs text-slate-400">
        <LoaderCircle size={12} className="animate-spin" /> Loading preview…
      </div>
    );
  }
  if (error) {
    return (
      <div className="mt-3 rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
        {error}
      </div>
    );
  }
  if (!data) return null;

  if (data.kind === "repo_range") {
    return (
      <div className="mt-3 rounded-xl border border-shell-border bg-shell-1 p-2 font-mono text-[11px] text-slate-200">
        {data.lines.map((line) => (
          <div
            key={line.line}
            className={`flex gap-3 ${
              line.highlighted ? "bg-sky-400/10 text-sky-50" : ""
            }`}
          >
            <span className="w-8 flex-none text-right text-slate-500">{line.line}</span>
            <span className="whitespace-pre-wrap break-all">{line.text || " "}</span>
          </div>
        ))}
      </div>
    );
  }
  if (data.kind === "repo_pr") {
    return (
      <div className="mt-3 rounded-xl border border-shell-border bg-shell-1 px-3 py-2 text-xs text-slate-200">
        <div className="text-[11px] text-slate-400">
          {data.repo} · {data.state}
          {data.merged ? " · merged" : ""}
        </div>
        <div className="mt-1 font-medium text-slate-100">{data.title}</div>
      </div>
    );
  }
  if (data.kind === "repo_commit") {
    return (
      <div className="mt-3 rounded-xl border border-shell-border bg-shell-1 px-3 py-2 font-mono text-[11px] text-slate-200">
        <div className="text-slate-400">
          {data.repo} · {data.sha.slice(0, 7)}
        </div>
        <pre className="mt-1 whitespace-pre-wrap break-all text-slate-100">{data.message}</pre>
      </div>
    );
  }
  return null;
}

function stateLabel(state: ResolvedState | null): string {
  switch (state) {
    case "live":
      return "Live";
    case "stale":
      return "Stale";
    case "missing":
      return "Missing";
    default:
      return "Unverified";
  }
}

function CitationPopover({
  citation,
  anchor,
  onClose,
}: {
  citation: Citation | null;
  anchor: string;
  onClose: () => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        onClose();
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose]);

  const url = citation ? githubUrlForCitation(citation) : null;
  const state = citation?.resolved_state ?? null;
  const target = citation?.target ?? {};
  const observed = citation?.last_observed ?? null;
  const suggested = observed?.suggested_range as
    | { line_start?: number; line_end?: number }
    | undefined;

  return (
    <div
      ref={containerRef}
      contentEditable={false}
      className="absolute left-0 top-full z-30 mt-1 w-80 rounded-2xl border border-shell-border bg-shell-1 p-4 text-left text-sm text-slate-100 shadow-panel backdrop-blur-xl"
    >
      {citation ? (
        <>
          <div className="flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {citation.kind.replace("_", " ")}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                state === "live"
                  ? "bg-emerald-400/15 text-emerald-200"
                  : state === "stale"
                    ? "bg-amber-400/15 text-amber-200"
                    : state === "missing"
                      ? "bg-rose-500/15 text-rose-200"
                      : "bg-shell-2 text-slate-300"
              }`}
            >
              {stateLabel(state)}
            </span>
          </div>
          <div className="mt-2 break-all font-mono text-xs text-slate-200">
            {citationPillLabel(citation, anchor)}
          </div>
          {citation.kind === "repo_range" ? (
            <div className="mt-1 text-[11px] text-slate-500">
              {String(target.repo ?? "")} · {String(target.path ?? "")}
            </div>
          ) : citation.kind === "repo_pr" ? (
            <div className="mt-1 text-[11px] text-slate-500">
              {String(target.repo ?? "")} · {String(target.title_at_draft ?? "")}
            </div>
          ) : citation.kind === "repo_commit" ? (
            <div className="mt-1 text-[11px] text-slate-500">
              {String(target.repo ?? "")}
            </div>
          ) : null}
          {state === "stale" && suggested?.line_start && suggested?.line_end ? (
            <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              Content moved to lines {suggested.line_start}–{suggested.line_end}.
            </div>
          ) : null}
          {state === "stale" && citation.kind === "repo_range" ? (
            <CitationDiffPane citationId={citation.id} />
          ) : null}
          {state === "missing" ? (
            <div className="mt-3 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
              Target no longer resolves on GitHub.
            </div>
          ) : (
            <CitationPreviewPane citationId={citation.id} />
          )}
          <div className="mt-4 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">anchor: {anchor}</span>
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-shell-border bg-shell-2 px-3 py-1 text-xs text-slate-100 hover:border-shell-border-strong hover:bg-shell-2"
              >
                <Github size={12} />
                View in GitHub
              </a>
            ) : null}
          </div>
        </>
      ) : (
        <>
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
            Unverified citation
          </div>
          <div className="mt-2 text-xs text-slate-400">
            Anchor <code className="font-mono">{anchor}</code> couldn't be matched against this
            artifact. Reopen the workpad or run Verify citations to refresh.
          </div>
        </>
      )}
    </div>
  );
}

function CitationPill({ node }: NodeViewProps) {
  const anchor = String(node.attrs.anchor ?? "").toLowerCase();
  const citation = useWorkbenchStore((state) =>
    state.activeArtifact?.citations?.find((item) => item.anchor === anchor) ?? null,
  );
  const verifyPhase = useWorkbenchStore((state) => state.verify.phase);
  const conversationStatus = useWorkbenchStore((state) => state.status);
  const [open, setOpen] = useState(false);
  const hoverTimerRef = useRef<number | null>(null);

  const label = citationPillLabel(citation, anchor);
  const stateModifier = citationStateModifier(citation?.resolved_state ?? null);
  const titleState = citation?.resolved_state
    ? ` · ${citation.resolved_state}`
    : "";
  const title = citation
    ? `${citation.kind}${titleState} · ${label}`
    : `Unresolved citation: ${anchor}`;
  const isConversationLoading = conversationStatus === "loading";
  const isVerifying = verifyPhase === "verifying";
  const skeletonModifier =
    !citation && isConversationLoading
      ? "workpad-citation--skeleton"
      : isVerifying
        ? "workpad-citation--pulsing"
        : "";

  function handlePointerEnter() {
    if (!citation) return;
    if (hoverTimerRef.current !== null) return;
    hoverTimerRef.current = window.setTimeout(() => {
      void fetchCitationPreview(citation.id);
      hoverTimerRef.current = null;
    }, 200);
  }

  function handlePointerLeave() {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  }

  useEffect(() => {
    return () => {
      if (hoverTimerRef.current !== null) {
        window.clearTimeout(hoverTimerRef.current);
      }
    };
  }, []);

  return (
    <NodeViewWrapper
      as="span"
      contentEditable={false}
      draggable={false}
      data-cite={anchor}
      data-state={citation?.resolved_state ?? "unknown"}
      className={`workpad-citation ${stateModifier} ${skeletonModifier}`.trim()}
      title={title}
      style={{ position: "relative" }}
      onMouseEnter={handlePointerEnter}
      onMouseLeave={handlePointerLeave}
    >
      <button
        type="button"
        className="workpad-citation__button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
      >
        <span className="workpad-citation__icon" aria-hidden>
          {citation ? iconForCitationKind(citation.kind) : <FileText size={12} />}
        </span>
        <span className="workpad-citation__label">{label}</span>
      </button>
      {open ? (
        <CitationPopover citation={citation} anchor={anchor} onClose={() => setOpen(false)} />
      ) : null}
    </NodeViewWrapper>
  );
}

const CitationExtension = TiptapNode.create({
  name: "citation",
  inline: true,
  group: "inline",
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      anchor: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-cite") ?? "",
        renderHTML: (attributes) =>
          attributes.anchor ? { "data-cite": String(attributes.anchor).toLowerCase() } : {},
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span[data-cite]",
        getAttrs: (element) => {
          const anchor = (element as HTMLElement).getAttribute("data-cite");
          return anchor ? { anchor: anchor.toLowerCase() } : false;
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "workpad-citation" })];
  },

  addNodeView() {
    return ReactNodeViewRenderer(CitationPill);
  },

  addPasteRules() {
    return [
      nodePasteRule({
        find: /\[\[cite:([a-z0-9_-]{2,32})\]\]/gi,
        type: this.type,
        getAttributes: (match) => ({ anchor: String(match[1] ?? "").toLowerCase() }),
      }),
    ];
  },
});

type ContentSegment = { kind: "markdown"; value: string } | { kind: "mermaid"; source: string };

const MERMAID_FENCE_PATTERN = /```mermaid[^\S\n]*\n([\s\S]*?)```/g;

function splitContentSegments(content: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  let cursor = 0;
  MERMAID_FENCE_PATTERN.lastIndex = 0;
  let match = MERMAID_FENCE_PATTERN.exec(content);
  while (match !== null) {
    if (match.index > cursor) {
      segments.push({ kind: "markdown", value: content.slice(cursor, match.index) });
    }
    segments.push({ kind: "mermaid", source: match[1].trimEnd() });
    cursor = match.index + match[0].length;
    match = MERMAID_FENCE_PATTERN.exec(content);
  }
  if (cursor < content.length) {
    segments.push({ kind: "markdown", value: content.slice(cursor) });
  }
  return segments.length > 0 ? segments : [{ kind: "markdown", value: content }];
}

function MermaidBlock({ source }: { source: string }) {
  const reactId = useId();
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!source.trim()) {
      setSvg(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const safeId = `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
    mermaid
      .render(safeId, source)
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setSvg(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [source, reactId]);

  if (error) {
    return (
      <div className="my-3 rounded-2xl border border-rose-400/20 bg-rose-500/10 p-3 text-xs text-rose-100">
        <div className="mb-2 font-medium">Mermaid diagram failed to render.</div>
        <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[12px] leading-5 text-rose-100/80">{source}</pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-3 rounded-2xl border border-shell-border bg-shell-2 px-4 py-3 text-xs text-slate-500">
        Rendering diagram…
      </div>
    );
  }

  return (
    <div
      className="my-3 overflow-x-auto rounded-2xl border border-shell-border bg-shell-2 p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: sanitizeMermaidSvg(svg) }}
    />
  );
}

// Mermaid flowcharts render node labels via <foreignObject> containing HTML
// <div>/<span> so text can wrap and inherit CSS. DOMPurify's svg-only profile
// strips <foreignObject> (and anything HTML inside it), leaving coloured
// boxes with no visible text. We keep DOMPurify as defence-in-depth but let
// it handle HTML + SVG together and explicitly allow foreignObject.
// Mermaid itself runs with securityLevel: "strict" so user-supplied diagram
// source can't inject scripts before we get here.
function sanitizeMermaidSvg(svg: string): string {
  return DOMPurify.sanitize(svg, {
    ADD_TAGS: ["foreignObject"],
    ADD_ATTR: ["requiredExtensions", "xmlns:xlink"],
  });
}

// Parse the SVG with the browser's XML parser (which is authoritative),
// normalize width/height from the viewBox, and re-serialize through
// XMLSerializer. That guarantees the output is well-formed XML — no
// duplicate attributes, no missing namespaces — regardless of what mermaid
// emitted.
function normalizeSvgForRaster(svgString: string): { svg: string; width: number; height: number } {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgString, "image/svg+xml");
  const parseError = doc.querySelector("parsererror");
  if (parseError) {
    const detail = (parseError.textContent || "").trim().replace(/\s+/g, " ").slice(0, 160);
    throw new Error(`svg parse error: ${detail}`);
  }
  const root = doc.documentElement as unknown as SVGSVGElement;
  let width = 0;
  let height = 0;
  const viewBox = root.getAttribute("viewBox");
  if (viewBox) {
    const parts = viewBox.trim().split(/[\s,]+/).map(Number);
    if (parts.length === 4 && parts.every((n) => Number.isFinite(n))) {
      width = parts[2];
      height = parts[3];
    }
  }
  const explicitW = Number(root.getAttribute("width"));
  const explicitH = Number(root.getAttribute("height"));
  if (Number.isFinite(explicitW) && explicitW > 0) width = explicitW;
  if (Number.isFinite(explicitH) && explicitH > 0) height = explicitH;
  if (!width) width = 800;
  if (!height) height = 600;
  root.setAttribute("width", String(width));
  root.setAttribute("height", String(height));
  if (!root.getAttribute("xmlns")) {
    root.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  }
  if (!root.getAttribute("xmlns:xlink")) {
    root.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  }
  return { svg: new XMLSerializer().serializeToString(root), width, height };
}

// UTF-8-safe btoa. Plain btoa can't handle multi-byte characters.
function toBase64Utf8(str: string): string {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

async function svgStringToPngDataUrl(
  svgString: string,
): Promise<{ dataUrl: string; width: number; height: number }> {
  const { svg, width, height } = normalizeSvgForRaster(svgString);
  const dataUrl = `data:image/svg+xml;base64,${toBase64Utf8(svg)}`;
  const image: HTMLImageElement = await new Promise((resolve, reject) => {
    const el = document.createElement("img");
    el.decoding = "sync";
    el.onload = () => resolve(el);
    el.onerror = () => {
      const head = svg.slice(0, 160).replace(/\s+/g, " ");
      reject(new Error(`svg rasterize: image load failed — head: ${head}`));
    };
    el.src = dataUrl;
  });
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil(width * scale));
  canvas.height = Math.max(1, Math.ceil(height * scale));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("svg rasterize: canvas context unavailable");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  return { dataUrl: canvas.toDataURL("image/png"), width, height };
}

// Constrain rasterized diagrams to a single Letter page for both DOCX
// (Pandoc uses these attrs for sizing) and PDF (WeasyPrint respects them
// too, in addition to the max-height CSS on .doc-diagram img).
const EXPORT_DIAGRAM_MAX_WIDTH_PX = 576;  // ~6in at 96 DPI
const EXPORT_DIAGRAM_MAX_HEIGHT_PX = 720; // ~7.5in at 96 DPI

function fitDiagramDimensions(
  width: number,
  height: number,
): { width: number; height: number } {
  const ratio = Math.min(
    1,
    EXPORT_DIAGRAM_MAX_WIDTH_PX / Math.max(1, width),
    EXPORT_DIAGRAM_MAX_HEIGHT_PX / Math.max(1, height),
  );
  return {
    width: Math.max(1, Math.round(width * ratio)),
    height: Math.max(1, Math.round(height * ratio)),
  };
}

const MERMAID_PREVIEW_CONFIG = {
  startOnLoad: false,
  theme: "neutral" as const,
  securityLevel: "strict" as const,
  fontFamily: "inherit",
};

const MERMAID_EXPORT_CONFIG = {
  startOnLoad: false,
  theme: "default" as const,
  securityLevel: "loose" as const,
  fontFamily: "inherit",
  flowchart: { htmlLabels: false, useMaxWidth: false },
  sequence: { useMaxWidth: false },
  gantt: { useMaxWidth: false },
};

async function buildRenderedArtifactHtml(content: string): Promise<string> {
  const segments = splitContentSegments(content);
  const hasMermaid = segments.some((segment) => segment.kind === "mermaid");

  // Flip mermaid into export config once for the whole batch so we don't pay
  // two initialize() round-trips per diagram (they're synchronous and block
  // the main thread, which is the UI jitter source).
  if (hasMermaid) {
    mermaid.initialize(MERMAID_EXPORT_CONFIG);
  }

  try {
    const parts: string[] = [];
    for (let i = 0; i < segments.length; i += 1) {
      // Yield to the browser between segments so paint/input aren't starved.
      if (i > 0) {
        await new Promise<void>((resolve) => setTimeout(resolve, 0));
      }
      const segment = segments[i];
      if (segment.kind === "mermaid") {
        if (!segment.source.trim()) {
          continue;
        }
        const safeId = `mermaid-export-${Math.random().toString(36).slice(2, 10)}`;
        try {
          const { svg } = await mermaid.render(safeId, segment.source);
          const { dataUrl, width, height } = await svgStringToPngDataUrl(svg);
          const fit = fitDiagramDimensions(width, height);
          parts.push(
            `<div class="doc-diagram"><img src="${dataUrl}" alt="diagram" ` +
              `width="${fit.width}" height="${fit.height}" /></div>`,
          );
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          const escape = (text: string) =>
            text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          parts.push(
            `<pre><code>${escape(segment.source)}</code></pre>` +
              `<p><em>Mermaid diagram failed to render: ${escape(message)}</em></p>`,
          );
        }
      } else {
        parts.push(markdownToHtml(segment.value));
      }
    }
    return parts.join("\n");
  } finally {
    if (hasMermaid) {
      mermaid.initialize(MERMAID_PREVIEW_CONFIG);
    }
  }
}

function MarkdownWithDiagrams({ content, className }: { content: string; className?: string }) {
  const segments = useMemo(() => splitContentSegments(content), [content]);
  return (
    <div className={className}>
      {segments.map((segment, index) =>
        segment.kind === "mermaid" ? (
          <MermaidBlock key={index} source={segment.source} />
        ) : (
          <div key={index} dangerouslySetInnerHTML={{ __html: markdownToHtml(segment.value) }} />
        ),
      )}
    </div>
  );
}

function RenderedMessageContent({ content }: { content: string }) {
  return <MarkdownWithDiagrams content={content} className="prose-chat" />;
}

function messageTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function MessageRow({
  message,
  isLastUser = false,
  isLastAssistant = false,
}: {
  message: Message;
  isLastUser?: boolean;
  isLastAssistant?: boolean;
}) {
  const isUser = message.role === "user";
  const { user } = useAuth();
  const status = useWorkbenchStore((state) => state.status);
  const regenerateLastAssistant = useWorkbenchStore((state) => state.regenerateLastAssistant);
  const editLastUserMessage = useWorkbenchStore((state) => state.editLastUserMessage);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const streaming = status === "streaming";

  useEffect(() => {
    if (!isEditing) {
      setDraft(message.content);
    }
  }, [message.content, isEditing]);

  useEffect(() => {
    if (!isEditing || !textareaRef.current) {
      return;
    }
    const el = textareaRef.current;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [isEditing]);

  function handleEditSubmit() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === message.content.trim()) {
      setIsEditing(false);
      return;
    }
    setIsEditing(false);
    void editLastUserMessage(trimmed);
  }

  const initials =
    (user?.name || user?.email || "")
      .trim()
      .split(/\s+|@/)
      .filter(Boolean)
      .slice(0, 2)
      .map((chunk) => chunk[0]?.toUpperCase() ?? "")
      .join("") || "A";

  const header = (
    <div
      className={`flex items-center gap-2 font-mono text-[10px] text-ink-3 ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {!isUser ? (
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-ink-1 text-white">
          <Sparkles size={9} />
        </span>
      ) : null}
      <span>
        {isUser ? "You" : "Workpad AI"} · {messageTimestamp(message.created_at)}
      </span>
      {isUser ? (
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-signal-soft font-mono text-[8px] font-semibold text-signal-soft-ink">
          {initials}
        </span>
      ) : null}
    </div>
  );

  return (
    <div className="group flex flex-col gap-1.5">
      {header}
      <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
        {isUser ? (
          isEditing ? (
            <div className="w-full min-w-[240px] max-w-[92%] rounded-[10px] border border-signal-soft-border bg-signal-soft px-3 py-2">
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  const el = event.currentTarget;
                  el.style.height = "0px";
                  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    setIsEditing(false);
                  } else if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleEditSubmit();
                  }
                }}
                rows={1}
                className="max-h-48 w-full resize-none border-0 bg-transparent text-[13px] leading-6 text-signal-soft-ink outline-none placeholder:text-ink-3"
              />
              <div className="mt-1.5 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="rounded-md border border-shell-border-strong bg-shell-1 px-2.5 py-1 text-[12px] text-ink-2 transition hover:bg-shell-2 hover:text-ink-1"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleEditSubmit}
                  disabled={!draft.trim() || draft.trim() === message.content.trim()}
                  className="rounded-md bg-signal px-2.5 py-1 text-[12px] font-medium text-white transition hover:bg-signal-hover disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save & regenerate
                </button>
              </div>
            </div>
          ) : (
            <div className="max-w-[92%] whitespace-pre-wrap rounded-[10px] bg-signal-soft px-3 py-2 text-[13px] leading-[1.55] text-signal-soft-ink">
              {message.content}
            </div>
          )
        ) : (
          <div className="max-w-[100%] text-[13px] leading-[1.55] text-ink-1">
            <RenderedMessageContent content={message.content} />
          </div>
        )}
      </div>
      {!isEditing && (isLastUser || isLastAssistant) ? (
        <div
          className={`flex items-center gap-1 text-ink-3 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100 ${
            isUser ? "justify-end" : "justify-start"
          }`}
        >
          {isLastUser ? (
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              disabled={streaming}
              title="Edit message"
              aria-label="Edit message"
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] transition hover:bg-shell-2 hover:text-ink-1 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Pencil size={10} />
              Edit
            </button>
          ) : null}
          {isLastAssistant ? (
            <button
              type="button"
              onClick={() => void regenerateLastAssistant()}
              disabled={streaming}
              title="Regenerate response"
              aria-label="Regenerate response"
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] transition hover:bg-shell-2 hover:text-ink-1 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCcw size={10} />
              Regenerate
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ModelPicker() {
  const models = useWorkbenchStore((state) => state.models);
  const selectedModelId = useWorkbenchStore((state) => state.selectedModelId);
  const setSelectedModel = useWorkbenchStore((state) => state.setSelectedModel);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  const current = models.find((item) => item.id === selectedModelId) ?? models[0];
  if (!current) {
    return null;
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-1.5 rounded-full border border-shell-border bg-shell-1 px-2.5 py-1 font-mono text-[11px] text-ink-2 transition hover:border-shell-border-strong hover:text-ink-1"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Sparkles size={11} />
        {current.label}
        <ChevronDown size={11} />
      </button>
      {open ? (
        <div
          role="listbox"
          className="absolute bottom-full left-0 z-20 mb-2 min-w-[220px] rounded-lg border border-shell-border bg-shell-1 p-1 shadow-panel"
        >
          {models.map((model) => {
            const isSelected = model.id === current.id;
            const disabled = !model.available;
            return (
              <button
                key={model.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                disabled={disabled}
                onClick={() => {
                  if (disabled) {
                    return;
                  }
                  setSelectedModel(model.id);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-[13px] transition ${
                  disabled
                    ? "cursor-not-allowed text-ink-3"
                    : "text-ink-1 hover:bg-shell-2"
                } ${isSelected ? "bg-shell-2" : ""}`}
                title={
                  disabled
                    ? `Set ${model.provider === "openai" ? "OPENAI_API_KEY" : "ANTHROPIC_API_KEY"} to enable.`
                    : undefined
                }
              >
                <span className="flex flex-col">
                  <span>{model.label}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                    {model.provider}
                  </span>
                </span>
                {isSelected ? <Check size={13} className="text-signal" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function ChatComposer({
  centered = false,
}: {
  centered?: boolean;
}) {
  const composer = useWorkbenchStore((state) => state.composer);
  const setComposer = useWorkbenchStore((state) => state.setComposer);
  const sendMessage = useWorkbenchStore((state) => state.sendMessage);
  const status = useWorkbenchStore((state) => state.status);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!textareaRef.current) {
      return;
    }
    textareaRef.current.style.height = "0px";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
  }, [composer]);

  async function handleSubmit() {
    if (status === "streaming") {
      return;
    }
    await sendMessage(composer);
  }

  const wrapperClass = centered
    ? "mx-auto w-full max-w-2xl"
    : "flex-none border-t border-shell-border bg-shell-0 px-3 py-2.5";
  return (
    <div className={wrapperClass}>
      <div className="rounded-[10px] border border-shell-border-strong bg-shell-1 px-3 py-2 transition focus-within:border-signal">
        <textarea
          ref={textareaRef}
          value={composer}
          onChange={(event) => setComposer(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void handleSubmit();
            }
          }}
          rows={1}
          placeholder="Ask Workpad to draft, revise, or code…"
          className="max-h-44 w-full resize-none border-0 bg-transparent text-[13px] leading-relaxed text-ink-1 outline-none placeholder:text-ink-3"
        />
        <div className="mt-2 flex items-center justify-between gap-3">
          <ModelPicker />
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!composer.trim() || status === "streaming"}
            aria-label="Send message"
            className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-shell-2 text-ink-2 transition hover:bg-signal hover:text-white disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-shell-2 disabled:hover:text-ink-2"
          >
            {status === "streaming" ? (
              <LoaderCircle className="animate-spin" size={13} />
            ) : (
              <ArrowUp size={13} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function markdownEditorClassName(_theme: CanvasTheme): string {
  return "tiptap tiptap-light min-h-[480px] bg-transparent focus:outline-none";
}

function markdownPreviewClassName(_theme: CanvasTheme): string {
  return "tiptap tiptap-light min-h-[480px] bg-transparent";
}

function MarkdownEditor({
  value,
  onChange,
  readOnly,
  artifactId,
  theme,
  onEditorReady,
}: {
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  artifactId: string;
  theme: CanvasTheme;
  onEditorReady?: (editor: TiptapEditorType | null) => void;
}) {
  const lastSyncedValue = useRef(value);
  const syncingExternalValueRef = useRef<string | null>(null);
  const themeRef = useRef(theme);
  themeRef.current = theme;

  const editor = useEditor(
    {
      extensions: [
        StarterKit,
        Image.configure({ inline: false, allowBase64: true }),
        TaskList.configure({ HTMLAttributes: { class: "workpad-task-list" } }),
        TaskItem.configure({
          nested: true,
          HTMLAttributes: { class: "workpad-task-item" },
        }),
        CitationExtension,
      ],
      content: markdownToTiptapHtml(value),
      immediatelyRender: false,
      editable: !readOnly,
      editorProps: {
        attributes: {
          class: markdownEditorClassName(themeRef.current),
          "data-placeholder": "The workpad will appear here.",
        },
      },
      onUpdate({ editor: activeEditor }) {
        const markdownValue = turndown.turndown(activeEditor.getHTML()).trim();
        if (syncingExternalValueRef.current !== null && markdownValue === syncingExternalValueRef.current.trim()) {
          lastSyncedValue.current = syncingExternalValueRef.current;
          syncingExternalValueRef.current = null;
          return;
        }
        lastSyncedValue.current = markdownValue;
        onChange(markdownValue);
      },
    },
    [artifactId],
  );

  useEffect(() => {
    if (!editor) {
      return;
    }
    editor.setEditable(!readOnly);
    if (value !== lastSyncedValue.current) {
      lastSyncedValue.current = value;
      syncingExternalValueRef.current = value;
      editor.commands.setContent(markdownToTiptapHtml(value), false);
    }
  }, [editor, value, readOnly, artifactId]);

  useEffect(() => {
    if (!editor) {
      return;
    }
    editor.view.dom.className = markdownEditorClassName(theme);
  }, [editor, theme]);

  useEffect(() => {
    onEditorReady?.(editor ?? null);
    return () => onEditorReady?.(null);
  }, [editor, onEditorReady]);

  return <EditorContent editor={editor} />;
}

function DriftBanner() {
  const artifact = useWorkbenchStore((state) => state.activeArtifact);
  const verify = useWorkbenchStore((state) => state.verify);
  const verifyActiveCitations = useWorkbenchStore((state) => state.verifyActiveCitations);

  if (!artifact || artifact.spec_type !== "rfc") return null;
  const citations = artifact.citations ?? [];
  if (citations.length === 0) return null;

  const total = citations.length;
  const drifted = citations.filter(
    (c) => c.resolved_state === "stale" || c.resolved_state === "missing",
  );
  const unverified = citations.filter((c) => c.resolved_state === "unknown").length;

  if (drifted.length === 0 && unverified === 0 && verify.phase !== "error") {
    return null;
  }

  const firstDrifted = drifted[0];
  const shaShort = firstDrifted
    ? String((firstDrifted.target as Record<string, unknown>)?.ref_at_draft ?? "")
        .slice(0, 7)
    : "";

  return (
    <div className="border-b border-amber-300/20 bg-amber-500/10 px-5 py-3 text-xs text-amber-100">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {verify.phase === "error" ? (
            <>
              <RefreshCcw size={14} className="text-rose-300" />
              <span>
                Couldn't verify citations:{" "}
                <span className="font-medium text-rose-100">
                  {verify.error?.message ?? "unknown error"}
                </span>
              </span>
            </>
          ) : drifted.length > 0 ? (
            <>
              <RefreshCcw size={14} />
              <span>
                <button
                  type="button"
                  onClick={() => scrollToFirstDriftedCitation()}
                  className="mr-1 font-semibold text-amber-50 underline-offset-2 hover:underline"
                >
                  {drifted.length}
                </button>{" "}
                of {total} citations have drifted
                {shaShort ? <> since draft at <code>{shaShort}</code></> : null}.
              </span>
            </>
          ) : (
            <>
              <LoaderCircle size={14} className="animate-spin" />
              <span>{unverified} citations are unverified.</span>
            </>
          )}
        </div>
        <button
          type="button"
          onClick={() => void verifyActiveCitations({ force: true })}
          disabled={verify.phase === "verifying"}
          className="inline-flex items-center gap-1 rounded-full border border-amber-300/30 bg-amber-400/10 px-3 py-1 text-[11px] text-amber-50 transition hover:border-amber-300/50 hover:bg-amber-400/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {verify.phase === "verifying" ? (
            <LoaderCircle size={12} className="animate-spin" />
          ) : (
            <RefreshCcw size={12} />
          )}
          Verify again
        </button>
      </div>
    </div>
  );
}

function scrollToFirstDriftedCitation(): void {
  const target = document.querySelector<HTMLElement>(
    '.workpad-citation[data-state="stale"], .workpad-citation[data-state="missing"]',
  );
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function WorkpadPane() {
  const artifact = useWorkbenchStore((state) => state.activeArtifact);
  const setContent = useWorkbenchStore((state) => state.setActiveArtifactContent);
  const setTitle = useWorkbenchStore((state) => state.setActiveArtifactTitle);
  const refreshActiveArtifact = useWorkbenchStore((state) => state.refreshActiveArtifact);
  const verify = useWorkbenchStore((state) => state.verify);
  const verifyActiveCitations = useWorkbenchStore((state) => state.verifyActiveCitations);
  const status = useWorkbenchStore((state) => state.status);
  const [canvasTheme, toggleCanvasTheme] = useCanvasTheme();
  const [canvasMode, setCanvasMode] = useCanvasMode();
  const [markdownEditor, setMarkdownEditor] = useState<TiptapEditorType | null>(null);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const [downloadingFormat, setDownloadingFormat] = useState<"markdown" | "docx" | "pdf" | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied">("idle");
  const [refreshState, setRefreshState] = useState<"idle" | "refreshing" | "done">("idle");
  const downloadMenuRef = useRef<HTMLDivElement | null>(null);
  const canvasSticky = useStickyScroll();
  const monacoEditorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null);
  const editorChrome = canvasEditorClasses(canvasTheme);
  const isLightCanvas = canvasTheme === "light";

  if (!artifact) {
    return (
      <div className="panel-shell hidden h-full flex-col justify-center p-8 lg:flex">
        <div className="mx-auto max-w-md text-center">
          <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-lg border border-shell-border bg-shell-2">
            <FileText size={26} className="text-ink-3" />
          </div>
          <div className="wp-overline mb-3">Artifact workspace</div>
          <h2 className="font-serif text-[28px] font-medium leading-tight tracking-tight text-ink-1">
            No artifact open.
          </h2>
          <p className="mt-4 text-[14px] leading-relaxed text-ink-2">
            Draft from a repo and transcript, or start one manually. Artifacts render on paper here once the model produces durable output.
          </p>
        </div>
      </div>
    );
  }

  const isReadOnly = status === "streaming";
  const isMarkdownArtifact = artifact.content_type === "markdown";
  const effectiveCanvasMode: CanvasMode = status === "streaming" ? "edit" : canvasMode;
  const isPreviewing = isMarkdownArtifact && effectiveCanvasMode === "preview";
  const isDiffing = effectiveCanvasMode === "diff";
  const editingDisabled = isReadOnly || isPreviewing || isDiffing;
  const canUndo = isMarkdownArtifact
    ? Boolean(markdownEditor && markdownEditor.can().chain().focus().undo().run()) && !editingDisabled
    : !editingDisabled;
  const canRedo = isMarkdownArtifact
    ? Boolean(markdownEditor && markdownEditor.can().chain().focus().redo().run()) && !editingDisabled
    : !editingDisabled;

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!downloadMenuRef.current?.contains(event.target as Node)) {
        setDownloadMenuOpen(false);
      }
    }

    if (downloadMenuOpen) {
      document.addEventListener("mousedown", handlePointerDown);
    }

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [downloadMenuOpen]);

  useEffect(() => {
    if (copyState !== "copied") {
      return;
    }
    const timer = window.setTimeout(() => setCopyState("idle"), 1800);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  function handleUndo() {
    if (editingDisabled) {
      return;
    }
    if (isMarkdownArtifact) {
      markdownEditor?.chain().focus().undo().run();
      return;
    }
    monacoEditorRef.current?.focus();
    monacoEditorRef.current?.trigger("workpad-toolbar", "undo", null);
  }

  function handleRedo() {
    if (editingDisabled) {
      return;
    }
    if (isMarkdownArtifact) {
      markdownEditor?.chain().focus().redo().run();
      return;
    }
    monacoEditorRef.current?.focus();
    monacoEditorRef.current?.trigger("workpad-toolbar", "redo", null);
  }

  async function handleDownload(format: "markdown" | "docx" | "pdf") {
    if (!artifact) {
      return;
    }
    const currentArtifact = artifact;
    setDownloadMenuOpen(false);
    setDownloadingFormat(format);

    try {
      let response: Response;
      if ((format === "docx" || format === "pdf") && currentArtifact.content_type === "markdown") {
        const renderedHtml = await buildRenderedArtifactHtml(currentArtifact.content);
        response = await fetch(
          `${API_BASE}/api/artifacts/${currentArtifact.id}/export-rendered`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ format, html: renderedHtml }),
          },
        );
      } else {
        response = await fetch(
          `${API_BASE}/api/artifacts/${currentArtifact.id}/export?format=${format}`,
          { credentials: "include" },
        );
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }

      const blob = await response.blob();
      const fallbackExtension = format === "markdown" ? "md" : format;
      const fallbackName = `${currentArtifact.title || "workpad_export"}.${fallbackExtension}`;
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition"), fallbackName);
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (error) {
      console.error(error);
    } finally {
      setDownloadingFormat(null);
    }
  }

  async function handleCopy() {
    if (!artifact) {
      return;
    }
    try {
      await copyTextToClipboard(artifact.content);
      setCopyState("copied");
    } catch (error) {
      console.error(error);
    }
  }

  async function handleRefresh() {
    if (!artifact) {
      return;
    }
    if (artifact.dirty) {
      const ok = typeof window === "undefined" ? true : window.confirm("Discard unsaved canvas edits and reload from server?");
      if (!ok) {
        return;
      }
    }
    setRefreshState("refreshing");
    try {
      await refreshActiveArtifact();
      setRefreshState("done");
      // Flash "done" briefly so the user sees the button did something even
      // when the server returned the same version we already had.
      window.setTimeout(() => setRefreshState("idle"), 1400);
    } catch {
      setRefreshState("idle");
    }
  }

  const specTypeLabel = artifact.spec_type === "rfc" ? "RFC" : artifact.content_type;
  const artifactIdShort = artifact.id.slice(0, 8).toUpperCase();
  const savedLabel = artifact.dirty ? "SAVING" : "SAVED";
  const savedClass = artifact.dirty ? "text-state-stale-ink" : "text-state-live";

  return (
    <div className="flex h-full flex-col overflow-hidden bg-shell-0">
      <div className="sticky top-0 z-[3] flex flex-none items-center gap-2 border-b border-shell-border bg-shell-1 px-4 py-2">
        <span className="inline-flex items-center rounded-full border border-shell-border-strong bg-shell-2 px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-ink-2">
          {String(specTypeLabel).toUpperCase()}
        </span>
        <span className="font-mono text-[11px] text-ink-2">{artifactIdShort}</span>
        <span className="font-mono text-[11px] text-ink-3">· V{artifact.version} ·</span>
        <span className={`font-mono text-[11px] font-medium tracking-[0.08em] ${savedClass}`}>
          {savedLabel}
        </span>
        <div className="flex-1 min-w-[8px]" />
        {isMarkdownArtifact ? (
          <div
            className={`inline-flex items-center rounded-md border border-shell-border bg-shell-2 p-0.5 ${
              isReadOnly ? "opacity-50" : ""
            }`}
          >
            {(
              [
                { id: "edit", label: "Edit" },
                { id: "preview", label: "Preview" },
                { id: "diff", label: "Diff" },
              ] as const
            ).map((opt) => {
              const active = effectiveCanvasMode === opt.id;
              const disabled = isReadOnly && opt.id !== "edit";
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setCanvasMode(opt.id as CanvasMode)}
                  disabled={disabled}
                  title={
                    disabled
                      ? `${opt.label} disabled while streaming`
                      : opt.id === "diff"
                        ? "Compare with the previous version"
                        : undefined
                  }
                  className={`rounded px-2.5 py-0.5 text-[12px] font-medium transition ${
                    active
                      ? "bg-shell-0 text-ink-1 shadow-sm"
                      : "text-ink-2 hover:text-ink-1"
                  } disabled:cursor-not-allowed`}
                  aria-pressed={active}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        ) : null}
        <div className="mx-1 h-4 w-px bg-shell-border" />
        <PaperIconButton
          title="Undo"
          onClick={handleUndo}
          disabled={!canUndo}
        >
          <Undo2 size={14} />
        </PaperIconButton>
        <PaperIconButton
          title="Redo"
          onClick={handleRedo}
          disabled={!canRedo}
        >
          <Redo2 size={14} />
        </PaperIconButton>
        <PaperIconButton
          title={
            refreshState === "refreshing"
              ? "Refreshing from server…"
              : refreshState === "done"
                ? "Up to date"
                : "Refresh from server"
          }
          onClick={() => void handleRefresh()}
          disabled={isReadOnly || refreshState === "refreshing"}
        >
          {refreshState === "refreshing" ? (
            <LoaderCircle size={14} className="animate-spin" />
          ) : refreshState === "done" ? (
            <Check size={14} className="text-state-live" />
          ) : (
            <RefreshCcw size={14} />
          )}
        </PaperIconButton>
        <PaperIconButton
          title={copyState === "copied" ? "Copied" : "Copy"}
          onClick={() => void handleCopy()}
        >
          {copyState === "copied" ? <Check size={14} /> : <Copy size={14} />}
        </PaperIconButton>
        {artifact.spec_type === "rfc" ? (
          <PaperIconButton
            title={
              verify.phase === "error"
                ? verify.error?.message ?? "Verify failed — click to retry"
                : "Verify citations"
            }
            onClick={() => void verifyActiveCitations({ force: true })}
            disabled={verify.phase === "verifying"}
          >
            {verify.phase === "verifying" ? (
              <LoaderCircle size={14} className="animate-spin" />
            ) : verify.phase === "error" ? (
              <RefreshCcw size={14} className="text-state-missing" />
            ) : (
              <RefreshCcw size={14} />
            )}
          </PaperIconButton>
        ) : null}
        <div className="relative" ref={downloadMenuRef}>
          <PaperIconButton
            title="Download"
            onClick={() => setDownloadMenuOpen((open) => !open)}
            disabled={downloadingFormat !== null}
          >
            {downloadingFormat ? (
              <LoaderCircle size={14} className="animate-spin" />
            ) : (
              <FileDown size={14} />
            )}
          </PaperIconButton>
          {downloadMenuOpen ? (
            <div className="absolute right-0 top-full z-20 mt-1.5 min-w-[180px] rounded-lg border border-shell-border bg-shell-1 p-1 shadow-panel">
              {(
                [
                  { format: "markdown", label: "Markdown", ext: ".md" },
                  { format: "docx", label: "Word", ext: ".docx" },
                  { format: "pdf", label: "PDF", ext: ".pdf" },
                ] as const
              ).map((item) => {
                const isActive = downloadingFormat === item.format;
                return (
                  <button
                    key={item.format}
                    type="button"
                    onClick={() => void handleDownload(item.format)}
                    disabled={downloadingFormat !== null}
                    className="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-[13px] text-ink-1 transition hover:bg-shell-2 disabled:cursor-wait disabled:opacity-60"
                  >
                    <span className="flex items-center gap-2">
                      {isActive ? (
                        <LoaderCircle size={13} className="animate-spin text-ink-3" />
                      ) : null}
                      {item.label}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                      {item.ext}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
        <PaperIconButton
          title={isLightCanvas ? "Switch canvas to dark" : "Switch canvas to light"}
          onClick={toggleCanvasTheme}
        >
          {isLightCanvas ? <Moon size={14} /> : <Sun size={14} />}
        </PaperIconButton>
      </div>
      <div className="flex-none border-b border-shell-border bg-shell-0 px-6 pb-3 pt-5">
        <input
          value={artifact.title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Untitled artifact"
          className="w-full truncate border-0 bg-transparent font-serif text-[28px] font-medium tracking-tight text-ink-1 outline-none placeholder:text-ink-3"
          style={{ letterSpacing: "-0.02em", lineHeight: 1.2 }}
        />
        <div className="mt-1 font-mono text-[11px] text-ink-3">
          {artifact.content_type} ·{" "}
          {artifact.dirty ? (
            <span className="text-state-stale-ink">saving…</span>
          ) : (
            <span className="text-state-live">saved</span>
          )}
        </div>
      </div>
      <DriftBanner />
      <div className="relative flex-1 overflow-hidden bg-shell-0">
        <div
          ref={canvasSticky.containerRef}
          onScroll={canvasSticky.onScroll}
          className="h-full overflow-auto px-6 py-8"
        >
        <div ref={canvasSticky.contentRef}>
        {isDiffing ? (
          <ArtifactDiffView
            artifactId={artifact.id}
            latestVersion={artifact.version}
            canvasTheme={canvasTheme}
          />
        ) : artifact.content_type === "markdown" ? (
          <article
            className={`paper mx-auto max-w-[780px] rounded-lg border border-paper-border bg-paper-0 px-12 py-12 shadow-none ${canvasTheme === "dark" ? "paper-dark" : ""}`}
          >
            {isPreviewing ? (
              <MarkdownWithDiagrams content={artifact.content} className={markdownPreviewClassName(canvasTheme)} />
            ) : (
              <MarkdownEditor
                artifactId={artifact.id}
                readOnly={isReadOnly}
                value={artifact.content}
                onChange={setContent}
                theme={canvasTheme}
                onEditorReady={setMarkdownEditor}
              />
            )}
          </article>
        ) : (
          <div className={editorChrome.monacoWrap}>
            <MonacoEditor
              key={artifact.id}
              height="100%"
              defaultLanguage={artifact.content_type === "text" ? "plaintext" : artifact.content_type}
              language={artifact.content_type === "text" ? "plaintext" : artifact.content_type}
              theme={editorChrome.monacoTheme}
              value={artifact.content}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                wordWrap: "on",
                padding: { top: 20 },
                scrollBeyondLastLine: false,
                readOnly: isReadOnly,
                fontFamily: "IBM Plex Mono",
              }}
              onMount={(editor) => {
                monacoEditorRef.current = editor;
              }}
              onChange={(value) => setContent(value ?? "")}
            />
          </div>
        )}
        </div>
        </div>

        {artifact.content_type === "markdown" &&
        (canvasSticky.showJumpTop || canvasSticky.showJump) ? (
          <div className="pointer-events-none absolute bottom-4 right-4 flex flex-col items-end gap-2">
            {canvasSticky.showJumpTop ? (
              <ScrollJumpButton
                direction="up"
                onClick={canvasSticky.scrollToTop}
                className="pointer-events-auto"
              />
            ) : null}
            {canvasSticky.showJump ? (
              <ScrollJumpButton
                direction="down"
                onClick={canvasSticky.scrollToBottom}
                label="Jump to end"
                className="pointer-events-auto"
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ConversationCard({ conversation, active }: { conversation: ConversationSummary; active: boolean }) {
  const selectConversation = useWorkbenchStore((state) => state.selectConversation);
  const archiveConversation = useWorkbenchStore((state) => state.archiveConversation);
  const unarchiveConversation = useWorkbenchStore((state) => state.unarchiveConversation);
  const deleteConversation = useWorkbenchStore((state) => state.deleteConversation);
  const [menuOpen, setMenuOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [menuOpen]);

  const isArchived = Boolean(conversation.archived_at);
  const artifactCount = conversation.artifact_count;

  function handleDelete(event: React.MouseEvent) {
    event.stopPropagation();
    setMenuOpen(false);
    const confirmed =
      typeof window === "undefined"
        ? true
        : window.confirm(`Delete "${conversation.title}"? This can't be undone.`);
    if (!confirmed) {
      return;
    }
    void deleteConversation(conversation.id);
  }

  return (
    <div
      ref={containerRef}
      className={`group relative rounded-md border transition ${
        active
          ? "border-signal-soft-border bg-signal-soft"
          : "border-transparent hover:bg-shell-2"
      } ${isArchived ? "opacity-60" : ""}`}
    >
      <button
        type="button"
        onClick={() => void selectConversation(conversation.id)}
        className="block w-full rounded-md px-2.5 py-2 pr-8 text-left"
      >
        <div className={`truncate text-[12.5px] ${active ? "font-medium text-signal-soft-ink" : "font-normal text-ink-1"}`}>
          {conversation.title}
          {isArchived ? (
            <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-3">
              archived
            </span>
          ) : null}
        </div>
        <div className="mt-0.5 flex items-center gap-2 truncate font-mono text-[10px] text-ink-3">
          <span>{artifactCount} {artifactCount === 1 ? "artifact" : "artifacts"}</span>
          <span>·</span>
          <span>{formatTimestamp(conversation.updated_at)}</span>
        </div>
      </button>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setMenuOpen((value) => !value);
        }}
        title="Thread actions"
        aria-label="Thread actions"
        className={`absolute right-1 top-1.5 flex h-6 w-6 items-center justify-center rounded-md text-ink-3 transition ${
          menuOpen ? "bg-shell-2 text-ink-1 opacity-100" : "opacity-0 group-hover:opacity-100 hover:bg-shell-2 hover:text-ink-1"
        }`}
      >
        <MoreHorizontal size={14} />
      </button>
      {menuOpen ? (
        <div className="absolute right-1 top-9 z-20 min-w-[160px] rounded-lg border border-shell-border bg-shell-1 p-1 shadow-panel">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setMenuOpen(false);
              void (isArchived ? unarchiveConversation(conversation.id) : archiveConversation(conversation.id));
            }}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] text-ink-1 transition hover:bg-shell-2"
          >
            {isArchived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
            {isArchived ? "Unarchive" : "Archive"}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] text-state-missing-ink transition hover:bg-state-missing-soft"
          >
            <Trash2 size={13} />
            Delete
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Sidebar({ collapsed }: { collapsed: boolean }) {
  const conversations = useWorkbenchStore((state) => state.conversations);
  const activeConversationId = useWorkbenchStore((state) => state.activeConversationId);
  const startNewConversation = useWorkbenchStore((state) => state.startNewConversation);
  const showArchived = useWorkbenchStore((state) => state.showArchived);
  const setShowArchived = useWorkbenchStore((state) => state.setShowArchived);
  const { user, signOut } = useAuth();
  const [systemTheme, setSystemTheme] = useSystemTheme();
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);
  const liveCount = conversations.filter((c) => !c.archived_at).length;

  useEffect(() => {
    if (!accountMenuOpen) return;
    function onDown(event: MouseEvent) {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setAccountMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [accountMenuOpen]);

  const displayName = user?.name?.trim() || user?.email?.split("@")[0] || "Account";
  const displayHandle = user?.email || "signed in";
  const initials = (user?.name || user?.email || "")
    .trim()
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((chunk) => chunk[0]?.toUpperCase() ?? "")
    .join("") || "A";

  if (collapsed) {
    return (
      <aside className="hidden h-full w-14 flex-none flex-col items-center gap-3 border-r border-shell-border bg-shell-1 py-4 lg:flex">
        <button
          type="button"
          onClick={() => void startNewConversation()}
          title="New artifact"
          aria-label="New artifact"
          className="flex h-8 w-8 items-center justify-center rounded-md bg-signal text-white transition hover:bg-signal-hover"
        >
          <Plus size={16} />
        </button>
        <button
          type="button"
          title="Threads"
          aria-label="Threads"
          className="flex h-8 w-8 items-center justify-center rounded-md text-ink-2 transition hover:bg-shell-2 hover:text-ink-1"
        >
          <MessageSquareText size={16} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="hidden h-full w-[260px] flex-none flex-col border-r border-shell-border bg-shell-1 px-3 py-3 lg:flex">
      <button
        type="button"
        onClick={() => void startNewConversation()}
        className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg bg-signal px-3 py-2 text-[13px] font-medium text-white transition hover:bg-signal-hover"
      >
        <Plus size={14} />
        New artifact
      </button>

      <div className="px-2">
        <div className="wp-overline mb-1.5">Workspace</div>
      </div>
      <nav className="flex flex-col gap-0.5 pb-3">
        <SidebarNavItem icon={<FileText size={14} />} label="Library" count={null} disabled />
        <SidebarNavItem
          icon={<MessageSquareText size={14} />}
          label="Threads"
          count={liveCount}
          active
        />
        <SidebarNavItem icon={<GitCommit size={14} />} label="Search" kbd="⌘K" disabled />
        <SidebarNavItem icon={<Settings size={14} />} label="Settings" disabled />
      </nav>

      <div className="px-2 pb-1.5 pt-2">
        <div className="wp-overline">Collections</div>
      </div>
      <nav className="flex flex-col gap-0.5 pb-3">
        {([
          { label: "acme/platform", count: 89, dot: "bg-state-live" },
          { label: "acme/workpad-ai", count: 34, dot: "bg-state-live" },
          { label: "acme/legacy-billing", count: 19, dot: "bg-state-stale" },
        ] as const).map((c) => (
          <button
            key={c.label}
            type="button"
            className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition hover:bg-shell-2"
          >
            <span className={`h-2 w-2 flex-none rounded-sm ${c.dot}`} />
            <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink-2">
              {c.label}
            </span>
            <span className="font-mono text-[10px] text-ink-3">{c.count}</span>
          </button>
        ))}
      </nav>

      <div className="flex items-center justify-between px-2 pb-1.5 pt-2">
        <div className="wp-overline">Recent threads</div>
        {conversations.length > 4 ? (
          <span className="font-mono text-[10px] text-ink-3">{conversations.length}</span>
        ) : null}
      </div>
      <div className="-mr-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-1">
        {conversations.length === 0 ? (
          <div className="px-2 py-4 text-[12px] text-ink-3">
            No threads yet. Start one below.
          </div>
        ) : null}
        {conversations.map((conversation) => (
          <ConversationCard
            key={conversation.id}
            conversation={conversation}
            active={activeConversationId === conversation.id}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={() => void setShowArchived(!showArchived)}
        className="mx-2 mt-3 flex items-center justify-center gap-2 rounded-md px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 transition hover:bg-shell-2 hover:text-ink-2"
      >
        {showArchived ? <ArchiveRestore size={11} /> : <Archive size={11} />}
        {showArchived ? "Hide archived" : "Show archived"}
      </button>

      <div
        ref={accountMenuRef}
        className="relative mt-3 border-t border-shell-border pt-3"
      >
        <button
          type="button"
          onClick={() => setAccountMenuOpen((open) => !open)}
          className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition hover:bg-shell-2"
        >
          <div className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-paper-2 font-mono text-[10px] font-semibold text-paper-ink">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] font-medium text-ink-1">
              {displayName}
            </div>
            <div className="truncate font-mono text-[10px] text-ink-3">
              {displayHandle}
            </div>
          </div>
          <ChevronDown
            size={14}
            className={`flex-none text-ink-3 transition ${accountMenuOpen ? "rotate-180" : ""}`}
          />
        </button>
        {accountMenuOpen ? (
          <div className="absolute bottom-full left-0 right-0 z-30 mb-2 rounded-lg border border-shell-border bg-shell-1 p-1 shadow-panel">
            <div className="px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
              Signed in as
            </div>
            <div className="truncate px-2.5 pb-2 text-[12px] text-ink-1">
              {user?.email ?? "—"}
            </div>
            <div className="h-px bg-shell-border" />
            <div className="px-2.5 pb-1 pt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
              Appearance
            </div>
            <div className="mb-1 flex items-center gap-1 rounded-md bg-shell-2 p-0.5">
              {(
                [
                  { id: "light", label: "Light", icon: <Sun size={11} /> },
                  { id: "dark", label: "Dark", icon: <Moon size={11} /> },
                  { id: "auto", label: "Auto", icon: null },
                ] as const
              ).map((opt) => {
                const active = systemTheme === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setSystemTheme(opt.id as SystemTheme)}
                    className={`flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition ${
                      active
                        ? "bg-shell-1 text-ink-1 shadow-sm"
                        : "text-ink-2 hover:text-ink-1"
                    }`}
                    aria-pressed={active}
                  >
                    {opt.icon}
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <div className="h-px bg-shell-border" />
            <button
              type="button"
              onClick={() => {
                setAccountMenuOpen(false);
                void signOut();
              }}
              className="mt-1 flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] text-ink-1 transition hover:bg-shell-2"
            >
              <LogOut size={13} />
              Sign out
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function WorkpadWordmark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const fontSize = size === "sm" ? 14 : size === "lg" ? 24 : 17;
  const dot = size === "sm" ? 6 : size === "lg" ? 9 : 7;
  const gap = size === "sm" ? 5 : size === "lg" ? 9 : 6;
  return (
    <span
      className="inline-flex items-center font-sans font-bold tracking-tight text-ink-1"
      style={{ fontSize, gap, letterSpacing: "-0.02em" }}
    >
      Workpad
      <span
        className="wp-pulse inline-block"
        style={{ width: dot + 1, height: dot + 1, background: "var(--accent-signal)" }}
      />
    </span>
  );
}

function SidebarNavItem({
  icon,
  label,
  count,
  kbd,
  active,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  count?: number | null;
  kbd?: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const base =
    "relative flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] transition";
  const tone = active
    ? "bg-signal-soft text-signal-soft-ink font-medium"
    : disabled
      ? "text-ink-3 cursor-default"
      : "text-ink-2 hover:bg-shell-2 hover:text-ink-1";
  return (
    <button type="button" onClick={disabled ? undefined : onClick} className={`${base} ${tone}`}>
      {active ? (
        <span className="absolute -left-3 top-1.5 bottom-1.5 w-[2px] rounded-full bg-signal" />
      ) : null}
      {icon}
      <span className="flex-1">{label}</span>
      {count !== undefined && count !== null ? (
        <span
          className={`font-mono text-[10px] ${
            active ? "text-signal-soft-ink" : "text-ink-3"
          }`}
        >
          {count}
        </span>
      ) : null}
      {kbd ? <span className="font-mono text-[10px] text-ink-3">{kbd}</span> : null}
    </button>
  );
}

function normalizeRepoInput(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const patterns: RegExp[] = [
    /^https?:\/\/github\.com\/([^/\s]+)\/([^/\s#?]+?)(?:\.git)?(?:\/.*)?$/i,
    /^git@github\.com:([^/\s]+)\/([^/\s#?]+?)(?:\.git)?$/i,
    /^([^/\s]+)\/([^/\s]+)$/,
  ];
  for (const pattern of patterns) {
    const match = trimmed.match(pattern);
    if (match) {
      return `${match[1]}/${match[2]}`;
    }
  }
  return null;
}

const DRAFT_PHASE_ORDER: DraftPhase[] = ["pass1", "pass2", "finalizing", "completed"];

function draftPhaseStatus(
  phase: DraftPhase,
  current: DraftPhase,
): "pending" | "active" | "done" {
  if (current === "error") {
    return "pending";
  }
  const currentIndex = DRAFT_PHASE_ORDER.indexOf(current);
  const phaseIndex = DRAFT_PHASE_ORDER.indexOf(phase);
  if (currentIndex < 0) return "pending";
  if (phaseIndex < currentIndex) return "done";
  if (phaseIndex === currentIndex) return "active";
  return "pending";
}

function DraftProgressRow({
  label,
  status,
  detail,
}: {
  label: string;
  status: "pending" | "active" | "done";
  detail?: React.ReactNode;
}) {
  const pillClass =
    status === "done"
      ? "border-emerald-300/40 bg-emerald-400/15 text-emerald-100"
      : status === "active"
        ? "border-sky-300/40 bg-sky-400/15 text-sky-100"
        : "border-shell-border bg-shell-2 text-slate-400";
  return (
    <li className="flex items-start gap-3">
      <span
        className={`mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full border ${pillClass}`}
      >
        {status === "done" ? (
          <Check size={12} />
        ) : status === "active" ? (
          <LoaderCircle size={12} className="animate-spin" />
        ) : (
          <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div
          className={
            status === "pending"
              ? "text-sm text-slate-500"
              : "text-sm font-medium text-slate-100"
          }
        >
          {label}
        </div>
        {detail ? <div className="mt-1 text-xs text-slate-400">{detail}</div> : null}
      </div>
    </li>
  );
}

function DraftProgress() {
  const draft = useWorkbenchStore((state) => state.draft);
  const pickedDetail = draft.pickedPaths.length
    ? draft.pickedPaths.slice(0, 5).join(", ") +
      (draft.pickedPaths.length > 5 ? `, +${draft.pickedPaths.length - 5} more` : "")
    : null;
  const citationsDetail = draft.citationSummary
    ? `${draft.citationSummary.valid} valid · ${draft.citationSummary.dropped} dropped` +
      (draft.citationSummary.reasons.length
        ? ` (${Array.from(new Set(draft.citationSummary.reasons)).join(", ")})`
        : "")
    : null;

  return (
    <ul className="space-y-4">
      <DraftProgressRow
        label="Selecting relevant files"
        status={draftPhaseStatus("pass1", draft.phase)}
        detail={pickedDetail}
      />
      <DraftProgressRow
        label="Drafting RFC"
        status={draftPhaseStatus("pass2", draft.phase)}
      />
      <DraftProgressRow
        label="Validating citations"
        status={draftPhaseStatus("finalizing", draft.phase)}
        detail={citationsDetail}
      />
      <DraftProgressRow
        label="Opening workpad"
        status={draftPhaseStatus("completed", draft.phase)}
      />
    </ul>
  );
}

type SettingsInfo = { has_github_default_token: boolean; has_openai_api_key: boolean };

function NewSpecModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const draft = useWorkbenchStore((state) => state.draft);
  const draftSpec = useWorkbenchStore((state) => state.draftSpec);
  const resetDraft = useWorkbenchStore((state) => state.resetDraft);
  const activeConversationId = useWorkbenchStore((state) => state.activeConversationId);

  const [transcript, setTranscript] = useState("");
  const [repoInput, setRepoInput] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [attachToConversation, setAttachToConversation] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [settingsInfo, setSettingsInfo] = useState<SettingsInfo | null>(null);

  const isBusy = draft.phase === "pass1" || draft.phase === "pass2" || draft.phase === "finalizing";

  useEffect(() => {
    if (!open) {
      setLocalError(null);
      resetDraft();
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const info = await requestJson<SettingsInfo>("/api/settings/info");
        if (!cancelled) setSettingsInfo(info);
      } catch {
        if (!cancelled) setSettingsInfo(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, resetDraft]);

  useEffect(() => {
    if (!open) return;
    if (draft.phase === "completed") {
      const timer = window.setTimeout(() => onClose(), 700);
      return () => window.clearTimeout(timer);
    }
  }, [open, draft.phase, onClose]);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !isBusy) {
        onClose();
      }
    }
    if (open) {
      document.addEventListener("keydown", handleKey);
      return () => document.removeEventListener("keydown", handleKey);
    }
  }, [open, onClose, isBusy]);

  if (!open) return null;

  const repoNormalized = normalizeRepoInput(repoInput);
  const transcriptCount = transcript.length;
  const canSubmit =
    transcript.trim().length > 0 && repoNormalized !== null && !isBusy && draft.phase !== "completed";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    if (!repoNormalized) {
      setLocalError("Repo must look like 'owner/name' or a GitHub URL.");
      return;
    }
    if (!transcript.trim()) {
      setLocalError("Paste at least one line of transcript.");
      return;
    }
    await draftSpec({
      conversation_id: attachToConversation ? activeConversationId : null,
      transcript,
      repo: repoNormalized,
      github_token: githubToken.trim() || undefined,
    });
  }

  const errorToShow = localError
    ? { code: "validation", message: localError }
    : draft.error;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm" style={{ background: "rgba(12, 13, 16, 0.45)" }}>
      <div className="w-full max-w-2xl rounded-[28px] border border-shell-border bg-shell-1 p-6 shadow-panel">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-slate-500">New artifact</div>
            <div className="mt-1 flex items-center gap-2 text-lg font-semibold text-slate-50">
              <NotebookPen size={18} />
              Draft an RFC
            </div>
            <p className="mt-2 max-w-lg text-sm text-slate-400">
              Paste a meeting transcript and point at a GitHub repo. Workpad picks the
              relevant files, drafts the RFC, and anchors every claim to a citation.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isBusy}
            className="glass-button !px-3 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {(isBusy || draft.phase === "completed") && (
          <div className="mt-6 rounded-2xl border border-shell-border bg-shell-1 p-5">
            <DraftProgress />
            {draft.phase === "completed" ? (
              <div className="mt-4 rounded-xl border border-emerald-300/30 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-100">
                RFC ready — opening workpad…
              </div>
            ) : null}
          </div>
        )}

        {settingsInfo && !settingsInfo.has_github_default_token && !githubToken.trim() ? (
          <div className="mt-5 rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            <div className="font-medium">No GitHub token on the server.</div>
            <p className="mt-1 text-xs text-amber-100/90">
              Either paste a PAT below (kept for this request only) or set{" "}
              <code className="rounded bg-amber-500/20 px-1 py-0.5">GITHUB_DEFAULT_TOKEN</code>
              {" "}in <code>.env</code> — see <code>.env.example</code>. The token needs{" "}
              <code className="rounded bg-amber-500/20 px-1 py-0.5">repo:read</code> scope.
            </p>
          </div>
        ) : null}
        {settingsInfo && !settingsInfo.has_openai_api_key ? (
          <div className="mt-3 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            <div className="font-medium">OPENAI_API_KEY is not set.</div>
            <p className="mt-1 text-xs text-rose-100/90">
              The drafter needs an OpenAI key. Add it to <code>.env</code> and restart the API.
            </p>
          </div>
        ) : null}

        <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="text-xs uppercase tracking-[0.18em] text-slate-400">Transcript</label>
            <textarea
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              disabled={isBusy}
              rows={8}
              placeholder={"00:00:12 Alex: We should move auth out of the legacy service.\n00:00:45 Sam: Agreed, let me check the current handler."}
              className="mt-2 w-full resize-y rounded-2xl border border-shell-border bg-shell-1 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/40 focus:outline-none"
            />
            <div className="mt-1 text-right text-[11px] text-slate-500">
              {transcriptCount.toLocaleString()} chars
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="flex items-center gap-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                <Github size={12} /> Repo
              </label>
              <input
                value={repoInput}
                onChange={(event) => setRepoInput(event.target.value)}
                disabled={isBusy}
                placeholder="acme/foo or https://github.com/acme/foo"
                className="mt-2 w-full rounded-2xl border border-shell-border bg-shell-1 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/40 focus:outline-none"
              />
              <div className="mt-1 text-[11px] text-slate-500">
                {repoInput.trim()
                  ? repoNormalized
                    ? `Will draft against ${repoNormalized}`
                    : "Couldn't parse that — use owner/name or a GitHub URL."
                  : " "}
              </div>
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.18em] text-slate-400">
                GitHub token <span className="text-slate-500">(optional)</span>
              </label>
              <input
                value={githubToken}
                onChange={(event) => setGithubToken(event.target.value)}
                disabled={isBusy}
                type="password"
                placeholder="Falls back to GITHUB_DEFAULT_TOKEN"
                className="mt-2 w-full rounded-2xl border border-shell-border bg-shell-1 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/40 focus:outline-none"
              />
              <div className="mt-1 text-[11px] text-slate-500">
                Stored per-request. Use a PAT with <code>repo:read</code>.
              </div>
            </div>
          </div>

          {activeConversationId ? (
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={attachToConversation}
                onChange={(event) => setAttachToConversation(event.target.checked)}
                disabled={isBusy}
              />
              Attach to the current conversation
            </label>
          ) : null}

          {errorToShow ? (
            <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
              <div className="text-[11px] uppercase tracking-[0.18em] text-rose-300">
                {errorToShow.code}
              </div>
              <div className="mt-1">{errorToShow.message}</div>
            </div>
          ) : null}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isBusy}
              className="glass-button disabled:cursor-not-allowed disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center gap-2 rounded-full border border-sky-300/30 bg-sky-400/20 px-4 py-2 text-sm font-medium text-sky-50 transition hover:border-sky-300/50 hover:bg-sky-400/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isBusy ? <LoaderCircle size={14} className="animate-spin" /> : <NotebookPen size={14} />}
              {isBusy ? "Drafting…" : "Draft RFC"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PaperIconButton({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="flex h-7 w-7 items-center justify-center rounded-md text-ink-2 transition hover:bg-shell-2 hover:text-ink-1 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function ChatHeaderIcon({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className="flex h-7 w-7 items-center justify-center rounded-md text-ink-2 transition hover:bg-shell-2 hover:text-ink-1"
    >
      {children}
    </button>
  );
}

function AppHeader({
  showWorkpad,
  activeTitle,
  onNewSpec,
  sidebarCollapsed,
  onToggleSidebar,
}: {
  showWorkpad: boolean;
  activeTitle: string | null;
  onNewSpec: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
}) {
  const { user } = useAuth();
  const initials =
    (user?.name || user?.email || "")
      .trim()
      .split(/\s+|@/)
      .filter(Boolean)
      .slice(0, 2)
      .map((chunk) => chunk[0]?.toUpperCase() ?? "")
      .join("") || "A";
  const crumbs = showWorkpad
    ? ["Library", activeTitle || "Untitled artifact"]
    : ["Library"];
  return (
    <header className="flex h-14 flex-none items-center gap-5 border-b border-shell-border bg-shell-1 px-4 sm:px-5">
      <button
        type="button"
        onClick={onToggleSidebar}
        title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="hidden h-7 w-7 flex-none items-center justify-center rounded-md text-ink-3 transition hover:bg-shell-2 hover:text-ink-1 lg:flex"
      >
        {sidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
      </button>
      <WorkpadWordmark />
      <div className="flex min-w-0 items-center gap-3 font-mono text-[12px] text-ink-3">
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-3">
            <span className="text-ink-3">/</span>
            <span
              className={
                i === crumbs.length - 1
                  ? "truncate font-medium text-ink-1"
                  : "truncate text-ink-3"
              }
              style={{ maxWidth: 360 }}
            >
              {crumb}
            </span>
          </span>
        ))}
      </div>
      <button
        type="button"
        className="ml-auto hidden items-center gap-2 rounded-md border border-shell-border bg-shell-2 px-3 py-1.5 font-mono text-[11.5px] text-ink-3 transition hover:border-shell-border-strong hover:text-ink-2 md:flex md:min-w-[300px]"
      >
        <GitCommit size={12} />
        <span>Search artifacts, sources, threads</span>
        <span className="ml-auto flex items-center gap-1">
          <span className="wp-kbd">⌘</span>
          <span className="wp-kbd">K</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onNewSpec}
        className="inline-flex items-center gap-1.5 rounded-md border border-shell-border-strong bg-shell-1 px-2.5 py-1.5 text-[12px] font-medium text-ink-1 transition hover:bg-shell-2"
      >
        <Sparkles size={14} />
        Ask
      </button>
      <div
        className="flex h-7 w-7 flex-none cursor-pointer items-center justify-center rounded-full bg-paper-2 font-mono text-[10px] font-semibold text-paper-ink"
        title={user?.email ?? undefined}
      >
        {initials}
      </div>
    </header>
  );
}

function App() {
  const bootstrap = useWorkbenchStore((state) => state.bootstrap);
  const messages = useWorkbenchStore((state) => state.messages);
  const status = useWorkbenchStore((state) => state.status);
  const error = useWorkbenchStore((state) => state.error);
  const bootstrapped = useWorkbenchStore((state) => state.bootstrapped);
  const activeArtifact = useWorkbenchStore((state) => state.activeArtifact);
  const activeConversationId = useWorkbenchStore((state) => state.activeConversationId);
  const selectConversation = useWorkbenchStore((state) => state.selectConversation);
  const startNewConversation = useWorkbenchStore((state) => state.startNewConversation);
  const [canvasOnLeft] = useCanvasOnLeft();
  const [newSpecOpen, setNewSpecOpen] = useState(false);
  const [sidebarCollapsed, toggleSidebarCollapsed] = useSidebarCollapsed();
  useAutosave();
  useAutoVerifyCitations();
  useErrorToasts();

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const showWorkpad = Boolean(activeArtifact);

  return (
    <div className="flex h-screen overflow-hidden bg-shell-0">
      <Sidebar collapsed={sidebarCollapsed} />
      <main className="flex-1 overflow-auto">
        {!bootstrapped && status === "loading" ? (
          <div className="flex min-h-[80vh] items-center justify-center">
            <div className="inline-flex items-center gap-2 rounded-md border border-shell-border bg-shell-1 px-4 py-2 font-mono text-[12px] text-ink-2">
              <LoaderCircle className="animate-spin" size={14} />
              Loading workspace…
            </div>
          </div>
        ) : (
          <div className="mx-auto flex h-full max-w-[1680px] flex-col">
            <AppHeader
              showWorkpad={showWorkpad}
              activeTitle={activeArtifact?.title ?? null}
              onNewSpec={() => setNewSpecOpen(true)}
              sidebarCollapsed={sidebarCollapsed}
              onToggleSidebar={toggleSidebarCollapsed}
            />
            <div className="flex-1 overflow-hidden px-4 pb-4 sm:px-6 sm:pb-6">
            {!showWorkpad ? (
              <div className="flex h-full flex-col gap-4">
                {messages.length === 0 && !activeConversationId ? (
                  <div className="flex-1 overflow-auto">
                    <LibraryHome
                      onOpen={(a: ArtifactListItem) => {
                        void selectConversation(a.conversation_id);
                      }}
                      onNew={() => void startNewConversation()}
                      onDraftAI={() => setNewSpecOpen(true)}
                      onContinueLast={() => {
                        const latest = useWorkbenchStore
                          .getState()
                          .conversations.find((c) => !c.archived_at);
                        if (latest) void selectConversation(latest.id);
                      }}
                    />
                  </div>
                ) : (
                  <>
                    <div className="panel-shell flex flex-1 overflow-hidden p-5">
                      <ChatScrollRegion />
                    </div>
                    <ChatComposer />
                  </>
                )}
              </div>
            ) : (
              (() => {
                const canvasPanel = (
                  <Panel key="canvas" order={canvasOnLeft ? 1 : 2} defaultSize={66} minSize={36}>
                    <WorkpadPane />
                  </Panel>
                );
                const chatPanel = (
                  <Panel key="chat" order={1} defaultSize={38} minSize={28}>
                    <aside className="flex h-full min-h-0 flex-col border-r border-shell-border bg-shell-0">
                      <div className="flex flex-none items-center gap-2 border-b border-shell-border px-3.5 py-2.5">
                        <span className="text-[13px] font-semibold text-ink-1">Chat</span>
                        <span className="inline-flex items-center rounded-full border border-shell-border-strong bg-shell-2 px-2 py-0.5 font-mono text-[10px] text-ink-2">
                          thread
                        </span>
                        <div className="ml-auto flex items-center gap-0.5">
                          <ChatHeaderIcon
                            title="History"
                            onClick={() => {}}
                          >
                            <History size={14} />
                          </ChatHeaderIcon>
                          <ChatHeaderIcon
                            title="Share"
                            onClick={() => {}}
                          >
                            <Share2 size={14} />
                          </ChatHeaderIcon>
                          <ChatHeaderIcon
                            title="New thread"
                            onClick={() => void startNewConversation()}
                          >
                            <Plus size={14} />
                          </ChatHeaderIcon>
                          <ChatHeaderIcon
                            title="New RFC from sources"
                            onClick={() => setNewSpecOpen(true)}
                          >
                            <NotebookPen size={14} />
                          </ChatHeaderIcon>
                        </div>
                      </div>
                      <div className="flex-1 overflow-hidden">
                        <ChatScrollRegion />
                      </div>
                      <ChatComposer />
                    </aside>
                  </Panel>
                );
                const panels = canvasOnLeft ? [canvasPanel, chatPanel] : [chatPanel, canvasPanel];
                return (
                  <PanelGroup
                    key={canvasOnLeft ? "canvas-left" : "canvas-right"}
                    direction="horizontal"
                    className="h-full gap-4"
                  >
                    {panels[0]}
                    <PanelResizeHandle className="relative hidden w-3 shrink-0 lg:block">
                      <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 rounded-full bg-shell-2" />
                    </PanelResizeHandle>
                    {panels[1]}
                  </PanelGroup>
                );
              })()
            )}
            </div>
            {error ? (
              <div className="pointer-events-none fixed bottom-5 right-5 z-40 max-w-sm rounded-lg border border-state-missing/30 bg-state-missing-soft px-4 py-3 text-[12.5px] text-state-missing-ink shadow-panel">
                {error}
              </div>
            ) : null}
            {status === "streaming" ? (
              <div className="pointer-events-none fixed bottom-5 left-5 z-40 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-1 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-2 shadow-panel">
                <LoaderCircle className="animate-spin" size={12} />
                streaming
              </div>
            ) : null}
          </div>
        )}
      </main>
      <NewSpecModal open={newSpecOpen} onClose={() => setNewSpecOpen(false)} />
      <Toaster />
    </div>
  );
}

export default App;
