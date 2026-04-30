import { create } from "zustand";

type Page = "chat" | "settings";
type Theme = "light" | "dark";

interface AppState {
  activePage: Page;
  theme: Theme;
  selectedDataSources: string[];
  conversationId: string | null;
  setActivePage: (page: Page) => void;
  setTheme: (theme: Theme) => void;
  toggleDataSource: (id: string) => void;
  setSelectedDataSources: (ids: string[]) => void;
  setConversationId: (id: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  activePage: "chat",
  theme: "light",
  selectedDataSources: [],
  conversationId: null,
  setActivePage: (activePage) => set({ activePage }),
  setTheme: (theme) => set({ theme }),
  toggleDataSource: (id) =>
    set((state) => ({
      selectedDataSources: state.selectedDataSources.includes(id)
        ? state.selectedDataSources.filter((item) => item !== id)
        : [...state.selectedDataSources, id]
    })),
  setSelectedDataSources: (selectedDataSources) => set({ selectedDataSources }),
  setConversationId: (conversationId) => set({ conversationId })
}));
