import { useEffect } from "react";
import type { ReactNode } from "react";
import { MessageSquareText, Moon, Settings, Sun } from "lucide-react";

import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useAppStore } from "./store/appStore";

const SABIC_LOGO_URL = "https://www.sabic.com/en/Images/SABIC-LOGO_tcm1010-14323.svg";

export default function App() {
  const activePage = useAppStore((state) => state.activePage);
  const setActivePage = useAppStore((state) => state.setActivePage);
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <div className="min-h-screen p-4 text-ink-900 dark:text-ink-50">
      <div className="mx-auto flex max-w-[1800px] flex-col gap-4">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-[2rem] border border-white/60 bg-white/58 px-5 py-4 shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/62">
          <div className="flex items-center gap-4">
            <div className="grid h-12 w-[7.5rem] place-items-center rounded-2xl bg-white/80 px-3 shadow-inner dark:bg-white">
              <img className="h-9 w-auto" src={SABIC_LOGO_URL} alt="SABIC logo" />
            </div>
            <div>
              <h1 className="font-display text-xl font-bold">Chat with Data</h1>
            </div>
          </div>

          <nav className="flex items-center gap-2 rounded-2xl bg-white/60 p-1 dark:bg-white/5">
            <NavButton active={activePage === "chat"} onClick={() => setActivePage("chat")}>
              <MessageSquareText className="h-4 w-4" />
              Chat
            </NavButton>
            <NavButton active={activePage === "settings"} onClick={() => setActivePage("settings")}>
              <Settings className="h-4 w-4" />
              Settings
            </NavButton>
            <button
              className="rounded-xl p-2 transition hover:bg-white dark:hover:bg-white/10"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </nav>
        </header>

        {activePage === "chat" ? <ChatPage /> : <SettingsPage />}
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
          ? "bg-ink-900 text-white dark:bg-harbor-500"
          : "text-ink-700 hover:bg-white dark:text-ink-50 dark:hover:bg-white/10"
      ].join(" ")}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
