/**
 * Devices and codes (handoff 66 §2, §6) — the Asset Controller's.
 *
 * A device is bound to one person at a time. It is not a credential: the
 * person signs in as themselves and the phone names itself with the
 * `X-Cadra-Device` header, which the server checks against the binding.
 * Here the controller registers a device bound to a capturer, rebinds or
 * unbinds it, and deactivates it.
 *
 * Codes come in blocks: N (at most 500) asset codes issued to a device and
 * its person, drawn from the asset-code sequence under a lock. A capture
 * may use only a code reserved to its device and person. Returning a block
 * voids its unused codes — never reissued — and every block lists its codes
 * with their state (reserved → in review → active, or void).
 *
 * Every refusal is the server's sentence, verbatim — a rebind while the
 * device still carries a block issued to somebody else among them.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Smartphone } from "lucide-react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import type { CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import {
  AUDIT_KEY, CODE_STATE_WORDS, bindDevice, deactivateDevice, fetchAuditPeople, fetchBlock, fetchBlocks,
  fetchDevices, issueBlock, registerDevice, returnBlock,
  type AuditBlock, type AuditDevice, type AuditPeople, type CodeState,
} from "@/lib/auditCapture";
import { cn } from "@/lib/utils";
import {
  Btn, Empty, ErrorPanel, INPUT, Loading, PageHeader, Pill, invalidateAudit, n, when,
} from "./shared";

const MAX_BLOCK = 500;

export default function AuditDevices() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canManage = scopes.has(SCOPE.auditManage);

  useEffect(() => {
    setTitle("Devices and codes");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const devices = useQuery<AuditDevice[], CadraApiError>({
    queryKey: [...AUDIT_KEY, "devices"], queryFn: () => fetchDevices(), enabled: canManage,
  });
  const blocks = useQuery<AuditBlock[], CadraApiError>({
    queryKey: [...AUDIT_KEY, "blocks"], queryFn: () => fetchBlocks(), enabled: canManage,
  });
  const people = useQuery<AuditPeople, CadraApiError>({
    queryKey: [...AUDIT_KEY, "people"], queryFn: fetchAuditPeople, enabled: canManage,
  });

  if (!canManage) {
    return <ScopeRefusal scope={SCOPE.auditManage} detail="The Asset Controller holds it." />;
  }
  const capturers = people.data?.capturers ?? [];

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={<Smartphone size={15} />} title="Devices and codes">
        Register each audit phone bound to the person who carries it, and issue it a block of asset codes. A capture
        may use only a code reserved to its own device and person; returning a block voids the codes it did not use,
        and a voided code is never issued again.
      </PageHeader>
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {people.error && <ErrorPanel err={people.error} />}
        <section className="space-y-2">
          <h2 className="text-[13px] font-bold">Devices</h2>
          <RegisterDevice capturers={capturers} />
          {devices.error && <ErrorPanel err={devices.error} />}
          {devices.isLoading ? <Loading what="Reading the devices…" /> : (devices.data ?? []).length === 0 ? (
            <Empty testid="devices-empty">No device is registered.</Empty>
          ) : (
            <table className="w-full text-xs" data-testid="audit-devices">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2">Device</th>
                  <th className="text-left px-3">Bound to</th>
                  <th className="text-left px-3">Open block</th>
                  <th className="text-left px-3">Registered</th>
                  <th className="text-left px-3">Change</th>
                </tr>
              </thead>
              <tbody>
                {(devices.data ?? []).map(d => <DeviceRow key={d.id} d={d} capturers={capturers} blocks={blocks.data ?? []} />)}
              </tbody>
            </table>
          )}
        </section>

        <section className="space-y-2">
          <h2 className="text-[13px] font-bold">Code blocks</h2>
          <IssueBlock devices={(devices.data ?? []).filter(d => d.active && d.bound_to && !d.open_block_id)} />
          {blocks.error && <ErrorPanel err={blocks.error} />}
          {blocks.isLoading ? <Loading what="Reading the blocks…" /> : (blocks.data ?? []).length === 0 ? (
            <Empty testid="blocks-empty">No block of codes has been issued.</Empty>
          ) : (
            <div className="space-y-2" data-testid="audit-blocks">
              {(blocks.data ?? []).map(b => <BlockRow key={b.id} b={b} />)}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function PersonSelect({ value, onChange, capturers, testid, allowNobody }: {
  value: number | null; onChange: (v: number | null) => void; capturers: { id: number; name: string; login: string }[];
  testid: string; allowNobody?: boolean;
}) {
  return (
    <select className={INPUT} data-testid={testid} value={value ?? ""} onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{allowNobody ? "Nobody" : "Choose a capturer…"}</option>
      {capturers.map(p => <option key={p.id} value={p.id}>{p.name} ({p.login})</option>)}
    </select>
  );
}

function RegisterDevice({ capturers }: { capturers: { id: number; name: string; login: string }[] }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [user, setUser] = useState<number | null>(null);
  const m = useMutation<AuditDevice, CadraApiError>({
    mutationFn: () => registerDevice(name, user),
    onSuccess: () => { invalidateAudit(qc); setName(""); setUser(null); },
  });
  return (
    <form className="flex flex-wrap gap-2 items-center" data-testid="register-device-form"
          onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="What is written on the device"
             className={cn(INPUT, "w-64")} data-testid="input-device-name" aria-label="Device name" />
      <PersonSelect value={user} onChange={setUser} capturers={capturers} testid="select-device-person" allowNobody />
      <Btn type="submit" testid="button-register-device" disabled={!name.trim()} pending={m.isPending}>Register the device</Btn>
      {capturers.length === 0 && <span className="text-[11px] text-muted-foreground">Nobody holds the Audit Capturer role yet.</span>}
      {m.data && <span className="text-[11px] text-green-800 dark:text-green-300" data-testid="device-registered">
        Registered {m.data.name} — its code is <span className="font-mono">{m.data.device_code}</span>.</span>}
      {m.error && <div className="w-full"><ErrorPanel err={m.error} testid="register-device-error" /></div>}
    </form>
  );
}

function DeviceRow({ d, capturers, blocks }: {
  d: AuditDevice; capturers: { id: number; name: string; login: string }[]; blocks: AuditBlock[];
}) {
  const qc = useQueryClient();
  const [to, setTo] = useState<number | null>(d.bound_to?.id ?? null);
  useEffect(() => { setTo(d.bound_to?.id ?? null); }, [d.bound_to?.id]);
  const bind = useMutation<AuditDevice, CadraApiError>({
    mutationFn: () => bindDevice(d.id, to), onSuccess: () => invalidateAudit(qc),
  });
  const off = useMutation<AuditDevice, CadraApiError>({
    mutationFn: () => deactivateDevice(d.id), onSuccess: () => invalidateAudit(qc),
  });
  const open = blocks.find(b => b.id === d.open_block_id);
  // A person no longer a capturer can still be the current binding: keep
  // them selectable so the select shows the truth.
  const options = d.bound_to && !capturers.some(c => c.id === d.bound_to!.id)
    ? [...capturers, { id: d.bound_to.id, name: d.bound_to.name, login: "" }] : capturers;
  return (
    <tr className={cn("border-b border-border align-top", !d.active && "opacity-60")} data-testid={`device-row-${d.id}`}>
      <td className="px-3 py-2">
        <div className="font-semibold">{d.name}</div>
        <div className="font-mono text-muted-foreground" data-testid="device-code">{d.device_code}</div>
        {!d.active && <Pill tone="red">Deactivated</Pill>}
      </td>
      <td className="px-3 py-2">
        {d.bound_to ? <>{d.bound_to.name}<div className="text-muted-foreground">since {when(d.bound_at)}{d.bound_by && <> · by {d.bound_by.name}</>}</div></> : "Nobody"}
      </td>
      <td className="px-3 py-2">{open ? <>{open.name} <span className="text-muted-foreground">({open.first_code} – {open.last_code})</span></> : "—"}</td>
      <td className="px-3 py-2 text-muted-foreground">{d.registered_by?.name ?? "—"}, {when(d.registered_at)}</td>
      <td className="px-3 py-2">
        {d.active && (
          <div className="flex flex-wrap gap-2 items-center">
            <PersonSelect value={to} onChange={setTo} capturers={options} testid={`select-bind-${d.id}`} allowNobody />
            <Btn kind="plain" testid={`button-bind-${d.id}`} disabled={to === (d.bound_to?.id ?? null)} pending={bind.isPending}
                 onClick={() => bind.mutate()}>{to == null ? "Unbind" : d.bound_to ? "Rebind" : "Bind"}</Btn>
            <Btn kind="plain" testid={`button-deactivate-${d.id}`} pending={off.isPending} onClick={() => off.mutate()}>Deactivate</Btn>
          </div>
        )}
        {bind.error && <ErrorPanel err={bind.error} testid="bind-error" />}
        {off.error && <ErrorPanel err={off.error} testid="deactivate-error" />}
      </td>
    </tr>
  );
}

function IssueBlock({ devices }: { devices: AuditDevice[] }) {
  const qc = useQueryClient();
  const [device, setDevice] = useState<number | null>(null);
  const [size, setSize] = useState("50");
  const m = useMutation<AuditBlock, CadraApiError>({
    mutationFn: () => issueBlock(device as number, Number(size)),
    onSuccess: () => { invalidateAudit(qc); setDevice(null); },
  });
  const sizeOk = /^\d+$/.test(size) && Number(size) >= 1 && Number(size) <= MAX_BLOCK;
  return (
    <div className="space-y-1">
      <form className="flex flex-wrap gap-2 items-center" data-testid="issue-block-form"
            onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <select className={INPUT} data-testid="select-block-device" value={device ?? ""}
                onChange={e => setDevice(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Choose a device…</option>
          {devices.map(d => <option key={d.id} value={d.id}>{d.name} — {d.bound_to?.name}</option>)}
        </select>
        <label className="text-[11px] text-muted-foreground">Codes
          <input value={size} onChange={e => setSize(e.target.value)} inputMode="numeric"
                 className={cn(INPUT, "w-20 ml-1.5")} data-testid="input-block-size" />
        </label>
        <Btn type="submit" testid="button-issue-block" disabled={device == null || !sizeOk} pending={m.isPending}>Issue the block</Btn>
        <span className="text-[11px] text-muted-foreground">At most {MAX_BLOCK}. Only an active device bound to a person, with no open block, is offered.</span>
      </form>
      {m.data && <p className="text-[11px] text-green-800 dark:text-green-300" data-testid="block-issued">
        Issued {m.data.name}: {n(m.data.size)} codes, {m.data.first_code} – {m.data.last_code}, to {m.data.issued_to?.name ?? "—"}.</p>}
      {m.error && <ErrorPanel err={m.error} testid="issue-block-error" />}
    </div>
  );
}

const STATE_TONE: Record<CodeState, "plain" | "amber" | "green" | "red"> = {
  reserved: "plain", in_review: "amber", active: "green", void: "red",
};

function BlockRow({ b }: { b: AuditBlock }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [returning, setReturning] = useState(false);
  const [reason, setReason] = useState("");
  const codes = useQuery<AuditBlock, CadraApiError>({
    queryKey: [...AUDIT_KEY, "block", b.id], queryFn: () => fetchBlock(b.id), enabled: open,
  });
  const ret = useMutation<AuditBlock, CadraApiError>({
    mutationFn: () => returnBlock(b.id, reason), onSuccess: () => { invalidateAudit(qc); setReturning(false); },
  });
  const counts = Object.entries(b.codes_by_state).filter(([, v]) => v) as [CodeState, number][];
  return (
    <div className="rounded-xl border border-border p-3" data-testid={`block-row-${b.id}`} data-state={b.state}>
      <div className="flex flex-wrap gap-2 items-center text-[12px]">
        <span className="font-semibold">{b.name}</span>
        <Pill tone={b.state === "issued" ? "green" : "plain"}>{b.state === "issued" ? "Issued" : "Returned"}</Pill>
        <span className="font-mono">{b.first_code} – {b.last_code}</span>
        <span className="text-muted-foreground">{n(b.size)} codes · {b.device.name} · {b.issued_to?.name ?? "—"} · issued {when(b.issued_at)} by {b.issued_by?.name ?? "—"}</span>
      </div>
      <div className="flex flex-wrap gap-1.5 mt-1.5" data-testid="block-counts">
        {counts.map(([k, v]) => <Pill key={k} tone={STATE_TONE[k]}>{CODE_STATE_WORDS[k]}: {n(v)}</Pill>)}
      </div>
      {b.state === "returned" && (
        <p className="text-[11px] text-muted-foreground mt-1">Returned {when(b.returned_at)} by {b.returned_by?.name ?? "—"}{b.return_reason && <>: {b.return_reason}</>}.</p>
      )}
      <div className="flex gap-2 mt-2 flex-wrap items-center">
        <Btn kind="plain" testid={`button-block-codes-${b.id}`} onClick={() => setOpen(o => !o)}>{open ? "Hide the codes" : "Show the codes"}</Btn>
        {b.state === "issued" && !returning && (
          <Btn kind="plain" testid={`button-return-block-${b.id}`} onClick={() => setReturning(true)}>Return the block</Btn>
        )}
      </div>
      {returning && (
        <div className="mt-2 space-y-1.5" data-testid="return-block-form">
          <p className="text-[12px]">The codes this block has not used are voided, and never issued again. Codes already on a capture keep their state.</p>
          <div className="flex gap-2 items-center flex-wrap">
            <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Why (optional)" className={cn(INPUT, "w-72")}
                   data-testid="input-return-block-reason" />
            <Btn testid="button-return-block-send" pending={ret.isPending} onClick={() => ret.mutate()}>Return it</Btn>
            <Btn kind="plain" onClick={() => setReturning(false)}>Cancel</Btn>
          </div>
          {ret.error && <ErrorPanel err={ret.error} testid="return-block-error" />}
        </div>
      )}
      {ret.data?.voided_now != null && <p className="text-[11px] mt-1" data-testid="block-voided-now">{n(ret.data.voided_now)} unused codes voided.</p>}
      {open && (
        <div className="mt-2">
          {codes.error && <ErrorPanel err={codes.error} />}
          {codes.isLoading ? <Loading what="Reading the codes…" /> : (
            <table className="w-full text-xs" data-testid={`block-codes-${b.id}`}>
              <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr><th className="text-left py-1 pr-3">Code</th><th className="text-left pr-3">State</th><th className="text-left pr-3">Used</th><th className="text-left">What it became</th></tr>
              </thead>
              <tbody>
                {(codes.data?.codes ?? []).map(c => (
                  <tr key={c.code} data-testid={`code-${c.code}`} data-state={c.state}>
                    <td className="py-0.5 pr-3 font-mono">{c.code}</td>
                    <td className="pr-3"><Pill tone={STATE_TONE[c.state]}>{CODE_STATE_WORDS[c.state]}</Pill></td>
                    <td className="pr-3 text-muted-foreground">{c.used_at ? when(c.used_at) : "—"}</td>
                    <td className="text-muted-foreground">
                      {c.asset_id ? <>asset {c.asset_id}</> : c.capture_id ? <>capture {c.capture_id.slice(0, 8)}</> : "—"}
                      {c.void_reason && <> · {c.void_reason}</>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
