import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current directory.
  const env = loadEnv(mode, path.resolve(import.meta.dirname), "");

  const port = Number(env.PORT || process.env.PORT || 5173);
  if (Number.isNaN(port) || port <= 0) {
    throw new Error(`Invalid PORT value: "${env.PORT || process.env.PORT}"`);
  }

  const basePath = env.BASE_PATH || process.env.BASE_PATH || "/";
  const apiProxy = env.VITE_API_PROXY || process.env.VITE_API_PROXY;

  return {
    base: basePath,
    plugins: [
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "src"),
        "@assets": path.resolve(import.meta.dirname, "..", "..", "attached_assets"),
      },
      dedupe: ["react", "react-dom"],
    },
    root: path.resolve(import.meta.dirname),
    build: {
      outDir: path.resolve(import.meta.dirname, "dist/public"),
      emptyOutDir: true,
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        output: {
          manualChunks: {
            react:    ["react", "react-dom", "react/jsx-runtime", "scheduler"],
            tanstack: ["@tanstack/react-query", "@tanstack/react-table"],
            leaflet:  ["leaflet", "react-leaflet"],
            charts:   ["recharts"],
            radix:    [
              "@radix-ui/react-dialog",
              "@radix-ui/react-dropdown-menu",
              "@radix-ui/react-popover",
              "@radix-ui/react-tooltip",
              "@radix-ui/react-select",
              "@radix-ui/react-tabs",
              "@radix-ui/react-toast",
            ],
            icons:    ["lucide-react", "react-icons"],
          },
        },
      },
    },
    server: {
      port,
      strictPort: true,
      host: "0.0.0.0",
      allowedHosts: true,
      fs: {
        strict: true,
      },
      proxy: apiProxy
        ? {
            "/api": {
              target: apiProxy,
              changeOrigin: true,
              secure: false,
            },
          }
        : undefined,
    },
    preview: {
      port,
      host: "0.0.0.0",
      allowedHosts: true,
    },
  };
});

