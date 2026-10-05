/**
 * The sentence instead of the white page (handoff 50 ruling 2).
 *
 * Report 49 found that one null render value — `book_value` on a snapshot
 * row — unmounted the ENTIRE app to a blank screen, because nothing between
 * the root and the page caught a render error. The blank page is the worst
 * failure available: the person cannot tell whether it is their network,
 * their account, or us.
 *
 * This boundary sits INSIDE AppLayout, around the route's Suspense, so a
 * page that throws takes down only the page area — the shell and the
 * sidebar stay alive, and "use the menu" is true when we say it. Wrapping
 * the Suspense (not just the Switch) also catches a lazy chunk that fails
 * to load after a deploy. App.tsx keys it on the current location, so
 * navigating away resets it without anybody clicking "Try again".
 *
 * React 19 still has no hook for this: getDerivedStateFromError and
 * componentDidCatch exist only on a class component.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The console is where a developer looks; the panel below is where the
    // person does. Both get the truth.
    console.error("[RouteErrorBoundary]", error, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div className="p-8 max-w-xl mx-auto" data-testid="route-error-boundary">
          <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
            <div className="flex items-start gap-3">
              <AlertCircle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[13px] font-semibold text-foreground">This page failed to draw.</p>
                <p className="text-[12px] text-muted-foreground mt-0.5">
                  The rest of Cadra is still working — use the menu to open another page, or try again.
                </p>
                {/* Something to report, in the person's hand rather than only
                    in a console they will never open. */}
                <p className="text-[11px] font-mono text-muted-foreground/70 mt-2 break-words" data-testid="route-error-message">
                  {this.state.error.message || String(this.state.error)}
                </p>
              </div>
            </div>
            <button
              onClick={this.reset}
              data-testid="button-route-error-retry"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
            >
              <RefreshCw size={12} /> Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
