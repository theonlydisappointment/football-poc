import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // host: true listens on 0.0.0.0 so the dev server is reachable from outside the container.
    host: true,
    port: 5173,
    strictPort: true,
    // Without VITE_API_URL the app calls /api on its own origin (as on Vercel); in local dev,
    // forward those calls to the API on port 8000.
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
