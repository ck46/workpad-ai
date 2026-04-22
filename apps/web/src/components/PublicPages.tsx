// Marketing, sign-in, and sign-up surfaces.
// These are presentational only — there is no backend for auth in v1.
// Forms submit client-side and navigate back to the app. Shared components
// live here because they're small and referenced from exactly one place.

import { useState } from "react";
import { ArrowLeft, ArrowRight, Github, LoaderCircle } from "lucide-react";
import { signIn, signUp, type AuthUser } from "../lib/auth";

type Route = "marketing" | "signin" | "signup" | "forgot";

type Nav = (route: Route | "app") => void;

export function Wordmark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
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

function GoogleGlyph({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
      <path
        fill="currentColor"
        d="M21.35 11.1H12v3.21h5.35c-.23 1.4-1.67 4.11-5.35 4.11-3.22 0-5.85-2.67-5.85-5.95s2.63-5.95 5.85-5.95c1.83 0 3.06.78 3.76 1.45l2.57-2.48C16.77 4.16 14.62 3 12 3 7.03 3 3 7.03 3 12s4.03 9 9 9c5.2 0 8.65-3.65 8.65-8.79 0-.59-.06-1.04-.13-1.49z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Marketing
// ---------------------------------------------------------------------------

export function MarketingPage({
  nav,
  isAuthed = false,
}: {
  nav: Nav;
  isAuthed?: boolean;
}) {
  return (
    <div className="min-h-screen bg-shell-0 text-ink-1">
      <MarketingNav nav={nav} isAuthed={isAuthed} />
      <MarketingHero nav={nav} isAuthed={isAuthed} />
      <ArtifactDemoPanel />
      <MarketingFeatures />
      <MarketingTypes />
      <MarketingCTA nav={nav} isAuthed={isAuthed} />
      <MarketingFooter />
    </div>
  );
}

function MarketingNav({ nav, isAuthed }: { nav: Nav; isAuthed: boolean }) {
  return (
    <nav
      className="sticky top-0 z-10 border-b border-shell-border"
      style={{ background: "rgba(247,247,245,0.85)", backdropFilter: "blur(12px)" }}
    >
      <div className="mx-auto flex max-w-[1200px] items-center gap-6 px-6 py-3.5 sm:px-8">
        <a href="#/marketing" onClick={(e) => { e.preventDefault(); nav("marketing"); }}>
          <Wordmark />
        </a>
        <div className="hidden items-center gap-5 md:flex" style={{ marginLeft: 24 }}>
          {["Product", "Changelog", "Docs", "Pricing"].map((l) => (
            <a key={l} href="#" className="text-[13px] text-ink-2 no-underline hover:text-ink-1">
              {l}
            </a>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {isAuthed ? (
            <button
              type="button"
              onClick={() => nav("app")}
              className="inline-flex items-center gap-1.5 rounded-md bg-ink-1 px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-black"
            >
              Open workspace
              <ArrowRight size={13} />
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={() => nav("signin")}
                className="rounded-md px-2.5 py-1.5 text-[12.5px] text-ink-2 hover:bg-shell-2 hover:text-ink-1"
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => nav("signup")}
                className="inline-flex items-center gap-1.5 rounded-md bg-ink-1 px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-black"
              >
                Get started
                <ArrowRight size={13} />
              </button>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

function MarketingHero({ nav, isAuthed }: { nav: Nav; isAuthed: boolean }) {
  return (
    <section className="relative mx-auto max-w-[1200px] px-6 pb-10 pt-20 sm:px-8">
      <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-1 px-3 py-1 font-mono text-[12px] text-ink-2">
        <span
          className="wp-pulse inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: "var(--accent-signal)" }}
        />
        Workpad is in private beta · April 2026
      </div>
      <h1
        className="m-0 max-w-[14ch] font-serif font-medium text-ink-1"
        style={{
          fontSize: "clamp(48px, 7vw, 92px)",
          letterSpacing: "-0.03em",
          lineHeight: 1.02,
          textWrap: "balance",
        }}
      >
        An engineering memory for{" "}
        <em className="italic" style={{ color: "var(--accent-signal)" }}>
          what you decided
        </em>{" "}
        and why.
      </h1>
      <p
        className="m-0 mb-8 mt-6 max-w-[60ch] text-[19px] leading-[1.5] text-ink-2"
        style={{ textWrap: "pretty" }}
      >
        Workpad is a personal workspace for source-grounded pads. Draft RFCs, ADRs,
        design notes, and run notes against your actual repo, with citations that stay
        live as the code moves.
      </p>
      <div className="flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          onClick={() => nav(isAuthed ? "app" : "signup")}
          className="inline-flex items-center gap-2 rounded-md bg-signal px-5 py-3 text-[15px] font-medium text-white transition hover:bg-signal-hover"
        >
          {isAuthed ? "Open workspace" : "Start a workspace"}
          <ArrowRight size={16} />
        </button>
        {!isAuthed ? (
          <button
            type="button"
            onClick={() => nav("signin")}
            className="inline-flex items-center gap-2 rounded-md border border-shell-border-strong bg-shell-1 px-5 py-3 text-[15px] font-medium text-ink-1 transition hover:bg-shell-2"
          >
            Sign in
          </button>
        ) : null}
      </div>
      <div className="mt-5 font-mono text-[12px] text-ink-3">
        Free during beta · No credit card · One workspace per person
      </div>
    </section>
  );
}

function ArtifactDemoPanel() {
  return (
    <section className="mx-auto my-14 max-w-[1200px] px-6 sm:px-8">
      <div className="relative rounded-[20px] bg-ink-1 p-6">
        <div className="mb-4 flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#44474F" }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#44474F" }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#44474F" }} />
          <span
            className="ml-auto font-mono text-[11px]"
            style={{ color: "rgba(236,236,234,0.5)" }}
          >
            workpad.ai/rfc/0042
          </span>
        </div>
        <div
          className="grid gap-3.5"
          style={{ gridTemplateColumns: "220px 1fr 260px", height: 520 }}
        >
          <div
            className="rounded-xl p-3"
            style={{ background: "#14161A", border: "1px solid #1F2128" }}
          >
            <div
              className="px-1.5 pb-2 pt-1 font-semibold uppercase"
              style={{
                fontSize: 10,
                color: "rgba(236,236,234,0.45)",
                letterSpacing: "0.14em",
              }}
            >
              Library
            </div>
            {["RFC-0042", "ADR-0018", "DN-0007", "RUN-0031"].map((n, i) => (
              <div
                key={n}
                className="mb-0.5 rounded px-2 py-2 font-mono text-[12px]"
                style={{
                  color: i === 0 ? "#fff" : "rgba(236,236,234,0.55)",
                  background: i === 0 ? "rgba(216,90,30,0.15)" : "transparent",
                  borderLeft:
                    i === 0
                      ? "2px solid var(--accent-signal)"
                      : "2px solid transparent",
                }}
              >
                {n}
              </div>
            ))}
          </div>
          <div
            className="paper overflow-hidden rounded-xl"
            style={{ background: "var(--paper-0)", padding: "36px 44px" }}
          >
            <div className="mb-3.5 flex items-center gap-1.5">
              <span
                className="inline-flex items-center rounded border border-paper-border-strong bg-paper-1 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase"
                style={{ letterSpacing: "0.08em", color: "var(--paper-ink-2)" }}
              >
                RFC
              </span>
              <span
                className="wp-stamp"
                style={{ color: "var(--paper-ink-3)" }}
              >
                RFC-0042 · v7 · live
              </span>
            </div>
            <h2
              className="m-0 mb-5 font-serif font-medium"
              style={{
                fontSize: 32,
                letterSpacing: "-0.02em",
                lineHeight: 1.15,
                color: "var(--paper-ink)",
              }}
            >
              Rate limiting at the edge: per-token vs. per-IP
            </h2>
            <p
              className="m-0 mb-3.5 font-serif"
              style={{ fontSize: 15, lineHeight: 1.65, color: "var(--paper-ink)" }}
            >
              Our edge gateway currently throttles by source IP. After the API program
              launched in Q1, ~73% of calls arrive from a small set of partner egress IPs
              — one noisy tenant pushes another over the limit.
            </p>
            <p
              className="m-0 font-serif"
              style={{ fontSize: 15, lineHeight: 1.65, color: "var(--paper-ink)" }}
            >
              We propose pinning limits to tokens. Implementation lives in{" "}
              <span
                className="font-mono"
                style={{
                  background: "var(--accent-signal-soft)",
                  borderBottom: "1.5px solid var(--accent-signal)",
                  padding: "0 3px",
                  fontSize: "0.92em",
                }}
              >
                ratelimit.ts:142
              </span>
              .
            </p>
          </div>
          <div
            className="rounded-xl p-3.5"
            style={{
              background: "#14161A",
              border: "1px solid #1F2128",
              color: "#ECECEA",
            }}
          >
            <div
              className="mb-2.5 font-semibold uppercase"
              style={{
                fontSize: 10,
                color: "rgba(236,236,234,0.45)",
                letterSpacing: "0.14em",
              }}
            >
              Citations · 14
            </div>
            {[
              ["api/ratelimit.ts:142", "live"],
              ["api/tokens.ts:88", "stale"],
              ["ADR-0018 §Decision", "live"],
              ["notes/gateway.md", "live"],
              ["core/middleware.ts:11", "missing"],
            ].map(([p, s]) => (
              <div
                key={p}
                className="mb-1 flex items-center gap-2 rounded px-2.5 py-1.5"
                style={{ background: "#1C1F25" }}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{
                    background:
                      s === "live"
                        ? "var(--state-live)"
                        : s === "stale"
                          ? "var(--state-stale)"
                          : "var(--state-missing)",
                  }}
                />
                <span
                  className="flex-1 truncate font-mono text-[11px]"
                >
                  {p}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketingFeatures() {
  const feats = [
    {
      k: "Library-first",
      t: "Your library, not your chat history.",
      d: "Pads are the primary object. Threads exist, but they're how you drive AI — not how you find work you did last month.",
    },
    {
      k: "Source-grounded",
      t: "Citations that stay live.",
      d: "Every citation is pinned to a specific repo, path, and line range. When the code moves, we tell you. When it disappears, we tell you that too.",
    },
    {
      k: "Editorial",
      t: "A paper for each pad.",
      d: "RFCs, ADRs, design notes, run notes — each with its own surface, status model, and revision history. Built for re-reading, not just writing.",
    },
    {
      k: "Ask across",
      t: "Synthesis beats search.",
      d: "Ask a question across your whole library. Get an answer grounded in the pads you already wrote, with inline citations you can click through.",
    },
  ];
  return (
    <section className="mx-auto my-14 max-w-[1200px] px-6 sm:px-8">
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {feats.map((f) => (
          <div
            key={f.k}
            className="rounded-2xl border border-shell-border bg-shell-1 px-7 py-7"
          >
            <div className="wp-overline mb-3.5">{f.k}</div>
            <h3
              className="m-0 mb-2 font-serif font-medium"
              style={{ fontSize: 26, letterSpacing: "-0.015em", lineHeight: 1.2 }}
            >
              {f.t}
            </h3>
            <p className="m-0 text-[14px] leading-[1.55] text-ink-2">{f.d}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function MarketingTypes() {
  const types = [
    { k: "RFC", n: "0042", t: "Proposals with a decision attached." },
    { k: "ADR", n: "0018", t: "What you chose, and what you weighed." },
    { k: "DN", n: "0007", t: "Loose design writing. A thought, a pattern." },
    { k: "RUN", n: "0031", t: "A timestamped log of a run of work." },
  ];
  return (
    <section className="mx-auto my-20 max-w-[1200px] px-6 sm:px-8">
      <div className="wp-overline mb-2.5">Four pad types</div>
      <h2
        className="m-0 mb-9 max-w-[18ch] font-serif font-medium text-ink-1"
        style={{ fontSize: 44, letterSpacing: "-0.02em", textWrap: "balance" }}
      >
        One format per kind of thinking.
      </h2>
      <div className="grid grid-cols-2 overflow-hidden rounded-2xl border border-shell-border bg-shell-1 md:grid-cols-4">
        {types.map((t, i) => (
          <div
            key={t.k}
            className="p-6"
            style={{
              borderRight: i < 3 ? "1px solid var(--shell-border)" : "none",
            }}
          >
            <div className="mb-1.5 font-mono text-[11px] text-ink-3">
              {t.k}-{t.n}
            </div>
            <div
              className="mb-2.5 font-serif font-medium"
              style={{ fontSize: 28, letterSpacing: "-0.015em", lineHeight: 1.2 }}
            >
              {t.k}
            </div>
            <p className="m-0 text-[13px] leading-[1.5] text-ink-2">{t.t}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function MarketingCTA({ nav, isAuthed }: { nav: Nav; isAuthed: boolean }) {
  return (
    <section className="mx-auto my-20 max-w-[1200px] px-6 sm:px-8">
      <div
        className="relative overflow-hidden rounded-2xl bg-ink-1 px-10 py-14 text-center"
        style={{ color: "#ECECEA" }}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(circle at 90% 10%, rgba(216,90,30,0.22), transparent 40%)",
          }}
        />
        <div className="relative">
          <div
            className="mb-3 font-mono text-[11px] uppercase"
            style={{ color: "rgba(236,236,234,0.5)", letterSpacing: "0.14em" }}
          >
            Start drafting
          </div>
          <h2
            className="m-0 font-serif font-medium"
            style={{ fontSize: 48, letterSpacing: "-0.02em", lineHeight: 1.05 }}
          >
            Living specs for engineering teams.
          </h2>
          <div className="mt-6 flex flex-wrap justify-center gap-2.5">
            <button
              type="button"
              onClick={() => nav(isAuthed ? "app" : "signup")}
              className="inline-flex items-center gap-2 rounded-md bg-signal px-5 py-3 text-[14px] font-medium text-white transition hover:bg-signal-hover"
            >
              {isAuthed ? "Open workspace" : "Start a workspace"}
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketingFooter() {
  return (
    <footer
      className="mt-20 border-t border-shell-border bg-shell-1 px-6 py-12 sm:px-8"
    >
      <div className="mx-auto grid max-w-[1200px] grid-cols-2 gap-6 md:grid-cols-4">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-[28ch] font-mono text-[12px] text-ink-3">
            Engineering memory, built for one person at a time.
          </p>
        </div>
        {(
          [
            ["Product", ["Library", "Threads", "Ask", "Changelog"]],
            ["Company", ["About", "Security", "Careers"]],
            ["Legal", ["Terms", "Privacy", "Contact"]],
          ] as const
        ).map(([h, items]) => (
          <div key={h}>
            <div className="wp-overline mb-3">{h}</div>
            {items.map((i) => (
              <div key={i} className="mb-1.5 text-[13px]">
                <a href="#" className="text-ink-2 no-underline hover:text-ink-1">
                  {i}
                </a>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="mx-auto mt-8 flex max-w-[1200px] justify-between border-t border-shell-border pt-5 font-mono text-[11px] text-ink-3">
        <span>© 2026 Workpad AI</span>
        <span>v0.8.2 · built against main@a3f91c2</span>
      </div>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

type AuthVariant = "signin" | "signup" | "forgot";

export function AuthPage({
  variant,
  nav,
  onAuthenticated,
}: {
  variant: AuthVariant;
  nav: Nav;
  onAuthenticated: (user: AuthUser) => void;
}) {
  return (
    <div className="grid min-h-screen bg-shell-0 md:grid-cols-2">
      <div className="flex min-h-screen flex-col px-8 py-8 sm:px-12">
        <a
          href="#/marketing"
          onClick={(e) => {
            e.preventDefault();
            nav("marketing");
          }}
        >
          <Wordmark />
        </a>
        <div className="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center">
          {variant === "signin" ? (
            <SignInView nav={nav} onAuthenticated={onAuthenticated} />
          ) : variant === "signup" ? (
            <SignUpView nav={nav} onAuthenticated={onAuthenticated} />
          ) : (
            <ForgotView nav={nav} />
          )}
        </div>
        <div className="flex justify-between font-mono text-[11px] text-ink-3">
          <span>© 2026 Workpad AI</span>
          <span>
            {variant === "signin"
              ? "Need an account?"
              : variant === "signup"
                ? "Have an account?"
                : "Reset link expires in 30 min"}
          </span>
        </div>
      </div>
      <AuthManifest />
    </div>
  );
}

function AuthManifest() {
  return (
    <div
      className="relative hidden flex-col justify-between overflow-hidden px-12 py-12 md:flex"
      style={{
        background: "var(--ink-1)",
        color: "#ECECEA",
        minHeight: "100vh",
      }}
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle at 90% 10%, rgba(216,90,30,0.15), transparent 40%)",
        }}
      />
      <div className="relative z-[1]">
        <div
          className="mb-6 font-mono uppercase"
          style={{
            fontSize: 11,
            color: "rgba(236,236,234,0.5)",
            letterSpacing: "0.14em",
          }}
        >
          Workpad · engineering memory
        </div>
        <h1
          className="m-0 max-w-[14ch] font-serif font-medium"
          style={{
            fontSize: 48,
            letterSpacing: "-0.02em",
            lineHeight: 1.1,
            textWrap: "pretty",
          }}
        >
          Your work should still be there tomorrow.
        </h1>
        <p
          className="mt-6 max-w-[44ch]"
          style={{
            color: "rgba(236,236,234,0.65)",
            fontSize: 15,
            lineHeight: 1.55,
          }}
        >
          Workpad is a personal workspace for source-grounded pads. RFCs, ADRs,
          design notes, run notes — each one tied to the repo it was written against,
          and each citation still live in a year.
        </p>
      </div>
      <div
        className="relative z-[1] flex flex-col gap-2 font-mono"
        style={{ fontSize: 11, color: "rgba(236,236,234,0.45)" }}
      >
        <div className="flex gap-2.5">
          <span style={{ color: "var(--accent-signal)" }}>RFC-0042</span>
          <span>Rate limiting at the edge: per-token vs. per-IP</span>
        </div>
        <div className="flex gap-2.5">
          <span style={{ color: "#A7A9B2" }}>ADR-0018</span>
          <span>Adopt SQLite WAL for the workpad cache</span>
        </div>
        <div className="flex gap-2.5">
          <span style={{ color: "#A7A9B2" }}>DN-0007</span>
          <span>Citation resolution after commit drift</span>
        </div>
        <div className="flex gap-2.5">
          <span style={{ color: "#A7A9B2" }}>RUN-0031</span>
          <span>Upgrade Python 3.11 → 3.12 on worker pool</span>
        </div>
      </div>
    </div>
  );
}

function OAuthButtons() {
  return (
    <div className="mb-5 flex flex-col gap-2">
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2.5 rounded-md border border-shell-border-strong bg-shell-1 px-4 py-2.5 text-[14px] font-medium text-ink-1 transition hover:bg-shell-2"
      >
        <Github size={15} />
        Continue with GitHub
      </button>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2.5 rounded-md border border-shell-border-strong bg-shell-1 px-4 py-2.5 text-[14px] font-medium text-ink-1 transition hover:bg-shell-2"
      >
        <GoogleGlyph size={15} />
        Continue with Google
      </button>
    </div>
  );
}

function AuthDivider() {
  return (
    <div className="mb-5 mt-3 flex items-center gap-2.5 text-ink-3">
      <div className="h-px flex-1 bg-shell-border" />
      <span
        className="font-mono uppercase"
        style={{ fontSize: 10, letterSpacing: "0.14em" }}
      >
        or with email
      </span>
      <div className="h-px flex-1 bg-shell-border" />
    </div>
  );
}

function Field({
  label,
  children,
  hint,
  aside,
}: {
  label: string;
  children: React.ReactNode;
  hint?: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span
          className="font-sans font-semibold uppercase text-ink-3"
          style={{ fontSize: 11, letterSpacing: "0.14em" }}
        >
          {label}
        </span>
        {aside}
      </div>
      {children}
      {hint ? <div className="mt-1 text-[11px] text-ink-3">{hint}</div> : null}
    </label>
  );
}

function TextInput({
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
  disabled,
  required,
  minLength,
}: {
  type?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
  disabled?: boolean;
  required?: boolean;
  minLength?: number;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      autoComplete={autoComplete}
      disabled={disabled}
      required={required}
      minLength={minLength}
      className="w-full rounded-md border border-shell-border-strong bg-shell-1 px-3 py-2.5 text-[14px] text-ink-1 outline-none transition placeholder:text-ink-3 focus:border-signal disabled:cursor-not-allowed disabled:opacity-60"
    />
  );
}

function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-md border border-state-missing-soft bg-state-missing-soft px-3 py-2 text-[12.5px] text-state-missing-ink">
      {message}
    </div>
  );
}

function SignInView({
  nav,
  onAuthenticated,
}: {
  nav: Nav;
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const user = await signIn(email.trim(), password);
      onAuthenticated(user);
      nav("app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
      <div className="wp-overline mb-3">Sign in</div>
      <h1
        className="m-0 font-serif font-medium text-ink-1"
        style={{ fontSize: 36, letterSpacing: "-0.02em" }}
      >
        Welcome back.
      </h1>
      <p className="mb-4 text-ink-2">Pick up where you left off.</p>
      <ErrorBanner message={error} />
      <Field label="Email">
        <TextInput
          type="email"
          value={email}
          onChange={setEmail}
          placeholder="you@example.com"
          autoComplete="email"
          disabled={busy}
          required
        />
      </Field>
      <Field
        label="Password"
        aside={
          <button
            type="button"
            onClick={() => nav("forgot")}
            className="cursor-pointer font-mono text-[11px] text-ink-2 underline"
          >
            forgot?
          </button>
        }
      >
        <TextInput
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          disabled={busy}
          required
        />
      </Field>
      <button
        type="submit"
        disabled={busy || !email || !password}
        className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-md bg-ink-1 px-4 py-3 text-[14px] font-medium text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? <LoaderCircle size={14} className="animate-spin" /> : null}
        {busy ? "Signing in…" : "Sign in"}
        {!busy ? <ArrowRight size={14} /> : null}
      </button>
      <div className="mt-6 text-[13px] text-ink-2">
        No account?{" "}
        <a
          href="#/signup"
          onClick={(e) => {
            e.preventDefault();
            nav("signup");
          }}
          className="text-ink-1"
        >
          Create one
        </a>
      </div>
    </form>
  );
}

function SignUpView({
  nav,
  onAuthenticated,
}: {
  nav: Nav;
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const user = await signUp(email.trim(), password, name.trim());
      onAuthenticated(user);
      nav("app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create workspace.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
      <div className="wp-overline mb-3">Sign up</div>
      <h1
        className="m-0 font-serif font-medium text-ink-1"
        style={{ fontSize: 36, letterSpacing: "-0.02em" }}
      >
        Start a workspace.
      </h1>
      <p className="mb-4 text-ink-2">
        Free while we're in beta. No credit card. One person per workspace.
      </p>
      <ErrorBanner message={error} />
      <Field label="Name">
        <TextInput
          value={name}
          onChange={setName}
          autoComplete="name"
          placeholder="Alex Kim"
          disabled={busy}
        />
      </Field>
      <Field label="Email">
        <TextInput
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="you@example.com"
          disabled={busy}
          required
        />
      </Field>
      <Field
        label="Password"
        hint="8+ characters. A passphrase is easier to remember."
      >
        <TextInput
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          disabled={busy}
          required
          minLength={8}
        />
      </Field>
      <button
        type="submit"
        disabled={busy || !email || password.length < 8}
        className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-md bg-signal px-4 py-3 text-[14px] font-medium text-white transition hover:bg-signal-hover disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? <LoaderCircle size={14} className="animate-spin" /> : null}
        {busy ? "Creating workspace…" : "Create workspace"}
        {!busy ? <ArrowRight size={14} /> : null}
      </button>
      <div className="mt-6 text-[13px] text-ink-2">
        Already have an account?{" "}
        <a
          href="#/signin"
          onClick={(e) => {
            e.preventDefault();
            nav("signin");
          }}
          className="text-ink-1"
        >
          Sign in
        </a>
      </div>
    </form>
  );
}

function ForgotView({ nav }: { nav: Nav }) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  if (sent) {
    return (
      <div className="flex flex-col gap-3.5">
        <div className="wp-overline mb-3">Check your inbox</div>
        <h1
          className="m-0 font-serif font-medium text-ink-1"
          style={{ fontSize: 36, letterSpacing: "-0.02em" }}
        >
          We sent a link.
        </h1>
        <p className="mb-4 text-ink-2">
          If{" "}
          <span className="font-mono text-ink-1">{email || "that email"}</span>{" "}
          is registered, you'll have a reset link in a minute. It expires in 30 minutes.
        </p>
        <button
          type="button"
          onClick={() => nav("signin")}
          className="inline-flex items-center gap-2 self-start rounded-md border border-shell-border-strong bg-shell-1 px-4 py-2.5 text-[14px] font-medium text-ink-1 transition hover:bg-shell-2"
        >
          <ArrowLeft size={14} />
          Back to sign in
        </button>
      </div>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        // Password reset is not yet implemented server-side. The confirmation
        // screen is deliberately ambiguous about whether the email exists.
        setSent(true);
      }}
      className="flex flex-col gap-3.5"
    >
      <div className="wp-overline mb-3">Reset password</div>
      <h1
        className="m-0 font-serif font-medium text-ink-1"
        style={{ fontSize: 36, letterSpacing: "-0.02em" }}
      >
        Forgot password.
      </h1>
      <p className="mb-6 text-ink-2">
        Give us the email on your workspace. We'll send a reset link.
      </p>
      <Field label="Email">
        <TextInput
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="you@example.com"
          required
        />
      </Field>
      <button
        type="submit"
        disabled={!email}
        className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-md bg-ink-1 px-4 py-3 text-[14px] font-medium text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-60"
      >
        Send reset link
        <ArrowRight size={14} />
      </button>
      <button
        type="button"
        onClick={() => nav("signin")}
        className="mt-2 inline-flex items-center gap-1 self-start bg-transparent text-[12px] text-ink-2 hover:text-ink-1"
      >
        <ArrowLeft size={12} />
        Back to sign in
      </button>
    </form>
  );
}
