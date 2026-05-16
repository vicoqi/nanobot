import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.MANAGER_API_URL ?? "http://127.0.0.1:8080";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      outDir: path.resolve(__dirname, "../nanobot/manager/static"),
      emptyOutDir: true,
      sourcemap: false,
    },
    server: {
      host: "127.0.0.1",
      port: 5175,
      strictPort: true,
      proxy: {
        "/api": { target, changeOrigin: true },
        "/admin": { target, changeOrigin: true },
      },
    },
  };
});
