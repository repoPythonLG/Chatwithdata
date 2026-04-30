import { create } from "zustand";

type Page = "chat" | "settings";
type Theme = "light" | "dark";
export type ResponseMode = "simple" | "advanced";

interface AppState {
  activePage: Page;
  theme: Theme;
  responseMode: ResponseMode;
  selectedDataSources: string[];
  conversationId: string | null;
  setActivePage: (page: Page) => void;
  setTheme: (theme: Theme) => void;
  setResponseMode: (mode: ResponseMode) => void;
  toggleDataSource: (id: string) => void;
  setSelectedDataSources: (ids: string[]) => void;
  setConversationId: (id: string | null) => void;
}

function readResponseMode(): ResponseMode {
  if (typeof window === "undefined") return "simple";
  return window.localStorage.getItem("responseMode") === "advanced" ? "advanced" : "simple";
}

function saveResponseMode(responseMode: ResponseMode) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem("responseMode", responseMode);
}

export const useAppStore = create<AppState>((set) => ({
  activePage: "chat",
  theme: "light",
  responseMode: readResponseMode(),
  selectedDataSources: [],
  conversationId: null,
  setActivePage: (activePage) => set({ activePage }),
  setTheme: (theme) => set({ theme }),
  setResponseMode: (responseMode) => {
    saveResponseMode(responseMode);
    set({ responseMode });
  },
  toggleDataSource: (id) =>
    set((state) => ({
      selectedDataSources: state.selectedDataSources.includes(id)
        ? state.selectedDataSources.filter((item) => item !== id)
        : [...state.selectedDataSources, id]
    })),
  setSelectedDataSources: (selectedDataSources) => set({ selectedDataSources }),
  setConversationId: (conversationId) => set({ conversationId })
}));
