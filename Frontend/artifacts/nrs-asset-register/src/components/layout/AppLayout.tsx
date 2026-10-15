import { createContext, useContext, useState, useCallback } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

interface LayoutCtx {
  setTitle: (t: string) => void;
  /** A list page takes the top bar's keystrokes. Registering also sets the
   *  box's TEXT — to `initial`, or empty — so the box never shows a search
   *  the page under it is not running (handoff 60: Back to Candidates showed
   *  a receipt's GRN above an unfiltered list). */
  setSearchHandler: (fn: ((q: string) => void) | undefined, initial?: string) => void;
}

const LayoutContext = createContext<LayoutCtx>({
  setTitle: () => {},
  setSearchHandler: () => {},
});

export const useLayoutCtx = () => useContext(LayoutContext);

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [title, setTitleState] = useState("Facility Command Center");
  const [searchHandler, setSearchHandlerState] = useState<((q: string) => void) | undefined>(undefined);
  // A new object each registration, so the same text twice still resets.
  const [searchSeed, setSearchSeed] = useState<{ text: string } | null>(null);

  const setTitle = useCallback((t: string) => setTitleState(t), []);
  const setSearchHandler = useCallback(
    (fn: ((q: string) => void) | undefined, initial?: string) => {
      setSearchHandlerState(() => fn);
      // Only on REGISTERING: clearing on unregister would wipe what a person
      // just typed and sent to the global search with Enter.
      if (fn) setSearchSeed({ text: initial ?? "" });
    },
    []
  );

  return (
    <LayoutContext.Provider value={{ setTitle, setSearchHandler }}>
      <div className="flex h-screen bg-background overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <Topbar title={title} onSearch={searchHandler} seed={searchSeed} />
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </LayoutContext.Provider>
  );
}
