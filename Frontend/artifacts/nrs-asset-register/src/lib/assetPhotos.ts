/**
 * Handoff 61 §5 — photos on an asset: the API calls, and the one thing the
 * browser does before sending a picture.
 *
 *   GET  /api/v1/assets/<id>/photos                         the list
 *   POST /api/v1/assets/<id>/photos                         one photo, multipart
 *   POST /api/v1/assets/<id>/photos/<photo_id>/supersede    `{reason}`
 *   GET  /api/v1/assets/<id>/photos/<photo_id>              the bytes
 *
 * The list is ONE answer to "what pictures does this asset have": photos and
 * Internal Audit's verification evidence, each labelled `kind`. Evidence
 * obeys the evidence guard: a caller without `evidence:read` gets no
 * evidence item and `iad_evidence.summary` ("IAD evidence: N items").
 *
 * Kept out of `dataProvider.ts`, which other work in the same handoff edits.
 */
import { apiGet, apiGetRaw, apiPost, apiUpload, newIdempotencyKey } from "./api";

/** AI-NFR-07: a photo is at most 300 KB. The server refuses anything over
 *  it (413); the browser compresses below it first so a person never meets
 *  that refusal from this app. */
export const PHOTO_MAX_BYTES = 300 * 1024;

export interface PhotoUserRef {
  id: number;
  name: string;
}

export interface PhotoSuperseded {
  /** UTC, `YYYY-MM-DD HH:MM:SS`, no zone. */
  at: string | null;
  by: PhotoUserRef | null;
  by_name: string | null;
  reason: string | null;
  event_id: number;
}

export interface AssetPicture {
  kind: "photo" | "iad_evidence";
  /** A photo's id, or an evidence file's attachment id: two sequences, so
   *  `(kind, id)` is the key. */
  id: number;
  asset_id: number;
  /** `web` / `mobile` for a photo; `gate_evidence` for IAD's evidence. */
  source: "web" | "mobile" | "gate_evidence" | string;
  caption: string | null;
  filename: string | null;
  mimetype: string | null;
  size: number;
  width: number | null;
  height: number | null;
  sha256: string | null;
  uploaded_by: PhotoUserRef | null;
  uploaded_by_name: string | null;
  /** UTC, `YYYY-MM-DD HH:MM:SS`, no zone. */
  uploaded_at: string | null;
  superseded: PhotoSuperseded | null;
  verification_event_id: number | null;
  is_test_fixture: boolean | null;
  /** Needs the bearer token — fetched with `apiGetRaw`, never an `<img src>`
   *  or `<a href>` pointing at the API. */
  url: string;
}

export interface AssetPhotosAnswer {
  asset_id: number;
  /** Newest first. */
  items: AssetPicture[];
  photos: {
    count: number;
    /** Not superseded — what the 12-photo cap counts. */
    standing: number;
    superseded: number;
    max_standing: number;
    max_bytes: number;
    allowed_types: string[];
  };
  iad_evidence: {
    readable: boolean;
    count: number;
    /** Non-readers only: "IAD evidence: N items". */
    summary?: string;
    requires_scope?: string;
  };
}

/** The query key the list is cached under; every write invalidates it. */
export const assetPhotosKey = (assetId: string | number) =>
  ["asset-photos", String(assetId)] as const;

export async function fetchAssetPhotos(assetId: string | number): Promise<AssetPhotosAnswer> {
  const res = await apiGet<AssetPhotosAnswer>(
    `/api/v1/assets/${encodeURIComponent(String(assetId))}/photos`);
  const d = res.data;
  return {
    asset_id: d?.asset_id ?? Number(assetId),
    items: Array.isArray(d?.items) ? d.items : [],
    photos: d?.photos ?? {
      count: 0, standing: 0, superseded: 0, max_standing: 12,
      max_bytes: PHOTO_MAX_BYTES, allowed_types: ["image/jpeg", "image/png"],
    },
    iad_evidence: d?.iad_evidence ?? { readable: false, count: 0 },
  };
}

/** The picture's bytes as an object URL, through the bearer token. The
 *  caller revokes it (`URL.revokeObjectURL`) when the picture goes away. */
export async function fetchPictureObjectUrl(picture: Pick<AssetPicture, "url" | "mimetype">): Promise<string> {
  const res = await apiGetRaw(picture.url);
  const raw = await res.blob();
  const type = picture.mimetype || res.headers.get("Content-Type") || raw.type;
  const blob = type && raw.type !== type ? new Blob([raw], { type }) : raw;
  return URL.createObjectURL(blob);
}

/** `POST …/photos` — one picture, `source=web`. Sent under a fresh
 *  idempotency key, so a double-submit stores one photo. */
export async function uploadAssetPhoto(
  assetId: string | number, picture: Blob, filename: string, caption?: string,
): Promise<AssetPicture> {
  const form = new FormData();
  form.append("file", picture, filename);
  form.append("source", "web");
  if (caption && caption.trim()) form.append("caption", caption.trim());
  const res = await apiUpload<AssetPicture>(
    `/api/v1/assets/${encodeURIComponent(String(assetId))}/photos`, form,
    { idempotencyKey: newIdempotencyKey() });
  return res.data;
}

/** `POST …/photos/<id>/supersede` — the photo is kept and marked. */
export async function supersedeAssetPhoto(
  assetId: string | number, photoId: number, reason: string,
): Promise<AssetPicture> {
  const res = await apiPost<AssetPicture>(
    `/api/v1/assets/${encodeURIComponent(String(assetId))}/photos/${photoId}/supersede`,
    { reason }, { idempotencyKey: newIdempotencyKey() });
  return res.data;
}

// ── before sending: under 300 KB, as a JPEG ────────────────────────────────

/** The longest side the first attempt is drawn at. A register photo is
 *  read on a screen; 1600 px is more than any screen here shows. */
const FIRST_LONG_SIDE = 1600;
/** Below this the picture stops being useful evidence; a file that still
 *  will not fit is refused in words instead of being sent as a smear. */
const MIN_LONG_SIDE = 320;
const QUALITIES = [0.86, 0.76, 0.66, 0.56, 0.46];

export interface PreparedPhoto {
  blob: Blob;
  filename: string;
  width: number;
  height: number;
}

function jpegName(name: string): string {
  const base = (name || "photo").replace(/\.[^./\\]+$/, "") || "photo";
  return `${base}.jpg`;
}

function encode(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

/**
 * Redraw the chosen picture as a JPEG of at most `PHOTO_MAX_BYTES`, in the
 * browser, before it is sent. Downsized to `FIRST_LONG_SIDE` on its longest
 * side, then re-encoded at falling quality, then shrunk again, until it
 * fits. Re-encoding also drops the original's metadata (a phone's GPS
 * position among it), which a register photo does not need to carry.
 *
 * The orientation the camera recorded is applied (`from-image`), so a
 * portrait photo is uploaded upright. White is painted underneath, so a
 * transparent PNG does not turn black as a JPEG.
 *
 * Throws an `Error` whose message is a sentence for the person: when the
 * browser cannot open the file as a picture at all (a PDF, a document), or
 * when it cannot be made small enough.
 */
export async function preparePhotoForUpload(file: File): Promise<PreparedPhoto> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new Error(
      `"${file.name}" is not a picture this browser can open. Choose a JPEG or PNG photo.`);
  }
  try {
    const longest = Math.max(bitmap.width, bitmap.height);
    let scale = Math.min(1, FIRST_LONG_SIDE / longest);
    // The first attempt always runs, at full size for a picture already
    // smaller than MIN_LONG_SIDE — such a picture is what it is, and was
    // refused before it had been tried (verification pass, handoff 61).
    let first = true;
    while (first || longest * scale >= MIN_LONG_SIDE) {
      first = false;
      const width = Math.max(1, Math.round(bitmap.width * scale));
      const height = Math.max(1, Math.round(bitmap.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("This browser cannot prepare the photo (no canvas).");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(bitmap, 0, 0, width, height);
      for (const quality of QUALITIES) {
        const blob = await encode(canvas, quality);
        if (blob && blob.size <= PHOTO_MAX_BYTES) {
          return { blob, filename: jpegName(file.name), width, height };
        }
      }
      scale *= 0.75;
    }
  } finally {
    bitmap.close();
  }
  throw new Error(
    `"${file.name}" could not be made smaller than 300 KB without becoming too small to read.`);
}
