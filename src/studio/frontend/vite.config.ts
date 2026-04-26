import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  root,
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2022",
    reportCompressedSize: true,
    chunkSizeWarningLimit: 800,
  },
  server: { port: 5173, strictPort: true },
  base: "/",
});
