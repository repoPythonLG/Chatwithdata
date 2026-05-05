import { create } from "zustand";

type Page = "chat" | "settings";
type Theme = "light" | "dark";
export type ResponseMode = "simple" | "advanced";
export type AnalysisEngine = "standard" | "qwen_cli";

interface AppState {
  activePage: Page;
  theme: Theme;
  responseMode: ResponseMode;
  analysisEngine: AnalysisEngine;
  selectedDataSources: string[];
  conversationId: string | null;
  setActivePage: (page: Page) => void;
  setTheme: (theme: Theme) => void;
  setResponseMode: (mode: ResponseMode) => void;
  setAnalysisEngine: (engine: AnalysisEngine) => void;
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

function readAnalysisEngine(): AnalysisEngine {
  if (typeof window === "undefined") return "standard";
  return window.localStorage.getItem("analysisEngine") === "qwen_cli" ? "qwen_cli" : "standard";
}

function saveAnalysisEngine(analysisEngine: AnalysisEngine) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem("analysisEngine", analysisEngine);
}

export const useAppStore = create<AppState>((set) => ({
  activePage: "chat",
  theme: "light",
  responseMode: readResponseMode(),
  analysisEngine: readAnalysisEngine(),
  selectedDataSources: [],
  conversationId: null,
  setActivePage: (activePage) => set({ activePage }),
  setTheme: (theme) => set({ theme }),
  setResponseMode: (responseMode) => {
    saveResponseMode(responseMode);
    set({ responseMode });
  },
  setAnalysisEngine: (analysisEngine) => {
    saveAnalysisEngine(analysisEngine);
    set({ analysisEngine });
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
