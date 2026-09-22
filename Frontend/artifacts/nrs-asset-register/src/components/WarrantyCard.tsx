import type { Asset } from "@/types";
import { useEnumLabel } from "@/hooks/useEnums";
import { formatIsoDate } from "@/lib/utils";

/**
 * The asset page's Warranty section (handoff 34).
 *
 * A warranty is a fact about a CONTRACT, not about the asset, and this card is
 * drawn so it cannot be read as one about the asset: one neutral style for
 * every status — no green for covered, no red for lapsed — because those are
 * the colours of the service pills in the hero, and an expired warranty on a
 * laptop that works is not a finding. Nothing here feeds a pill, a status or a
 * count of working stock.
 *
 * It publishes the WORKING, not only the answer. A bare "expires 12 March
 * 2028" cannot be checked against a certificate; "24 months from 12 March
 * 2026" can, and the server's `basis` sentence is printed as sent.
 *
 * No warranty recorded is the ordinary case, and says so plainly — neutral,
 * not an alarm. But `none` means NO EXPIRY is recorded, and the model accepts
 * a warrantor or a certificate number without one; the verification pass
 * found the first draft telling that person "nothing has been entered" and
 * hiding exactly the two facts they need — who to call and what to quote.
 * So the short box is only for a warranty with nothing on it at all. A server that predates the block sends none at all, and then
 * the card shows the bare expiry date if there is one and draws no verdict:
 * an old server has not said whether a warranty is recorded.
 */

function Row({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <div className="flex flex-col sm:flex-row sm:gap-4 py-2.5 border-b border-border last:border-0">
      <dt className="text-xs font-medium text-muted-foreground w-44 shrink-0">{label}</dt>
      <dd className="text-xs text-foreground mt-0.5 sm:mt-0" data-testid={testId}>{children}</dd>
    </div>
  );
}

const notRecorded = <span className="italic text-muted-foreground">Not recorded</span>;

export default function WarrantyCard({ asset }: { asset: Asset }) {
  const statusLabel = useEnumLabel("warranty_status");
  const w = asset.warranty;
  const legacyExpiry = asset.keyDates?.warrantyExpiry;

  if (!w && !legacyExpiry) return null;
  const nothingEntered = !!w && w.status === "none" && !w.warrantor && !w.reference;

  return (
    <section data-testid="warranty-card">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Warranty</h3>
      {!w ? (
        <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
          <Row label="Expires" testId="warranty-expiry">{formatIsoDate(legacyExpiry)}</Row>
        </dl>
      ) : nothingEntered ? (
        <div className="bg-card border border-card-border rounded-xl px-5 py-4" data-testid="warranty-none">
          <p className="text-xs text-foreground" data-testid="warranty-status">{statusLabel("none")}</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            Nothing about a warranty has been entered for this asset. That is a fact about the record,
            not about the asset's condition or whether it is in service.
          </p>
        </div>
      ) : (
        <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
          <Row label="Status" testId="warranty-status">
            {/* One neutral chip for every status, on purpose — see above. */}
            <span className="inline-flex items-center px-2 py-0.5 rounded-md border border-border bg-muted/50 text-foreground font-medium">
              {statusLabel(w.status)}
            </span>
            {w.statusAsOf && (
              <span className="ml-2 text-[11px] text-muted-foreground">as of {formatIsoDate(w.statusAsOf)} (Lagos)</span>
            )}
          </Row>
          <Row label="Expires" testId="warranty-expiry">
            {w.expiry ? formatIsoDate(w.expiry) : (
              <span className="italic text-muted-foreground">
                Not recorded — so the register cannot say whether this warranty is still in force
              </span>
            )}
          </Row>
          <Row label="How the expiry was set" testId="warranty-basis">{w.basis ?? notRecorded}</Row>
          <Row label="Who honours it" testId="warranty-warrantor">{w.warrantor ?? notRecorded}</Row>
          <Row label="Certificate / document ref." testId="warranty-reference">{w.reference ?? notRecorded}</Row>
        </dl>
      )}
    </section>
  );
}
