import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/react/" : "/",
  root: fileURLToPath(new URL(".", import.meta.url)),
  build: {
    outDir: fileURLToPath(new URL("../python/sdpstudio_server/static/react", import.meta.url)),
    emptyOutDir: true,
    rollupOptions: { input: fileURLToPath(new URL("./react-index.html", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8788",
      "/ws": {
        target: "ws://127.0.0.1:8788",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"] },
}));
