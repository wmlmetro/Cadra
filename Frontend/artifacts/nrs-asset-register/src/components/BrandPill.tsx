import { getBrand } from "@/lib/brand";

/**
 * The little tenant badge that heads every report and settings page.
 *
 * Exists so the brand is resolved in ONE place. One static bundle serves every
 * tenant — lib/brand.ts fetches the brand for the current host at startup — so
 * a hardcoded "NRS" pill renders the wrong mark on Jaiz, GTB and LASG. That is
 * exactly what happened across seven pages before this component existed.
 */
export default function BrandPill({ className = "" }: { className?: string }) {
  const brand = getBrand();
  return (
    <span
      className={
        "inline-flex items-center px-2 py-1 rounded-lg text-[10px] font-extrabold tracking-wider " +
        className
      }
      style={{ background: brand.primary, color: "white" }}
      data-testid="brand-pill"
    >
      {brand.short_name || brand.name}
    </span>
  );
}
