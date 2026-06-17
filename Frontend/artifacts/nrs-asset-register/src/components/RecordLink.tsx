import { useLocation } from "wouter";
import { cn } from "@/lib/utils";

interface Props {
  to: string;
  /** When false, render as plain text (e.g. id missing). */
  enabled?: boolean;
  children: React.ReactNode;
  className?: string;
  /** Don't underline on hover — useful when the surrounding row already
   *  signals interactivity. */
  subtle?: boolean;
}

/**
 * Small consistent "clickable record" link used wherever the UI shows a
 * resource name that maps to a detail page (asset → /assets/:id, employee
 * → /hr/employees/:id, location → /locations/:id, request → /service-desk/:id).
 * When `enabled=false` we fall back to plain text so the caller can pass an
 * id that may or may not be present without conditional wrapping.
 */
export default function RecordLink({ to, enabled = true, children, className, subtle }: Props) {
  const [, nav] = useLocation();

  if (!enabled) {
    return <span className={className}>{children}</span>;
  }

  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); nav(to); }}
      className={cn(
        "inline text-left text-primary hover:opacity-80",
        !subtle && "hover:underline",
        className,
      )}
    >
      {children}
    </button>
  );
}
