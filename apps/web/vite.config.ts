import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// De "vitest/config", e não de "vite": é a mesma função, com o bloco `test` tipado.
import { defineConfig } from "vitest/config";

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
  test: {
    // jsdom e não o navegador: o que estes testes afirmam é sobre foco e marcação, que
    // o jsdom representa fielmente. Navegador de verdade custa minutos na esteira e se
    // paga quando houver afirmação sobre pintura — hoje não há.
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/setupTests.ts"],
    restoreMocks: true,
  },
});
