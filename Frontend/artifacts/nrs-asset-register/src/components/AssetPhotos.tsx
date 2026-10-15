/**
 * The pictures of an asset (handoff 61 §5): its photos and Internal Audit's
 * verification evidence, in ONE list, each labelled with what it is.
 *
 * - **Photo** — added here or by the mobile app; never deleted or replaced.
 *   One that no longer stands is *superseded* with a reason: it stays in the
 *   list, dimmed, with who superseded it, when and why.
 * - **IAD evidence** — what IAD attached when it verified the receipt. It
 *   obeys the evidence guard: somebody without `evidence:read` is shown
 *   "IAD evidence: N items" and nothing that opens one.
 *
 * Every picture is fetched with the bearer token and shown from a blob URL —
 * the app has no Odoo session, so an `<img src>` pointing at the API would
 * be refused.
 *
 * *Add photo* and *Supersede* are drawn only for `assets:write`. A chosen
 * picture is redrawn in the browser as a JPEG under 300 KB (AI-NFR-07)
 * before it is sent, so the server's size refusal is never what a person
 * meets from here; the server still sniffs and checks what arrives.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, FileText, Image as ImageIcon, Loader2, Upload, X } from "lucide-react";
import type { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { formatIsoDateTime } from "@/lib/utils";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { openGateEvidenceFile } from "@/lib/gateEvidence";
import {
  assetPhotosKey, fetchAssetPhotos, fetchPictureObjectUrl, preparePhotoForUpload,
  supersedeAssetPhoto, uploadAssetPhoto,
  type AssetPicture, type PreparedPhoto,
} from "@/lib/assetPhotos";

const SOURCE_WORDS: Record<string, string> = {
  web: "Web app",
  mobile: "Mobile app",
  gate_evidence: "IAD verification",
};

function sizeWords(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function when(utc: string | null | undefined): string {
  return utc ? formatIsoDateTime(utc.replace(" ", "T")) : "";
}

function isImage(p: Pick<AssetPicture, "mimetype">): boolean {
  return !!p.mimetype?.startsWith("image/");
}

/** The picture's bytes as an object URL, fetched once, let go on unmount. */
function useObjectUrl(picture: AssetPicture, enabled: boolean) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<CadraApiError | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    let made: string | null = null;
    fetchPictureObjectUrl(picture)
      .then((u) => {
        made = u;
        if (live) setUrl(u);
        else URL.revokeObjectURL(u);
      })
      .catch((e) => { if (live) setError(e as CadraApiError); });
    return () => {
      live = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [picture.url, picture.mimetype, enabled]);
  return { url, error };
}

function SupersedeForm({ assetId, photo, onDone }: {
  assetId: string | number; photo: AssetPicture; onDone: () => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const mutation = useMutation<AssetPicture, CadraApiError>({
    mutationFn: () => supersedeAssetPhoto(assetId, photo.id, reason.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assetPhotosKey(assetId) });
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "asset-history" });
      onDone();
    },
  });
  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => { e.preventDefault(); if (reason.trim()) mutation.mutate(); }}
      data-testid={`asset-photo-supersede-form-${photo.id}`}
    >
      <label className="block text-[11px] font-medium text-muted-foreground" htmlFor={`supersede-reason-${photo.id}`}>
        Why does this photo no longer stand? (required — it is kept, and the reason is recorded)
      </label>
      <textarea
        id={`supersede-reason-${photo.id}`}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
        className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
        data-testid="asset-photo-supersede-reason"
      />
      {mutation.error && <ApiErrorMessage err={mutation.error} />}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!reason.trim() || mutation.isPending}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary text-primary-foreground text-xs disabled:opacity-60"
          data-testid="asset-photo-supersede-confirm"
        >
          {mutation.isPending && <Loader2 size={12} className="animate-spin" />}
          Supersede photo
        </button>
        <button
          type="button"
          onClick={onDone}
          className="px-2.5 py-1 rounded-lg border border-border text-xs"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function PictureCard({ assetId, picture, canWrite }: {
  assetId: string | number; picture: AssetPicture; canWrite: boolean;
}) {
  const image = isImage(picture);
  const { url, error } = useObjectUrl(picture, image);
  const [superseding, setSuperseding] = useState(false);
  const [openError, setOpenError] = useState<CadraApiError | null>(null);
  const isPhoto = picture.kind === "photo";
  const superseded = picture.superseded;
  const who = picture.uploaded_by?.name || picture.uploaded_by_name || "somebody unrecorded";

  const openFile = async () => {
    setOpenError(null);
    try {
      await openGateEvidenceFile({
        id: picture.id, name: picture.filename || "evidence",
        mimetype: picture.mimetype, size: picture.size, url: picture.url,
      });
    } catch (e) {
      setOpenError(e as CadraApiError);
    }
  };

  return (
    <li
      className="bg-card border border-card-border rounded-xl overflow-hidden flex flex-col"
      data-testid={`asset-picture-${picture.kind}-${picture.id}`}
      data-kind={picture.kind}
      data-superseded={superseded ? "true" : "false"}
    >
      <div className={`relative aspect-[4/3] bg-muted/40 flex items-center justify-center ${superseded ? "opacity-50" : ""}`}>
        {image && url && (
          <a href={url} target="_blank" rel="noopener" className="block w-full h-full" title="Open full size">
            <img
              src={url}
              alt={picture.caption || picture.filename || (isPhoto ? "Photo of the asset" : "IAD evidence")}
              className="w-full h-full object-cover"
              data-testid="asset-picture-image"
            />
          </a>
        )}
        {image && !url && !error && <Loader2 size={16} className="animate-spin text-muted-foreground" />}
        {image && error && <p className="px-3 text-[11px] text-red-700 dark:text-red-400">{error.message}</p>}
        {!image && (
          <button type="button" onClick={openFile} className="flex flex-col items-center gap-1 text-xs text-foreground">
            <FileText size={22} className="text-muted-foreground" />
            <span className="truncate max-w-[12rem]">{picture.filename || "Evidence file"}</span>
            <span className="text-[10px] text-muted-foreground">Open</span>
          </button>
        )}
        <span
          className={`absolute top-2 left-2 px-1.5 py-0.5 rounded-md text-[10px] font-semibold ${
            isPhoto ? "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200"
                    : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"}`}
          data-testid="asset-picture-kind"
        >
          {isPhoto ? "Photo" : "IAD evidence"}
        </span>
        {superseded && (
          <span className="absolute top-2 right-2 px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-zinc-800 text-white">
            Superseded
          </span>
        )}
      </div>
      <div className="p-3 space-y-1 text-[11px] text-muted-foreground flex-1">
        {picture.caption && <p className="text-xs text-foreground">{picture.caption}</p>}
        <p>
          {isPhoto ? "Added by " : "Attached by "}<span className="text-foreground">{who}</span>
          {picture.uploaded_at && <> on {when(picture.uploaded_at)}</>}
        </p>
        <p>
          {SOURCE_WORDS[picture.source] ?? picture.source}
          {picture.width && picture.height ? ` · ${picture.width} × ${picture.height}` : ""}
          {picture.size ? ` · ${sizeWords(picture.size)}` : ""}
          {picture.mimetype ? ` · ${picture.mimetype}` : ""}
        </p>
        {superseded && (
          <p className="text-foreground" data-testid={`asset-photo-superseded-${picture.id}`}>
            Superseded by {superseded.by?.name || superseded.by_name || "somebody unrecorded"}
            {superseded.at && <> on {when(superseded.at)}</>}: “{superseded.reason}”
          </p>
        )}
        {openError && <ApiErrorMessage err={openError} />}
        {isPhoto && canWrite && !superseded && !superseding && (
          <button
            type="button"
            onClick={() => setSuperseding(true)}
            className="mt-1 text-[11px] underline text-foreground"
            data-testid={`asset-photo-supersede-${picture.id}`}
          >
            Supersede…
          </button>
        )}
        {superseding && (
          <SupersedeForm assetId={assetId} photo={picture} onDone={() => setSuperseding(false)} />
        )}
      </div>
    </li>
  );
}

function AddPhoto({ assetId, full }: { assetId: string | number; full: boolean }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [prepared, setPrepared] = useState<PreparedPhoto | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [caption, setCaption] = useState("");

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const reset = () => {
    setPrepared(null);
    setPreview(null);
    setCaption("");
    setProblem(null);
    if (input.current) input.current.value = "";
  };

  const upload = useMutation<AssetPicture, CadraApiError>({
    mutationFn: () => uploadAssetPhoto(assetId, prepared!.blob, prepared!.filename, caption),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assetPhotosKey(assetId) });
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "asset-history" });
      reset();
    },
  });

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setProblem(null);
    upload.reset();
    setPreparing(true);
    try {
      const p = await preparePhotoForUpload(file);
      setPrepared(p);
      setPreview(URL.createObjectURL(p.blob));
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setPreparing(false);
    }
  };

  return (
    <div className="bg-card border border-card-border rounded-xl p-4" data-testid="asset-photo-add-panel">
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/*"
        className="hidden"
        onChange={(e) => choose(e.target.files?.[0])}
        data-testid="asset-photo-input"
      />
      {!prepared && (
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={preparing || full}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs disabled:opacity-60"
            data-testid="asset-photo-add"
          >
            {preparing ? <Loader2 size={13} className="animate-spin" /> : <Camera size={13} />}
            Add photo
          </button>
          <p className="text-[11px] text-muted-foreground">
            {full
              ? "This asset holds the most photos it may (12). Supersede one it no longer needs to add another."
              : "JPEG or PNG. The picture is made smaller than 300 KB on this device before it is sent."}
          </p>
        </div>
      )}
      {problem && <p className="mt-2 text-xs text-red-700 dark:text-red-400" data-testid="asset-photo-problem">{problem}</p>}
      {prepared && (
        <form
          className="flex flex-col sm:flex-row gap-4"
          onSubmit={(e) => { e.preventDefault(); upload.mutate(); }}
        >
          {preview && (
            <img src={preview} alt="The photo to be added" className="w-40 h-28 object-cover rounded-lg border border-border" />
          )}
          <div className="flex-1 space-y-2">
            <p className="text-[11px] text-muted-foreground">
              Ready to send: {prepared.width} × {prepared.height}, {sizeWords(prepared.blob.size)} JPEG.
            </p>
            <label className="block text-[11px] font-medium text-muted-foreground" htmlFor="asset-photo-caption">
              Caption (optional)
            </label>
            <input
              id="asset-photo-caption"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
              placeholder="e.g. Tag on the left side panel"
              data-testid="asset-photo-caption"
            />
            {upload.error && <ApiErrorMessage err={upload.error} />}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={upload.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs disabled:opacity-60"
                data-testid="asset-photo-upload"
              >
                {upload.isPending ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                Upload photo
              </button>
              <button
                type="button"
                onClick={reset}
                disabled={upload.isPending}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border text-xs"
              >
                <X size={12} /> Cancel
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}

export function AssetPhotos({ assetId }: { assetId: string | number }) {
  const scopes = useScopes();
  const canWrite = scopes.has(SCOPE.assetsWrite);
  const { data, isLoading, error } = useQuery({
    queryKey: assetPhotosKey(assetId),
    queryFn: () => fetchAssetPhotos(assetId),
    enabled: !!assetId,
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="asset-photos-loading">
        <Loader2 size={13} className="animate-spin" /> Loading the pictures of this asset…
      </div>
    );
  }
  if (error) {
    return (
      <div className="bg-card border border-card-border rounded-xl px-5 py-4" data-testid="asset-photos-error">
        <ApiErrorMessage err={error as CadraApiError} />
      </div>
    );
  }
  if (!data) return null;

  const { items, photos, iad_evidence: evidence } = data;
  const full = photos.standing >= photos.max_standing;

  return (
    <div className="space-y-4" data-testid="asset-photos">
      {canWrite && <AddPhoto assetId={assetId} full={full} />}

      <p className="text-[11px] text-muted-foreground" data-testid="asset-photos-count">
        {photos.count === 0
          ? "No photos of this asset yet."
          : `${photos.standing} of ${photos.max_standing} photos${
              photos.superseded ? ` (and ${photos.superseded} superseded, kept and not counted)` : ""}.`}
      </p>

      {!evidence.readable && evidence.count > 0 && (
        <p
          className="flex items-center gap-1.5 text-xs text-foreground bg-muted/40 border border-border rounded-lg px-3 py-2"
          data-testid="asset-photos-evidence-count"
        >
          <ImageIcon size={13} className="text-muted-foreground" />
          {evidence.summary ?? `IAD evidence: ${evidence.count} item${evidence.count === 1 ? "" : "s"}`}
        </p>
      )}

      {items.length > 0 && (
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="asset-pictures">
          {items.map((p) => (
            <PictureCard key={`${p.kind}-${p.id}`} assetId={assetId} picture={p} canWrite={canWrite} />
          ))}
        </ul>
      )}
    </div>
  );
}
