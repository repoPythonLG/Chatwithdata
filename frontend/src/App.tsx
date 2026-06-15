import { useEffect } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut, MessageSquareText, Moon, Settings, Sun, UserCircle } from "lucide-react";

import { api } from "./api/client";
import { ChatPage } from "./pages/ChatPage";
import { LoginPage } from "./pages/LoginPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useAppStore } from "./store/appStore";

const SABIC_LOGO_URL = "/brand/sabic-logo.svg";

export default function App() {
  const queryClient = useQueryClient();
  const activePage = useAppStore((state) => state.activePage);
  const setActivePage = useAppStore((state) => state.setActivePage);
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const auth = useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.currentUser,
    retry: false
  });

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
      setActivePage("chat");
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    if (auth.data?.role !== "admin" && activePage === "settings") {
      setActivePage("chat");
    }
  }, [activePage, auth.data?.role, setActivePage]);

  if (auth.isLoading) {
    return <LoadingScreen />;
  }

  if (!auth.data) {
    return <LoginPage onLogin={() => queryClient.invalidateQueries({ queryKey: ["auth", "me"] })} />;
  }

  const currentUser = auth.data;
  const isAdmin = currentUser.role === "admin";

  return (
    <div className="min-h-screen p-4 text-ink-900 dark:text-ink-50">
      <div className="mx-auto flex max-w-[1800px] flex-col gap-4">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-[2rem] border border-white/60 bg-white/58 px-5 py-4 shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/62">
          <div className="flex items-center gap-4">
            <div className="grid h-12 w-[7.5rem] place-items-center rounded-2xl border border-ink-100 bg-white px-3 shadow-inner dark:border-white/20">
              <img className="h-9 w-auto" src={SABIC_LOGO_URL} alt="SABIC logo" />
            </div>
            <div>
              <h1 className="font-display text-xl text-ink-900 dark:text-white">Chat with Contracts</h1>
            </div>
          </div>

          <nav className="flex items-center gap-2 rounded-2xl bg-white/60 p-1 dark:bg-white/5">
            <NavButton active={activePage === "chat"} onClick={() => setActivePage("chat")}>
              <MessageSquareText className="h-4 w-4" />
              Chat
            </NavButton>
            {isAdmin ? (
              <NavButton
                active={activePage === "settings"}
                onClick={() => setActivePage("settings")}
              >
                <Settings className="h-4 w-4" />
                Settings
              </NavButton>
            ) : null}
            <div className="hidden items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-ink-700 dark:text-ink-50 md:flex">
              <UserCircle className="h-4 w-4 text-harbor-500" />
              <span>{currentUser.display_name}</span>
            </div>
            <button
              className="rounded-xl p-2 transition hover:bg-white dark:hover:bg-white/10"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              className="rounded-xl p-2 transition hover:bg-white dark:hover:bg-white/10"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </nav>
        </header>

        {activePage === "chat" || !isAdmin ? (
          <ChatPage />
        ) : (
          <SettingsPage currentUser={currentUser} />
        )}
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="grid min-h-screen place-items-center p-5 text-ink-900 dark:text-ink-50">
      <div className="rounded-3xl border border-white/60 bg-white/72 px-6 py-5 text-sm font-semibold shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/70">
        Checking secure session…
      </div>
    </div>
  );
}

function NavButton({
  active,
  children,
  onClick
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      className={[
        "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition",
        active
          ? "bg-harbor-500 text-white shadow-lg shadow-harbor-500/20 hover:bg-harbor-700 dark:bg-harbor-400 dark:text-ink-900"
          : "text-ink-700 hover:bg-white dark:text-ink-50 dark:hover:bg-white/10"
      ].join(" ")}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
