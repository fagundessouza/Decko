import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Evita CORS em desenvolvimento e mantém o front chamando caminhos relativos,
      // que é como ele roda em produção atrás de um único domínio.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // O alvo inclui máquina de caixa antiga; sem isso o bundle não roda em navegador
    // desatualizado e a falha aparece só no cliente.
    target: "es2020",
  },
});
