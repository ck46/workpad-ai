// Library home — the default view when no artifact is open. Fetches
// /api/library/artifacts (scoped to the current user by the backend) and
// renders the editorial "Library" surface from the design system:
// greeting hero, recently opened tiles, type-filtered all-artifacts list.

import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  History,
  LayoutGrid,
  List,
  Plus,
  Sparkles,
} from "lucide-react";
import { useAuth } from "../lib/auth";

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

type ArtifactListItem = {
  id: string;
  conversation_id: string;
  origin_conversation_id: string | null;
  title: string;
  content_type: string;
  version: number;
  artifact_type: string | null;
  updated_at: string;
  last_opened_at: string | null;
  summary: string;
  status: string;
  spec_type: string | null;
};

const TYPE_LABEL: Record<string, string> = {
  rfc: "RFC",
  adr: "ADR",
  design_note: "Design note",
  run_note: "Run note",
};

const TYPE_FILTERS: Array<{ id: string; label: string }> = [
  { id: "all", label: "All" },
  { id: "rfc", label: "RFCs" },
  { id: "adr", label: "ADRs" },
  { id: "design_note", label: "Design notes" },
  { id: "run_note", label: "Run notes" },
];

function timeSince(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Up late";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function artifactStamp(a: ArtifactListItem): string {
  const type = (a.artifact_type || a.spec_type || a.content_type || "pad").toUpperCase();
  return `${type}-${a.id.slice(0, 6)}`;
}

function shortType(a: ArtifactListItem): string {
  const t = a.artifact_type || a.spec_type;
  return t ? (TYPE_LABEL[t] ?? t).toUpperCase() : a.content_type.toUpperCase();
}

export function LibraryHome({
  projectId,
  onOpen,
  onNew,
  onDraftAI,
  onContinueLast,
}: {
  projectId: string | null;
  onOpen: (artifact: ArtifactListItem) => void;
  onNew: () => void;
  onDraftAI: () => void;
  onContinueLast: () => void;
}) {
  const { user } = useAuth();
  const [items, setItems] = useState<ArtifactListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [view, setView] = useState<"list" | "grid">("list");

  useEffect(() => {
    if (!projectId) {
      setItems([]);
      return;
    }
    let alive = true;
    (async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/library/artifacts?project_id=${encodeURIComponent(projectId)}&limit=200`,
          { credentials: "include" },
        );
        if (!response.ok) {
          throw new Error(`Library fetch failed (${response.status})`);
        }
        const data = (await response.json()) as ArtifactListItem[];
        if (alive) setItems(data);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Could not load the library.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

  const firstName = user?.name?.trim().split(/\s+/)[0] || user?.email?.split("@")[0] || "there";

  const filtered = useMemo(() => {
    if (!items) return [];
    if (filter === "all") return items;
    return items.filter((a) => (a.artifact_type || a.spec_type) === filter);
  }, [items, filter]);

  const recent = useMemo(() => {
    if (!items) return [];
    return [...items]
      .sort(
        (a, b) =>
          new Date(b.last_opened_at || b.updated_at).getTime() -
          new Date(a.last_opened_at || a.updated_at).getTime(),
      )
      .slice(0, 4);
  }, [items]);

  const totalArtifacts = items?.length ?? 0;
  const draftCount = items?.filter((a) => a.status === "draft").length ?? 0;

  return (
    <div className="mx-auto max-w-[1200px] px-6 pb-20 pt-10 sm:px-8">
      <section className="mb-9">
        <div className="wp-overline mb-2.5">Library</div>
        <h1
          className="m-0 font-serif font-medium text-ink-1"
          style={{ fontSize: 44, letterSpacing: "-0.02em", lineHeight: 1.1 }}
        >
          {greeting()}, {firstName}.
        </h1>
        <p className="mt-2 max-w-[56ch] text-[15px] text-ink-2">
          {totalArtifacts === 0 ? (
            <>No pads yet. Draft your first from a repo and transcript, or start writing manually.</>
          ) : (
            <>
              {totalArtifacts} {totalArtifacts === 1 ? "pad" : "pads"}
              {draftCount ? <> · {draftCount} in draft</> : null}
              .
            </>
          )}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onNew}
            className="inline-flex items-center gap-2 rounded-md bg-signal px-4 py-2 text-[13px] font-medium text-white transition hover:bg-signal-hover"
          >
            <Plus size={14} />
            New pad
          </button>
          <button
            type="button"
            onClick={onDraftAI}
            className="inline-flex items-center gap-2 rounded-md border border-shell-border-strong bg-shell-1 px-4 py-2 text-[13px] font-medium text-ink-1 transition hover:bg-shell-2"
          >
            <Sparkles size={14} />
            Draft with AI
          </button>
          <button
            type="button"
            onClick={onContinueLast}
            className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-[13px] font-medium text-ink-2 transition hover:bg-shell-2 hover:text-ink-1"
          >
            <History size={14} />
            Continue last thread
          </button>
        </div>
      </section>

      {error ? (
        <div className="mb-8 rounded-md border border-state-missing-soft bg-state-missing-soft px-3 py-2 text-[12.5px] text-state-missing-ink">
          {error}
        </div>
      ) : null}

      {recent.length > 0 ? (
        <section className="mb-11">
          <div className="mb-3.5 flex items-baseline gap-3">
            <h2 className="text-[15px] font-semibold tracking-tight text-ink-1">Recently opened</h2>
            <span className="font-mono text-[11px] text-ink-3">within 24h</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {recent.map((a) => (
              <RecentTile key={a.id} a={a} onClick={() => onOpen(a)} />
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <div className="mb-3.5 flex items-center gap-3">
          <h2 className="text-[15px] font-semibold tracking-tight text-ink-1">All pads</h2>
          <div className="ml-auto inline-flex items-center gap-0.5 rounded-md bg-shell-2 p-0.5">
            {(
              [
                { id: "list", icon: <List size={12} /> },
                { id: "grid", icon: <LayoutGrid size={12} /> },
              ] as const
            ).map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => setView(v.id)}
                className={`inline-flex items-center gap-1 rounded px-2 py-1 font-mono text-[11px] transition ${
                  view === v.id
                    ? "bg-shell-1 text-ink-1 shadow-sm"
                    : "text-ink-3 hover:text-ink-2"
                }`}
                aria-pressed={view === v.id}
              >
                {v.icon}
                {v.id}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-3.5 flex flex-wrap items-center gap-1.5">
          {TYPE_FILTERS.map((t) => {
            const count =
              t.id === "all"
                ? items?.length ?? 0
                : items?.filter((a) => (a.artifact_type || a.spec_type) === t.id).length ?? 0;
            const active = filter === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setFilter(t.id)}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] font-medium transition ${
                  active
                    ? "border-ink-1 bg-ink-1 text-white"
                    : "border-shell-border-strong text-ink-2 hover:bg-shell-2 hover:text-ink-1"
                }`}
              >
                {t.label}
                <span className={`font-mono text-[10px] ${active ? "opacity-80" : "opacity-60"}`}>
                  {count}
                </span>
              </button>
            );
          })}
          <span className="ml-auto font-mono text-[12px] text-ink-3">
            Sorted by updated ↓
          </span>
        </div>

        {items === null ? (
          <div className="rounded-lg border border-shell-border bg-shell-1 px-5 py-12 text-center font-mono text-[12px] text-ink-3">
            loading library…
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-lg border border-shell-border bg-shell-1 px-5 py-12 text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-md border border-shell-border bg-shell-2">
              <Archive size={16} className="text-ink-3" />
            </div>
            <div className="mb-1 font-serif text-[18px] font-medium text-ink-1">
              Nothing here yet.
            </div>
            <div className="text-[13px] text-ink-2">
              Create a new pad or switch the filter to see everything.
            </div>
          </div>
        ) : view === "list" ? (
          <div className="overflow-hidden rounded-lg border border-shell-border bg-shell-1">
            {filtered.map((a, i) => (
              <ArtifactRow
                key={a.id}
                a={a}
                divider={i < filtered.length - 1}
                onClick={() => onOpen(a)}
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {filtered.map((a) => (
              <ArtifactCard key={a.id} a={a} onClick={() => onOpen(a)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RecentTile({ a, onClick }: { a: ArtifactListItem; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col gap-2 rounded-lg border border-paper-border bg-paper-0 p-3.5 text-left transition hover:border-paper-border-strong"
    >
      <div className="flex items-center gap-1.5">
        <TypeChip type={shortType(a)} />
        <span
          className="font-mono text-[10px] font-medium uppercase tracking-[0.06em]"
          style={{ color: "var(--paper-ink-3)" }}
        >
          {artifactStamp(a)} · v{a.version}
        </span>
      </div>
      <div
        className="font-serif text-[17px] font-medium leading-tight text-paper-ink"
        style={{ letterSpacing: "-0.005em", textWrap: "pretty" }}
      >
        {a.title || "Untitled pad"}
      </div>
      <div
        className="mt-auto flex items-center gap-2 font-mono text-[11px]"
        style={{ color: "var(--paper-ink-3)" }}
      >
        <span>{a.status}</span>
        <span>·</span>
        <span>{timeSince(a.updated_at)}</span>
      </div>
    </button>
  );
}

function ArtifactRow({
  a,
  divider,
  onClick,
}: {
  a: ArtifactListItem;
  divider: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`grid w-full grid-cols-[68px_1fr_120px_100px] items-center gap-4 px-5 py-3.5 text-left transition hover:bg-shell-2 ${
        divider ? "border-b border-shell-border" : ""
      }`}
    >
      <TypeChip type={shortType(a)} />
      <div className="min-w-0">
        <div className="mb-0.5 flex items-center gap-2">
          <span className="wp-stamp">
            {artifactStamp(a)} · v{a.version}
          </span>
          {a.status !== "active" && a.status !== "draft" ? (
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
              {a.status}
            </span>
          ) : null}
        </div>
        <div
          className="truncate text-[14px] font-medium text-ink-1"
          style={{ letterSpacing: "-0.005em" }}
        >
          {a.title || "Untitled pad"}
        </div>
      </div>
      <div className="truncate font-mono text-[11.5px] text-ink-2">{a.content_type}</div>
      <div className="text-right font-mono text-[11px] text-ink-3">
        {timeSince(a.updated_at)}
      </div>
    </button>
  );
}

function ArtifactCard({ a, onClick }: { a: ArtifactListItem; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col gap-2.5 rounded-lg border border-shell-border bg-shell-1 p-4 text-left transition hover:border-shell-border-strong"
    >
      <div className="flex items-center gap-1.5">
        <TypeChip type={shortType(a)} />
        <span className="wp-stamp">
          {artifactStamp(a)} · v{a.version}
        </span>
        <span
          className={`ml-auto h-1.5 w-1.5 rounded-full ${
            a.status === "active"
              ? "bg-state-live"
              : a.status === "archived"
                ? "bg-ink-3"
                : "bg-state-stale"
          }`}
        />
      </div>
      <div
        className="text-[15px] font-semibold leading-tight text-ink-1"
        style={{ letterSpacing: "-0.01em", textWrap: "pretty" }}
      >
        {a.title || "Untitled pad"}
      </div>
      {a.summary ? (
        <div
          className="line-clamp-2 font-serif text-[13px] leading-relaxed text-ink-2"
          style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
        >
          {a.summary}
        </div>
      ) : null}
      <div className="mt-auto flex items-center gap-2 font-mono text-[11px] text-ink-3">
        <span>{a.content_type}</span>
        <span>·</span>
        <span>{timeSince(a.updated_at)}</span>
      </div>
    </button>
  );
}

function TypeChip({ type }: { type: string }) {
  return (
    <span
      className="inline-flex items-center rounded border border-paper-border-strong bg-paper-1 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase"
      style={{ letterSpacing: "0.08em", color: "var(--paper-ink-2)" }}
    >
      {type}
    </span>
  );
}

export type { ArtifactListItem };
