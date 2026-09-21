import type { ApprovalStatus } from "@/types";
import StatusPill from "@/components/StatusPill";
import LifecyclePill from "@/components/LifecyclePill";

/**
 * The status slot of an ASSET, wherever one is drawn — the one place that
 * decides its shape, so the hero, the register card, the register column and
 * the dashboard queue cannot disagree with each other.
 *
 * One slot, not two pills side by side. An asset carries two facts: its
 * lifecycle (`lifecycleState`, the model's `state`) and a data-quality verdict
 * (`status`). The verdict only exists for an asset in service. "Missing ·
 * Cleared" side by side is a contradiction on its face, and a data-quality
 * verdict about an asset nobody can find is not a fact anyone holds. So: not
 * active → the lifecycle, and nothing else; active → the verdict, as before.
 *
 * `lifecycleState` absent (a mock row, or a payload that never carried it)
 * falls back to the verdict — which, since `deriveStatus` stopped falling
 * through, is "Not in service" rather than "Cleared" for anything not active.
 */
export default function AssetStatusPills({ status, lifecycleState, showDot }: {
  status: ApprovalStatus;
  lifecycleState?: string;
  showDot?: boolean;
}) {
  if (lifecycleState && lifecycleState !== "active") {
    return <LifecyclePill state={lifecycleState} showDot={showDot} />;
  }
  return <StatusPill status={status} showDot={showDot} />;
}
