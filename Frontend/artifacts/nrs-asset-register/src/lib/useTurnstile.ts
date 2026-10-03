/**
 * Cloudflare Turnstile, for the two anonymous forms that send something on
 * a stranger's say-so: sign-in and "Forgot password?". Lifted out of
 * Login.tsx unchanged (handoff 45) so the second form cannot drift from the
 * first.
 *
 * One bundle serves every tenant, so the sitekey alone cannot decide whether
 * to show the widget: GET /api/v1/brand answers per host (`turnstile`). A
 * widget that fails to load must not become a lockout — the API is the real
 * gate — so `awaiting` is false once `broken` is true.
 */
import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { applyBrand, fetchBrand, getBrand } from "@/lib/brand";

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: string | HTMLElement,
        options: {
          sitekey: string;
          theme?: "light" | "dark" | "auto";
          callback: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
        }
      ) => string;
      reset: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
  }
}

const siteKey = import.meta.env.VITE_TURNSTILE_SITEKEY || "";

export function useTurnstile() {
  // Turnstile's own default is theme:"auto", which follows the OS. This app
  // themes by class with a persisted override (next-themes), so the widget
  // takes the resolved theme instead.
  const { resolvedTheme } = useTheme();
  const [token, setToken] = useState<string | null>(null);
  const [broken, setBroken] = useState(false);
  const [required, setRequired] = useState(getBrand().turnstile);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);

  // Re-read the brand on mount rather than trusting the boot-time value,
  // which may predate an operator enabling the challenge.
  useEffect(() => {
    let live = true;
    void fetchBrand().then((brand) => {
      if (!live) return;
      applyBrand(brand);
      setRequired(brand.turnstile);
    });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!siteKey || !required || !resolvedTheme) return;

    let script = document.getElementById("cloudflare-turnstile-script") as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement("script");
      script.id = "cloudflare-turnstile-script";
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }

    const onScriptError = () => setBroken(true);
    script.addEventListener("error", onScriptError);

    const renderWidget = () => {
      if (window.turnstile && containerRef.current && !widgetIdRef.current) {
        try {
          widgetIdRef.current = window.turnstile.render(containerRef.current, {
            sitekey: siteKey,
            theme: resolvedTheme === "dark" ? "dark" : "light",
            callback: (t: string) => setToken(t),
            "expired-callback": () => setToken(null),
            "error-callback": () => { setToken(null); setBroken(true); },
          });
        } catch (err) {
          console.error("Failed to render Turnstile widget:", err);
          setBroken(true);
        }
      }
    };

    if (window.turnstile) renderWidget();
    else script.addEventListener("load", renderWidget);

    return () => {
      if (script) {
        script.removeEventListener("load", renderWidget);
        script.removeEventListener("error", onScriptError);
      }
      if (widgetIdRef.current && window.turnstile) {
        try {
          window.turnstile.remove(widgetIdRef.current);
          widgetIdRef.current = null;
          setToken(null);
        } catch (err) {
          console.error("Failed to remove Turnstile widget:", err);
        }
      }
    };
    // `required` flips once /api/v1/brand answers; `resolvedTheme` is
    // undefined until next-themes hydrates and the widget takes its theme at
    // render time, so either change rebuilds it.
  }, [required, resolvedTheme]);

  /** After a refused submit: a used challenge token is single-use. */
  function reset() {
    if (window.turnstile && widgetIdRef.current) {
      try {
        window.turnstile.reset(widgetIdRef.current);
        setToken(null);
        setBroken(false);
      } catch (err) {
        console.error("Failed to reset Turnstile widget:", err);
      }
    }
  }

  const show = !!siteKey && required;
  return {
    containerRef,
    token,
    broken,
    show,
    awaiting: show && !token && !broken,
    reset,
  };
}
