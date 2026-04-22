import React, { useCallback, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { MarketingPage, AuthPage } from "./components/PublicPages";
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

// Public routes (marketing, auth) are presentational. The hash-based router
// keeps them dependency-free: #/marketing, #/signin, #/signup, #/forgot.
// Anything else falls through to the authenticated app.
type Route = "marketing" | "signin" | "signup" | "forgot" | "app";

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "").toLowerCase();
  if (hash === "marketing") return "marketing";
  if (hash === "signin" || hash === "login") return "signin";
  if (hash === "signup" || hash === "register") return "signup";
  if (hash === "forgot") return "forgot";
  return "app";
}

function Root() {
  const [route, setRoute] = useState<Route>(readRoute);
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
      setRoute(readRoute());
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
      setRoute("app");
      return;
    }
    if (window.location.hash !== target) {
      window.location.hash = target;
    } else {
      setRoute(next);
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
