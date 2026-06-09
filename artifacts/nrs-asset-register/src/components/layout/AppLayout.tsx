import { createContext, useContext, useState, useCallback } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

interface LayoutCtx {
  setTitle: (t: string) => void;
  setSearchHandler: (fn: ((q: string) => void) | undefined) => void;
}

const LayoutContext = createContext<LayoutCtx>({
  setTitle: () => {},
  setSearchHandler: () => {},
});

export const useLayoutCtx = () => useContext(LayoutContext);

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [title, setTitleState] = useState("Facility Command Center");
  const [searchHandler, setSearchHandlerState] = useState<((q: string) => void) | undefined>(undefined);

  const setTitle = useCallback((t: string) => setTitleState(t), []);
  const setSearchHandler = useCallback(
    (fn: ((q: string) => void) | undefined) => setSearchHandlerState(() => fn),
    []
  );

  return (
    <LayoutContext.Provider value={{ setTitle, setSearchHandler }}>
      <div className="flex h-screen bg-background overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <Topbar title={title} onSearch={searchHandler} />
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </LayoutContext.Provider>
  );
}
