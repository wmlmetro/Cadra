import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import {
  ENUM_SEED, ENUM_DEFAULT, enumLabel,
  type EnumName, type EnumOption,
} from "@/lib/enums";

/**
 * The model's enum sets, read from the server instead of declared here.
 *
 * `GET /api/v1/meta/enums` derives every set from the live Odoo Selection at
 * request time, so a value the model gains appears in these dropdowns without
 * a front-end release. That is the point: five hand-maintained copies of
 * these sets had drifted from the model, and a copy that must be maintained
 * is a copy that will drift again.
 *
 * `ENUM_SEED` is the placeholder, not the answer — it is what renders on the
 * first paint and what survives an offline start. It is held honest by
 * `tests/test_frontend_enums.py`, which fails when it disagrees with the
 * model, so falling back to it is safe rather than merely quiet.
 *
 * Cached for the session: these change when somebody edits a Python file, not
 * while a user is filling in a form.
 */

export type EnumSets = Record<string, EnumOption[]>;

export function useEnums() {
  const { data, isLoading } = useQuery<EnumSets>({
    queryKey: ["meta-enums"],
    queryFn: async () => (await apiGet<EnumSets>("/api/v1/meta/enums")).data,
    staleTime: 60 * 60_000,
    // The seed renders immediately and is replaced the moment the real sets
    // land. Without this the first paint of every form is an empty select.
    placeholderData: ENUM_SEED as unknown as EnumSets,
    // A failed metadata read must not blank a form. The seed is guarded
    // against the model, so the fallback is a correct set and not a guess.
    retry: 1,
  });
  return { sets: data ?? (ENUM_SEED as unknown as EnumSets), isLoading };
}

/**
 * One set, live. Falls back to the seed for that name.
 *
 * An unknown name returns `[]` rather than throwing — a set the server
 * publishes and this build has never heard of is not a reason to white-screen
 * a page.
 */
export function useEnum(name: EnumName): EnumOption[] {
  const { sets } = useEnums();
  return sets[name] ?? ENUM_SEED[name] ?? [];
}

/** `useEnum` plus a label lookup over the same live set. */
export function useEnumLabel(name: EnumName): (value: string | null | undefined) => string {
  const options = useEnum(name);
  return (value) => enumLabel(options, value);
}

export { ENUM_DEFAULT, enumLabel };
export type { EnumName, EnumOption };
