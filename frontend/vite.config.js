import { defineConfig } from "vite";

const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8080";

export default defineConfig({
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
