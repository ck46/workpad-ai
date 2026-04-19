import { useEffect, useId, useMemo, useRef, useState } from "react";
import { create } from "zustand";
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
import { marked } from "marked";
import { markedHighlight } from "marked-highlight";
import markedKatex from "marked-katex-extension";
import hljs from "highlight.js";
import mermaid from "mermaid";
import TurndownService from "turndown";
import DOMPurify from "dompurify";

import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "strict",
  fontFamily: "inherit",
});

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
  ArrowLeftRight,
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
type CanvasMode = "edit" | "preview";

const CANVAS_THEME_STORAGE_KEY = "workpad-canvas-theme";
const CANVAS_MODE_STORAGE_KEY = "workpad-canvas-mode";

const CANVAS_ON_LEFT_STORAGE_KEY = "workpad-canvas-on-left";

function useCanvasOnLeft(): [boolean, () => void] {
  const [canvasOnLeft, setCanvasOnLeft] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return true;
    }
    const stored = window.localStorage.getItem(CANVAS_ON_LEFT_STORAGE_KEY);
    return stored === null ? true : stored === "1";
  });

  useEffect(() => {
    window.localStorage.setItem(CANVAS_ON_LEFT_STORAGE_KEY, canvasOnLeft ? "1" : "0");
  }, [canvasOnLeft]);

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
      monacoWrap: "overflow-hidden rounded-[24px] border border-stone-200/80 bg-[#f7f5ef]",
      monacoTheme: "vs" as const,
    };
  }
  return {
    monacoWrap: "overflow-hidden rounded-[24px] border border-white/10 bg-black/20",
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
      const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`, { method: "DELETE" });
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
                : "border-white/10 bg-chrome-900/90 text-slate-100"
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

turndown.addRule("workpad-citation", {
  filter: (node) =>
    node.nodeName === "SPAN" &&
    (node as HTMLElement).hasAttribute?.("data-cite"),
  replacement: (_content, node) => {
    const anchor = (node as HTMLElement).getAttribute("data-cite") ?? "";
    return anchor ? `[[cite:${anchor}]]` : "";
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
        <div className="mt-2 rounded-xl border border-white/10 bg-black/40 p-2">
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
      <div className="mt-3 flex items-center gap-2 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-slate-400">
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
      <div className="mt-3 rounded-xl border border-white/10 bg-black/40 p-2 font-mono text-[11px] text-slate-200">
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
      <div className="mt-3 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-slate-200">
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
      <div className="mt-3 rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-[11px] text-slate-200">
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
      className="absolute left-0 top-full z-30 mt-1 w-80 rounded-2xl border border-white/10 bg-chrome-900/95 p-4 text-left text-sm text-slate-100 shadow-panel backdrop-blur-xl"
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
                      : "bg-white/10 text-slate-300"
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
                className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-100 hover:border-white/20 hover:bg-white/10"
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
      <div className="my-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-xs text-slate-500">
        Rendering diagram…
      </div>
    );
  }

  return (
    <div
      className="my-3 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03] p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } }) }}
    />
  );
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
  return <MarkdownWithDiagrams content={content} className="prose-chat text-[15px] leading-7 text-slate-100" />;
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
  const Icon = isUser ? User : Sparkles;
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

  return (
    <div className={`group flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${
          isUser
            ? "border-sky-300/30 bg-sky-400/15 text-sky-200"
            : "border-white/10 bg-white/[0.06] text-slate-200"
        }`}
      >
        <Icon size={14} />
      </div>
      <div className={`flex min-w-0 max-w-[85%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div className="mb-1 flex items-center gap-1.5 text-[11px] text-slate-500">
          <span className="font-medium text-slate-300">{isUser ? "You" : "Workpad AI"}</span>
          <span>·</span>
          <span>{formatTimestamp(message.created_at)}</span>
        </div>
        {isUser ? (
          isEditing ? (
            <div className="w-full min-w-[280px] rounded-[22px] rounded-br-md border border-sky-300/40 bg-sky-500/10 px-4 py-3">
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
                className="max-h-48 w-full resize-none border-0 bg-transparent text-[15px] leading-7 text-slate-50 outline-none"
              />
              <div className="mt-2 flex items-center justify-end gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="rounded-full border border-white/10 px-3 py-1 text-slate-300 transition hover:border-white/20 hover:bg-white/10"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleEditSubmit}
                  disabled={!draft.trim() || draft.trim() === message.content.trim()}
                  className="rounded-full border border-sky-300/40 bg-sky-400/20 px-3 py-1 text-sky-100 transition hover:border-sky-300/60 hover:bg-sky-400/30 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Save & regenerate
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-[22px] rounded-br-md border border-sky-300/30 bg-sky-500/15 px-5 py-3 text-[15px] leading-7 text-slate-50">
              <div className="whitespace-pre-wrap">{message.content}</div>
            </div>
          )
        ) : (
          <RenderedMessageContent content={message.content} />
        )}
        {!isEditing && (isLastUser || isLastAssistant) ? (
          <div
            className={`mt-1.5 flex items-center gap-1 text-slate-500 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100 ${
              isUser ? "self-end" : "self-start"
            }`}
          >
            {isLastUser ? (
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                disabled={streaming}
                title="Edit message"
                aria-label="Edit message"
                className="inline-flex items-center gap-1 rounded-full border border-white/5 px-2.5 py-1 text-[11px] transition hover:border-white/20 hover:bg-white/10 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Pencil size={12} />
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
                className="inline-flex items-center gap-1 rounded-full border border-white/5 px-2.5 py-1 text-[11px] transition hover:border-white/20 hover:bg-white/10 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <RefreshCcw size={12} />
                Regenerate
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
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
        className="glass-button !px-3 !py-1.5"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Sparkles size={14} />
        {current.label}
        <ChevronDown size={14} />
      </button>
      {open ? (
        <div
          role="listbox"
          className="absolute bottom-full left-0 z-20 mb-2 min-w-[220px] rounded-2xl border border-white/10 bg-chrome-900/95 p-2 shadow-panel backdrop-blur-xl"
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
                className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition ${
                  disabled ? "cursor-not-allowed text-slate-500" : "text-slate-100 hover:bg-white/10"
                } ${isSelected ? "bg-white/5" : ""}`}
                title={disabled ? `Set ${model.provider === "openai" ? "OPENAI_API_KEY" : "ANTHROPIC_API_KEY"} to enable.` : undefined}
              >
                <span className="flex flex-col">
                  <span>{model.label}</span>
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">{model.provider}</span>
                </span>
                {isSelected ? <Check size={14} className="text-sky-300" /> : null}
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

  return (
    <div className={`panel-shell ${centered ? "mx-auto w-full max-w-4xl" : "w-full"} p-3 sm:p-4`}>
      <div className="rounded-[24px] border border-white/10 bg-white/[0.03] px-4 py-4 sm:px-5">
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
          placeholder="Ask Workpad to draft, revise, or code..."
          className="max-h-44 w-full resize-none border-0 bg-transparent text-base text-slate-100 outline-none placeholder:text-slate-500"
        />
        <div className="mt-4 flex items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
            <ModelPicker />
          </div>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!composer.trim() || status === "streaming"}
            className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-950 transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {status === "streaming" ? <LoaderCircle className="animate-spin" size={18} /> : <ArrowUp size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function markdownEditorClassName(theme: CanvasTheme): string {
  const base = "tiptap min-h-[520px] rounded-[24px] border px-6 py-6 focus:outline-none";
  return theme === "light"
    ? `${base} tiptap-light border-stone-200/80 bg-[#f7f5ef]`
    : `${base} border-white/10 bg-black/10`;
}

function markdownPreviewClassName(theme: CanvasTheme): string {
  const base = "tiptap min-h-[520px] rounded-[24px] border px-6 py-6";
  return theme === "light"
    ? `${base} tiptap-light border-stone-200/80 bg-[#f7f5ef]`
    : `${base} border-white/10 bg-black/10`;
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
        CitationExtension,
      ],
      content: markdownToHtml(value),
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
      editor.commands.setContent(markdownToHtml(value), false);
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
  const downloadMenuRef = useRef<HTMLDivElement | null>(null);
  const monacoEditorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null);
  const editorChrome = canvasEditorClasses(canvasTheme);
  const isLightCanvas = canvasTheme === "light";

  if (!artifact) {
    return (
      <div className="panel-shell hidden h-full flex-col justify-center p-8 lg:flex">
        <div className="mx-auto max-w-md text-center">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-3xl border border-white/10 bg-white/5">
            <FileCode2 size={30} className="text-sky-200" />
          </div>
          <h2 className="text-2xl font-semibold text-slate-50">Workpad stays empty until the model produces durable output.</h2>
          <p className="mt-4 text-sm leading-7 text-slate-400">
            Ask for a memo, checklist, draft, or code file and the model will open the right pane automatically.
          </p>
        </div>
      </div>
    );
  }

  const isReadOnly = status === "streaming";
  const isMarkdownArtifact = artifact.content_type === "markdown";
  const effectiveCanvasMode: CanvasMode = status === "streaming" ? "edit" : canvasMode;
  const isPreviewing = isMarkdownArtifact && effectiveCanvasMode === "preview";
  const editingDisabled = isReadOnly || isPreviewing;
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
      const response = await fetch(`${API_BASE}/api/artifacts/${currentArtifact.id}/export?format=${format}`);
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
    await refreshActiveArtifact();
  }

  return (
    <div className="panel-shell flex h-full flex-col overflow-hidden">
      <div className="border-b border-white/10 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <input
              value={artifact.title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full truncate border-0 bg-transparent text-xl font-semibold text-slate-50 outline-none"
            />
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
              <span className="text-slate-400">{artifact.content_type}</span>
              <span>·</span>
              <span>v{artifact.version}</span>
              <span>·</span>
              {artifact.dirty ? <span className="text-amber-300">Saving…</span> : <span>Saved</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isMarkdownArtifact ? (
              <div
                className={`inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] p-0.5 text-xs ${
                  isReadOnly ? "opacity-50" : ""
                }`}
              >
                <button
                  type="button"
                  onClick={() => setCanvasMode("edit")}
                  disabled={isReadOnly}
                  className={`rounded-full px-3 py-1 transition ${
                    effectiveCanvasMode === "edit"
                      ? "bg-white/10 text-slate-100"
                      : "text-slate-400 hover:text-slate-200"
                  } disabled:cursor-not-allowed`}
                  aria-pressed={effectiveCanvasMode === "edit"}
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setCanvasMode("preview")}
                  disabled={isReadOnly}
                  title={isReadOnly ? "Preview disabled while streaming" : undefined}
                  className={`rounded-full px-3 py-1 transition ${
                    effectiveCanvasMode === "preview"
                      ? "bg-white/10 text-slate-100"
                      : "text-slate-400 hover:text-slate-200"
                  } disabled:cursor-not-allowed`}
                  aria-pressed={effectiveCanvasMode === "preview"}
                >
                  Preview
                </button>
              </div>
            ) : null}
            <button
              type="button"
              onClick={toggleCanvasTheme}
              title={isLightCanvas ? "Switch canvas to dark" : "Switch canvas to light"}
              aria-label={isLightCanvas ? "Switch canvas to dark" : "Switch canvas to light"}
              className="glass-button !px-3"
            >
              {isLightCanvas ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <button
              type="button"
              onClick={handleUndo}
              disabled={!canUndo}
              title="Undo"
              aria-label="Undo"
              className="glass-button !px-3 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Undo2 size={16} />
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={!canRedo}
              title="Redo"
              aria-label="Redo"
              className="glass-button !px-3 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Redo2 size={16} />
            </button>
            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={isReadOnly}
              title="Refresh from server"
              aria-label="Refresh from server"
              className="glass-button !px-3 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <RefreshCcw size={16} />
            </button>
            {artifact.spec_type === "rfc" ? (
              <button
                type="button"
                onClick={() => void verifyActiveCitations({ force: true })}
                disabled={verify.phase === "verifying"}
                title={
                  verify.phase === "error"
                    ? verify.error?.message ?? "Verify failed - click to retry"
                    : "Check citations against the repo"
                }
                aria-label="Verify citations"
                className="glass-button !px-3 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {verify.phase === "verifying" ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : verify.phase === "error" ? (
                  <RefreshCcw size={16} className="text-rose-300" />
                ) : (
                  <RefreshCcw size={16} />
                )}
              </button>
            ) : null}
            <button type="button" onClick={() => void handleCopy()} className="glass-button">
              {copyState === "copied" ? <Check size={16} /> : <Copy size={16} />}
              {copyState === "copied" ? "Copied" : "Copy"}
            </button>
            <div className="relative" ref={downloadMenuRef}>
              <button type="button" onClick={() => setDownloadMenuOpen((open) => !open)} className="glass-button">
                <FileDown size={16} />
                {downloadingFormat ? `Downloading ${downloadingFormat.toUpperCase()}` : "Download"}
                <ChevronDown size={16} />
              </button>
              {downloadMenuOpen ? (
                <div className="absolute right-0 top-full z-20 mt-2 min-w-[180px] rounded-2xl border border-white/10 bg-chrome-900/95 p-2 shadow-panel backdrop-blur-xl">
                  <button type="button" onClick={() => void handleDownload("markdown")} className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm text-slate-100 transition hover:bg-white/10">
                    <span>Markdown</span>
                    <span className="text-xs uppercase tracking-[0.18em] text-slate-500">.md</span>
                  </button>
                  <button type="button" onClick={() => void handleDownload("docx")} className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm text-slate-100 transition hover:bg-white/10">
                    <span>Word</span>
                    <span className="text-xs uppercase tracking-[0.18em] text-slate-500">.docx</span>
                  </button>
                  <button type="button" onClick={() => void handleDownload("pdf")} className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm text-slate-100 transition hover:bg-white/10">
                    <span>PDF</span>
                    <span className="text-xs uppercase tracking-[0.18em] text-slate-500">.pdf</span>
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      <DriftBanner />
      <div className="flex-1 overflow-auto p-5">
        {artifact.content_type === "markdown" ? (
          isPreviewing ? (
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
          )
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
  const artifactLabel = `${artifactCount} ${artifactCount === 1 ? "artifact" : "artifacts"}`;

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
      className={`group relative rounded-2xl border transition ${
        active
          ? "border-sky-300/25 bg-sky-400/10"
          : "border-transparent hover:border-white/10 hover:bg-white/[0.04]"
      } ${isArchived ? "opacity-70" : ""}`}
    >
      <button
        type="button"
        onClick={() => void selectConversation(conversation.id)}
        className="block w-full rounded-2xl px-3 py-2.5 pr-9 text-left"
      >
        <div className="truncate text-sm font-medium text-slate-100">
          {conversation.title}
          {isArchived ? <span className="ml-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">archived</span> : null}
        </div>
        <div className="mt-0.5 truncate text-xs text-slate-400">
          {conversation.last_message_preview || "Fresh conversation"}
        </div>
        <div className="mt-1 text-[11px] text-slate-500">
          {artifactLabel} · {formatTimestamp(conversation.updated_at)}
        </div>
      </button>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setMenuOpen((value) => !value);
        }}
        title="Conversation actions"
        aria-label="Conversation actions"
        className={`absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition ${
          menuOpen ? "bg-white/10 text-slate-100 opacity-100" : "opacity-0 group-hover:opacity-100 hover:bg-white/10 hover:text-slate-100"
        }`}
      >
        <MoreHorizontal size={14} />
      </button>
      {menuOpen ? (
        <div className="absolute right-1.5 top-10 z-20 min-w-[160px] rounded-2xl border border-white/10 bg-chrome-900/95 p-1.5 shadow-panel backdrop-blur-xl">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setMenuOpen(false);
              void (isArchived ? unarchiveConversation(conversation.id) : archiveConversation(conversation.id));
            }}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-1.5 text-left text-sm text-slate-100 transition hover:bg-white/10"
          >
            {isArchived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
            {isArchived ? "Unarchive" : "Archive"}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-1.5 text-left text-sm text-rose-200 transition hover:bg-rose-500/15"
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Sidebar() {
  const conversations = useWorkbenchStore((state) => state.conversations);
  const activeConversationId = useWorkbenchStore((state) => state.activeConversationId);
  const startNewConversation = useWorkbenchStore((state) => state.startNewConversation);
  const showArchived = useWorkbenchStore((state) => state.showArchived);
  const setShowArchived = useWorkbenchStore((state) => state.setShowArchived);
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();

  if (collapsed) {
    return (
      <aside className="hidden h-full w-16 flex-col items-center gap-3 border-r border-white/10 bg-black/10 px-2 py-5 lg:flex">
        <button
          type="button"
          onClick={toggleCollapsed}
          title="Expand sidebar"
          aria-label="Expand sidebar"
          className="glass-button !px-3"
        >
          <PanelLeftOpen size={16} />
        </button>
        <button
          type="button"
          onClick={() => void startNewConversation()}
          title="New conversation"
          aria-label="New conversation"
          className="glass-button !px-3"
        >
          <Plus size={16} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="hidden h-full w-[272px] flex-col border-r border-white/10 bg-black/10 px-3 py-4 lg:flex">
      <div className="mb-4 flex items-center justify-between gap-2 px-1">
        <div className="text-[15px] font-semibold text-slate-50">Conversations</div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void startNewConversation()}
            title="New conversation"
            aria-label="New conversation"
            className="glass-button !px-2.5 !py-1.5"
          >
            <Plus size={14} />
          </button>
          <button
            type="button"
            onClick={toggleCollapsed}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
            className="glass-button !px-2.5 !py-1.5"
          >
            <PanelLeftClose size={14} />
          </button>
        </div>
      </div>
      <div className="-mr-1 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
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
        className="mt-3 flex items-center justify-center gap-2 rounded-full border border-transparent px-3 py-1.5 text-[11px] text-slate-500 transition hover:border-white/10 hover:bg-white/[0.04] hover:text-slate-300"
      >
        {showArchived ? <ArchiveRestore size={12} /> : <Archive size={12} />}
        {showArchived ? "Hide archived" : "Show archived"}
      </button>
    </aside>
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
        : "border-white/10 bg-white/5 text-slate-400";
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-[28px] border border-white/10 bg-chrome-900/95 p-6 shadow-panel">
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
          <div className="mt-6 rounded-2xl border border-white/10 bg-black/20 p-5">
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
              className="mt-2 w-full resize-y rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/40 focus:outline-none"
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
                className="mt-2 w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/40 focus:outline-none"
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
                className="mt-2 w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400/40 focus:outline-none"
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

function App() {
  const bootstrap = useWorkbenchStore((state) => state.bootstrap);
  const messages = useWorkbenchStore((state) => state.messages);
  const status = useWorkbenchStore((state) => state.status);
  const error = useWorkbenchStore((state) => state.error);
  const bootstrapped = useWorkbenchStore((state) => state.bootstrapped);
  const activeArtifact = useWorkbenchStore((state) => state.activeArtifact);
  const startNewConversation = useWorkbenchStore((state) => state.startNewConversation);
  const [canvasOnLeft, toggleCanvasOnLeft] = useCanvasOnLeft();
  const [newSpecOpen, setNewSpecOpen] = useState(false);
  useAutosave();
  useAutoVerifyCitations();
  useErrorToasts();

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const showWorkpad = Boolean(activeArtifact);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto px-4 py-4 sm:px-6 sm:py-6">
        {!bootstrapped && status === "loading" ? (
          <div className="flex min-h-[80vh] items-center justify-center">
            <div className="glass-button">
              <LoaderCircle className="animate-spin" size={16} />
              Loading workspace…
            </div>
          </div>
        ) : (
          <div className="mx-auto h-[calc(100vh-2rem)] max-w-[1680px]">
            {!showWorkpad ? (
              <div className="flex h-full flex-col gap-6">
                <div className="flex items-center justify-between px-2 pt-2">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                      <MessageSquareText size={20} className="text-sky-200" />
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Chat Workspace</div>
                      <div className="mt-1 text-lg font-semibold text-slate-50">Workpad AI</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setNewSpecOpen(true)}
                      className="glass-button"
                    >
                      <NotebookPen size={16} />
                      New RFC
                    </button>
                    <button type="button" onClick={() => void startNewConversation()} className="glass-button">
                      <Plus size={16} />
                      New thread
                    </button>
                  </div>
                </div>

                {messages.length === 0 ? (
                  <div className="flex flex-1 items-center justify-center">
                    <div className="w-full text-center">
                      <p className="mb-6 text-sm uppercase tracking-[0.3em] text-slate-500">Modern AI Work Surface</p>
                      <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight text-slate-50 sm:text-6xl">
                        What should we draft, edit, or build today?
                      </h1>
                      <p className="mx-auto mt-6 max-w-2xl text-base leading-8 text-slate-400">
                        Chat stays conversational. The workpad opens the moment the response deserves to persist.
                      </p>
                      <div className="mt-10">
                        <ChatComposer centered />
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="panel-shell flex-1 overflow-hidden p-5">
                      <div className="h-full overflow-auto pr-2">
                        <div className="mx-auto max-w-4xl space-y-6">
                          {renderMessageList(messages)}
                        </div>
                      </div>
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
                  <Panel key="chat" order={canvasOnLeft ? 2 : 1} defaultSize={34} minSize={28}>
                    <div className="flex h-full flex-col gap-4">
                      <div className="panel-shell flex-1 overflow-hidden p-5">
                        <div className="flex h-full flex-col">
                          <div className="mb-4 flex items-center justify-between">
                            <div className="text-lg font-semibold text-slate-50">Chat</div>
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={toggleCanvasOnLeft}
                                title={canvasOnLeft ? "Move canvas to the right" : "Move canvas to the left"}
                                aria-label={canvasOnLeft ? "Move canvas to the right" : "Move canvas to the left"}
                                className="glass-button !px-3"
                              >
                                <ArrowLeftRight size={16} />
                              </button>
                              <button
                                type="button"
                                onClick={() => setNewSpecOpen(true)}
                                title="New RFC"
                                aria-label="New RFC"
                                className="glass-button !px-3"
                              >
                                <NotebookPen size={16} />
                              </button>
                              <button
                                type="button"
                                onClick={() => void startNewConversation()}
                                title="New thread"
                                aria-label="New thread"
                                className="glass-button !px-3"
                              >
                                <Plus size={16} />
                              </button>
                            </div>
                          </div>
                          <div className="flex-1 overflow-auto pr-2">
                            <div className="space-y-6">
                              {renderMessageList(messages)}
                            </div>
                          </div>
                        </div>
                      </div>
                      <ChatComposer />
                    </div>
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
                      <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 rounded-full bg-white/10" />
                    </PanelResizeHandle>
                    {panels[1]}
                  </PanelGroup>
                );
              })()
            )}
            {error ? (
              <div className="pointer-events-none fixed bottom-5 right-5 max-w-sm rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {error}
              </div>
            ) : null}
            {status === "streaming" ? (
              <div className="pointer-events-none fixed bottom-5 left-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/40 px-4 py-2 text-xs uppercase tracking-[0.22em] text-slate-300 backdrop-blur-xl">
                <LoaderCircle className="animate-spin" size={14} />
                Streaming
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
