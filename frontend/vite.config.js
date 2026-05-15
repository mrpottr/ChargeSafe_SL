import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const frontendPort = Number(env.FRONTEND_PORT || 5173);
  const runningInContainer = Boolean(process.env.HOSTNAME);
  const proxyTarget =
    process.env.VITE_API_PROXY_TARGET ||
    process.env.FRONTEND_API_PROXY_TARGET ||
    env.VITE_API_PROXY_TARGET ||
    env.FRONTEND_API_PROXY_TARGET ||
    (runningInContainer ? "http://backend:8000" : "http://localhost:8000");

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: frontendPort,
      strictPort: true,
      origin: `http://localhost:${frontendPort}`,
      hmr: {
        host: "localhost",
        clientPort: frontendPort,
        protocol: "ws",
      },
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

