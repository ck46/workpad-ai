// Side-by-side summary + unified diff between two artifact versions.
// Backend returns unified-diff text from difflib; we tokenize it into
// colored lines (add / remove / context / hunk header).
//
// Lives on its own paper surface so the reader stays in an editorial
// reading flow: stamp row at top, then the diff as a mono block.

import { useEffect, useState } from "react";

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

type DiffResponse = {
  artifact_id: string;
  from_version: number;
  to_version: number;
  from_title: string;
  to_title: string;
  unified_diff: string;
  added_lines: number;
  removed_lines: number;
  available_versions: number[];
};

type Row =
  | { kind: "header"; text: string }
  | { kind: "hunk"; text: string }
  | { kind: "add"; text: string }
  | { kind: "del"; text: string }
  | { kind: "ctx"; text: string };

function tokenize(diff: string): Row[] {
  if (!diff) return [];
  const rows: Row[] = [];
  for (const line of diff.split("\n")) {
    if (line.startsWith("+++") || line.startsWith("---")) {
      rows.push({ kind: "header", text: line });
    } else if (line.startsWith("@@")) {
      rows.push({ kind: "hunk", text: line });
    } else if (line.startsWith("+")) {
      rows.push({ kind: "add", text: line.slice(1) });
    } else if (line.startsWith("-")) {
      rows.push({ kind: "del", text: line.slice(1) });
    } else {
      rows.push({ kind: "ctx", text: line.startsWith(" ") ? line.slice(1) : line });
    }
  }
  return rows;
}

export function ArtifactDiffView({
  artifactId,
  latestVersion,
  canvasTheme = "light",
}: {
  artifactId: string;
  latestVersion: number;
  canvasTheme?: "light" | "dark";
}) {
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toVersion, setToVersion] = useState<number>(latestVersion);
  const [fromVersion, setFromVersion] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    const params = new URLSearchParams();
    if (fromVersion !== null) params.set("from_version", String(fromVersion));
    if (toVersion !== null) params.set("to_version", String(toVersion));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    (async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/artifacts/${artifactId}/diff${suffix}`,
          { credentials: "include" },
        );
        if (!response.ok) {
          throw new Error(`Diff failed (${response.status})`);
        }
        const data = (await response.json()) as DiffResponse;
        if (alive) setDiff(data);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Could not compute diff.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [artifactId, fromVersion, toVersion]);

  const rows = diff ? tokenize(diff.unified_diff) : [];

  return (
    <article
      className={`paper mx-auto max-w-[900px] rounded-lg border border-paper-border bg-paper-0 px-10 py-10 shadow-none ${canvasTheme === "dark" ? "paper-dark" : ""}`}
    >
      <header className="mb-5 flex flex-wrap items-center gap-3 border-b border-paper-border pb-4">
        <div className="wp-stamp" style={{ color: "var(--paper-ink-3)" }}>
          DIFF · v{diff?.from_version ?? "—"} → v{diff?.to_version ?? latestVersion}
        </div>
        <div className="ml-auto flex items-center gap-2 font-mono text-[11px]">
          <span className="inline-flex items-center gap-1 rounded border border-state-live-soft bg-state-live-soft px-1.5 py-0.5 text-state-live-ink">
            +{diff?.added_lines ?? 0}
          </span>
          <span className="inline-flex items-center gap-1 rounded border border-state-missing-soft bg-state-missing-soft px-1.5 py-0.5 text-state-missing-ink">
            −{diff?.removed_lines ?? 0}
          </span>
        </div>
        <div className="flex w-full items-center gap-2 font-mono text-[11px]" style={{ color: "var(--paper-ink-3)" }}>
          <span>Compare</span>
          <VersionPicker
            label="from"
            value={fromVersion}
            versions={diff?.available_versions ?? []}
            onChange={setFromVersion}
          />
          <span>→</span>
          <VersionPicker
            label="to"
            value={toVersion}
            versions={diff?.available_versions ?? []}
            onChange={(v) => setToVersion(v ?? latestVersion)}
          />
        </div>
      </header>
      {error ? (
        <div className="rounded-md border border-state-missing-soft bg-state-missing-soft px-3 py-2 font-mono text-[12px] text-state-missing-ink">
          {error}
        </div>
      ) : !diff ? (
        <div className="font-mono text-[12px]" style={{ color: "var(--paper-ink-3)" }}>
          computing diff…
        </div>
      ) : rows.length === 0 || !diff.unified_diff.trim() ? (
        <div className="rounded-md border border-paper-border bg-paper-1 px-4 py-4 font-mono text-[12.5px]" style={{ color: "var(--paper-ink-2)" }}>
          No changes between v{diff.from_version} and v{diff.to_version}.
        </div>
      ) : (
        <div
          className="overflow-x-auto rounded-md border border-paper-border bg-paper-1 font-mono text-[12.5px] leading-[1.55]"
          style={{ color: "var(--paper-ink)" }}
        >
          <div className="min-w-max">
            {rows.map((row, i) => (
              <DiffRow key={i} row={row} />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function DiffRow({ row }: { row: Row }) {
  let bg = "transparent";
  let fg = "var(--paper-ink)";
  let sign = "\u00A0\u00A0";
  if (row.kind === "add") {
    bg = "var(--state-live-soft)";
    fg = "var(--state-live-ink)";
    sign = "+\u00A0";
  } else if (row.kind === "del") {
    bg = "var(--state-missing-soft)";
    fg = "var(--state-missing-ink)";
    sign = "−\u00A0";
  } else if (row.kind === "hunk") {
    bg = "var(--shell-2)";
    fg = "var(--ink-2)";
    sign = "\u00A0\u00A0";
  } else if (row.kind === "header") {
    bg = "var(--shell-2)";
    fg = "var(--ink-3)";
    sign = "\u00A0\u00A0";
  } else {
    fg = "var(--paper-ink-2)";
  }
  return (
    <div className="flex whitespace-pre" style={{ background: bg, color: fg }}>
      <span
        aria-hidden
        className="select-none pl-3 pr-2"
        style={{ color: "var(--paper-ink-3)" }}
      >
        {sign}
      </span>
      <span className="flex-1 pr-4">{row.text || "\u00A0"}</span>
    </div>
  );
}

function VersionPicker({
  label,
  value,
  versions,
  onChange,
}: {
  label: string;
  value: number | null;
  versions: number[];
  onChange: (v: number | null) => void;
}) {
  const options: Array<{ value: number | null; label: string }> = [
    { value: null, label: `previous (${label})` },
    ...[...new Set(versions)].sort((a, b) => b - a).map((v) => ({ value: v, label: `v${v}` })),
  ];
  return (
    <select
      value={value === null ? "" : String(value)}
      onChange={(e) => {
        const raw = e.target.value;
        onChange(raw === "" ? null : Number(raw));
      }}
      className="rounded border border-paper-border-strong bg-paper-0 px-2 py-0.5 font-mono text-[11px] outline-none"
      style={{ color: "var(--paper-ink)" }}
    >
      {options.map((opt, i) => (
        <option key={i} value={opt.value === null ? "" : String(opt.value)}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
