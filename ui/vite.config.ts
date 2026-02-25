import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  server: {
    proxy: {
      "/api": "http://localhost:9999",
      "/events": "http://localhost:9999",
      "/health": "http://localhost:9999",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsInlineLimit: 0,
  },
});
