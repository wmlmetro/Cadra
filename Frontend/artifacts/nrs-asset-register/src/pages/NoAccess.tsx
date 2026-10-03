/**
 * Where somebody lands when no page in the app opens for them (handoff 46's
 * landing rule, `landingPath` in lib/navigation.ts).
 *
 * Before this page a sign-in went to `/`, and an account with no reading
 * scope — the Tag-Issuing Unit on its own, whose one scope is
 * `tagging:write` — opened on a dashboard of refusals with a sidebar of
 * doors it could not open. This says instead what the account holds, that
 * it opens nothing here, and who can change that. It changes nothing and
 * asks the server nothing: the scopes are the ones the sign-in stored.
 */
import { useEffect } from "react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { useScopes } from "@/hooks/use-scopes";
import { scopeWords } from "@/pages/admin/Users";
import { ShieldOff } from "lucide-react";

export default function NoAccess() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();

  useEffect(() => {
    setTitle("No access");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // The one combination the role model makes common: a tagger given the
  // Tag-Issuing Unit without Asset User. The role confirms a label; finding
  // the asset to confirm it on is a read, and the read is Asset User's
  // (CLAUDE.md, "A human in the Tag-Issuing Unit also holds Asset User").
  const taggerAlone = scopes.all.includes("tagging:write") && !scopes.has("assets:read");

  return (
    <div className="p-8 max-w-xl mx-auto" data-testid="no-access">
      <div className="bg-card border border-border rounded-2xl p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center border shrink-0 bg-muted border-border">
            <ShieldOff size={18} className="text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <h1 className="text-[15px] font-bold text-foreground">Nothing in Cadra opens for this account yet</h1>
            <p className="text-[12px] text-muted-foreground mt-1 leading-relaxed">
              You are signed in, but this account holds no role that opens a screen in Cadra.
            </p>
          </div>
        </div>

        {taggerAlone && (
          <p className="mt-4 text-[12px] text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-3 leading-relaxed" data-testid="no-access-tagger">
            The Tag-Issuing Unit role lets you confirm a label on an asset, but finding the asset needs Asset User as well.
          </p>
        )}

        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">What this account holds</p>
          {scopes.all.length === 0 ? (
            <p className="text-[12px] text-foreground" data-testid="no-access-scopes-none">None</p>
          ) : (
            <ul className="space-y-1" data-testid="no-access-scopes">
              {scopes.all.map(s => (
                <li key={s} className="text-[12px] text-foreground" data-scope={s}>
                  {scopeWords(s)} <span className="font-mono text-[11px] text-muted-foreground">({s})</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="mt-4 text-[12px] text-muted-foreground leading-relaxed">
          An administrator can add a role to your account. Sign out and sign in again once they have.
        </p>
      </div>
    </div>
  );
}
