import React, { useCallback, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import {
  AuthPage,
  InviteAcceptPage,
  MarketingPage,
  ResetConfirmPage,
} from "./components/PublicPages";
import {
  AuthContext,
  fetchCurrentUser,
  signOut as apiSignOut,
  type AuthUser,
} from "./lib/auth";
import { initSystemTheme } from "./lib/systemTheme";
import "./index.css";

// Run before React mounts so the dark theme applies on first paint.
initSystemTheme();

// Public routes are hash-based: #/marketing, #/signin, #/signup, #/forgot,
// #/reset?token=..., #/invite?token=... — kept dependency-free (no router lib).
// Anything else falls through to the authenticated app.
type Route =
  | "marketing"
  | "signin"
  | "signup"
  | "forgot"
  | "reset"
  | "invite"
  | "app";

type ParsedRoute = { route: Route; token: string | null };

function readRoute(): ParsedRoute {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?", 2);
  const token = new URLSearchParams(query).get("token");
  const slug = path.toLowerCase();
  if (slug === "marketing") return { route: "marketing", token: null };
  if (slug === "signin" || slug === "login") return { route: "signin", token: null };
  if (slug === "signup" || slug === "register") return { route: "signup", token: null };
  if (slug === "forgot") return { route: "forgot", token: null };
  if (slug === "reset") return { route: "reset", token };
  if (slug === "invite") return { route: "invite", token };
  return { route: "app", token: null };
}

function Root() {
  const [parsed, setParsed] = useState<ParsedRoute>(readRoute);
  const route = parsed.route;
  const token = parsed.token;
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchCurrentUser()
      .then((current) => {
        if (alive) setUser(current);
      })
      .catch(() => {
        // Network / unexpected error — treat as signed out so the app can
        // still render the public routes.
        if (alive) setUser(null);
      })
      .finally(() => {
        if (alive) setAuthReady(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    function onHash() {
      setParsed(readRoute());
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const nav = useCallback((next: Route) => {
    const target = next === "app" ? "" : `#/${next}`;
    if (next === "app") {
      if (window.location.hash) {
        history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search,
        );
      }
      setParsed({ route: "app", token: null });
      return;
    }
    if (window.location.hash !== target) {
      window.location.hash = target;
    } else {
      setParsed({ route: next, token: null });
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiSignOut();
    } catch {
      // best effort — still clear local state and route to marketing
    }
    setUser(null);
    nav("marketing");
  }, [nav]);

  // While we're resolving the session, render a neutral placeholder rather
  // than flashing the marketing or app UI.
  if (!authReady) {
    return (
      <div
        style={{
          background: "var(--shell-0)",
          color: "var(--ink-3)",
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--ff-mono)",
          fontSize: 12,
          letterSpacing: "0.08em",
        }}
      >
        loading workspace…
      </div>
    );
  }

  // Marketing is reachable to everyone (signed-in users can visit too).
  // Auth pages only make sense when unauthenticated — if a signed-in user
  // lands on them, redirect back to the app.
  if (route === "signin" || route === "signup" || route === "forgot") {
    if (user) {
      nav("app");
      return null;
    }
    return (
      <AuthContext.Provider value={{ user, setUser, signOut }}>
        <AuthPage
          variant={route}
          nav={nav}
          onAuthenticated={(u) => setUser(u)}
        />
      </AuthContext.Provider>
    );
  }

  // Reset-confirm is a deep-link from the reset email (or the dev log).
  // It works whether or not the user is currently signed in — finishing a
  // reset revokes all sessions, so the user ends up signed out regardless.
  if (route === "reset") {
    return (
      <AuthContext.Provider value={{ user, setUser, signOut }}>
        <ResetConfirmPage token={token} nav={nav} />
      </AuthContext.Provider>
    );
  }

  // Invite-accept is also a deep-link but it requires a signed-in user —
  // the project membership row gets attached to whoever's cookie the
  // backend sees. If the visitor isn't signed in, bounce to signup first
  // and preserve the token so InviteAcceptPage can pick it back up post-
  // auth.
  if (route === "invite") {
    if (!user) {
      return (
        <AuthContext.Provider value={{ user, setUser, signOut }}>
          <InviteAcceptPage token={token} user={null} nav={nav} />
        </AuthContext.Provider>
      );
    }
    return (
      <AuthContext.Provider value={{ user, setUser, signOut }}>
        <InviteAcceptPage token={token} user={user} nav={nav} />
      </AuthContext.Provider>
    );
  }

  if (route === "marketing") {
    return (
      <AuthContext.Provider value={{ user, setUser, signOut }}>
        <MarketingPage nav={nav} isAuthed={Boolean(user)} />
      </AuthContext.Provider>
    );
  }

  // route === "app" — gate on auth. Unauthenticated visitors see the
  // marketing page by default.
  if (!user) {
    return (
      <AuthContext.Provider value={{ user, setUser, signOut }}>
        <MarketingPage nav={nav} isAuthed={false} />
      </AuthContext.Provider>
    );
  }

  return (
    <AuthContext.Provider value={{ user, setUser, signOut }}>
      <App />
    </AuthContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
