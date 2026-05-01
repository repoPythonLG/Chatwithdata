import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8001";
const serverHost = process.env.VITE_HOST ?? "127.0.0.1";
const serverPort = Number(process.env.VITE_PORT ?? "5173");
const allowedHosts = (
  process.env.VITE_ALLOWED_HOSTS ??
  process.env.CLOUDERA_PUBLIC_HOST ??
  ""
)
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);
const hmr =
  process.env.VITE_HMR === "false"
    ? false
    : {
        host: process.env.VITE_HMR_HOST || undefined,
        clientPort: process.env.VITE_HMR_CLIENT_PORT
          ? Number(process.env.VITE_HMR_CLIENT_PORT)
          : undefined
      };

function clouderaHealthPlugin(): Plugin {
  return {
    name: "cloudera-healthz",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split("?", 1)[0];
        if (path !== "/healthz") {
          next();
          return;
        }
        res.statusCode = 200;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "ok", service: "chat-with-data" }));
      });
    }
  };
}

export default defineConfig({
  plugins: [clouderaHealthPlugin(), react()],
  build: {
    chunkSizeWarningLimit: 5500
  },
  server: {
    host: serverHost,
    port: serverPort,
    strictPort: true,
    allowedHosts: allowedHosts.length ? allowedHosts : undefined,
    hmr,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "")
      }
    }
  }
});
