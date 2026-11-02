import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // host: true listens on 0.0.0.0 so the dev server is reachable from outside the container.
  server: { host: true, port: 5173, strictPort: true },
});
