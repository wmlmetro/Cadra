/**
 * Every record the suite creates is tagged with a unique, greppable marker so
 * test residue is easy to find and clean up later (the app/API expose no hard
 * delete — assets soft-condemn to `disposed`, locations archive via active=false).
 *
 * Example name: "E2E-1730000000000-4821 Test Asset"
 */
const RUN_ID = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;

export const MARKER_PREFIX = `E2E-${RUN_ID}`;

/** A unique, marked display name for a created record. */
export function markedName(label: string): string {
  return `${MARKER_PREFIX} ${label}`;
}

/** Track created records across the run so the final report can list them. */
export interface CreatedRecord {
  kind: "asset" | "location" | "request";
  id?: number | string;
  name: string;
}

const created: CreatedRecord[] = [];
export function recordCreated(rec: CreatedRecord) {
  created.push(rec);
}
export function createdRecords(): CreatedRecord[] {
  return created;
}
