/**
 * Identify from photo (handoff 64, ruling R11) — the client half.
 *
 * Cadra's SERVER asks the vision model; this app only sends the photo to
 * `POST /api/v1/ai/identify` and shows what comes back as SUGGESTIONS. No
 * field is written from a suggestion until the person accepts it, and the
 * save names the suggestion (`ai_suggestion`) so the server records, per
 * field, accepted / changed / ignored.
 *
 * The switch is the tenant's: `GET /api/v1/settings` → `ai_identify`. Off
 * (the default everywhere), no screen draws the button.
 */
import { apiGet, apiUpload, newIdempotencyKey } from "@/lib/api";

export interface AiSwitch {
  enabled: boolean;
  provider: string;
  provider_label: string;
  notice: string;
}

export interface ScoredCategory {
  id: number;
  name: string | null;
  identification_mode: string | null;
  sap_asset_class: string | null;
  confidence: number;
}

export interface SapCandidate {
  id: number;
  rank: number | null;
  reason_code: string | null;
  reason: string | null;
  asset_number: string;
  sub_number: string | null;
  class: string | null;
  description: string | null;
  old_tag: string | null;
  office_code: string | null;
}

export interface AiSuggestion {
  suggestion_id: number;
  provider: string;
  provider_label: string;
  model: string | null;
  latency_ms: number | null;
  photo: { kind: "asset_photo" | "pending" | "expired"; id: number | null; asset_id?: number; expires_at?: string };
  category: ScoredCategory & { alternatives: ScoredCategory[] };
  attributes: {
    name: string | null; colour: string | null; material: string | null;
    make: string | null; model_name: string | null; dimensions: string | null;
  };
  condition: { value: string; note: string | null };
  text_read: { text: string; looks_like: string }[];
  sap_candidates: {
    count: number; items: SapCandidate[] | null; basis: string | null;
    note: string | null;
  };
  notes: string[];
  notice: string;
}

/** The fields a suggestion can propose, in the order the screens show them,
 *  as the server names them (`ai_suggestion.SUGGESTED_FIELDS`). */
export const SUGGESTED_FIELDS = [
  "category_id", "name", "colour", "material", "make", "model_name",
  "dimensions", "condition",
] as const;
export type SuggestedField = typeof SUGGESTED_FIELDS[number];

export const FIELD_WORDS: Record<SuggestedField, string> = {
  category_id: "Class",
  name: "Description",
  colour: "Colour",
  material: "Material",
  make: "Make",
  model_name: "Model",
  dimensions: "Dimensions",
  condition: "Condition",
};

export const TEXT_KIND_WORDS: Record<string, string> = {
  brand: "brand",
  model: "model",
  serial_like: "looks like a serial",
  firs_tag_like: "looks like an old FIRS tag",
  other: "other text",
};

/** `{field: proposed value}` — only the fields the suggestion offered. */
export function proposedValues(s: AiSuggestion): Partial<Record<SuggestedField, string | number>> {
  const out: Partial<Record<SuggestedField, string | number>> = {};
  if (s.category?.id) out.category_id = s.category.id;
  for (const k of ["name", "colour", "material", "make", "model_name", "dimensions"] as const) {
    const v = s.attributes?.[k];
    if (v) out[k] = v;
  }
  if (s.condition?.value) out.condition = s.condition.value;
  return out;
}

export async function fetchAiSwitch(): Promise<AiSwitch | null> {
  try {
    const res = await apiGet<{ ai_identify?: AiSwitch }>("/api/v1/settings");
    return res.data?.ai_identify ?? null;
  } catch {
    return null;
  }
}

/** A photo for an asset not saved yet. Held 24 h for the save to claim. */
export async function identifyNewPhoto(picture: Blob, filename: string): Promise<AiSuggestion> {
  const form = new FormData();
  form.append("file", picture, filename);
  form.append("source", "web");
  const res = await apiUpload<AiSuggestion>("/api/v1/ai/identify", form,
    { idempotencyKey: newIdempotencyKey() });
  return res.data;
}

/** A photo already on an asset. */
export async function identifyStoredPhoto(photoId: number): Promise<AiSuggestion> {
  const form = new FormData();
  form.append("photo_id", String(photoId));
  const res = await apiUpload<AiSuggestion>("/api/v1/ai/identify", form,
    { idempotencyKey: newIdempotencyKey() });
  return res.data;
}
