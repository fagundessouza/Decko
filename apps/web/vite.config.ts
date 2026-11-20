import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// De "vitest/config", e não de "vite": é a mesma função, com o bloco `test` tipado.
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    /* O pacote inteiro fica guardado no aparelho.
     *
     * Sem isto, internet caída não deixava nem abrir: o navegador mostrava a própria tela
     * de erro, e para quem está no balcão ou na lavoura isso é indistinguível de "o Decko
     * morreu". Guardar o pacote é a metade barata do offline-first da
     * docs/adr/0019-offline-first.md — a tela abre; o que ela deixa **fazer** sem rede é a
     * outra metade, que continua bloqueada pelas perguntas em aberto daquela ADR.
     */
    VitePWA({
      /* "prompt", e não "autoUpdate": o alvo inclui PDV, e atualização que recarrega
       * sozinha pode cair no meio de uma venda. Quem escolhe a hora é quem está operando. */
      registerType: "prompt",
      includeAssets: ["favicon.svg", "icons.svg"],
      manifest: {
        name: "Decko",
        short_name: "Decko",
        description: "Gestão e frente de caixa",
        lang: "pt-BR",
        start_url: "/",
        display: "standalone",
        background_color: "#1e2a38",
        theme_color: "#1e2a38",
        icons: [
          // O ícone definitivo é trabalho de marca, não de build — ver docs/BRAND.md.
          { src: "favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        /* Qualquer caminho abre o index guardado: a navegação é por estado, e sem isto
         * recarregar a página fora da raiz falharia justamente quando não há rede. */
        navigateFallback: "index.html",
        // A API nunca sai do cache. Saldo e cadastro vêm do servidor ou não vêm — guardar
        // resposta aqui seria mostrar número velho com cara de atual.
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
      },
      devOptions: {
        // Desligado em desenvolvimento: service worker guardando pacote enquanto se edita
        // código é a origem clássica de "mas eu já corrigi isso".
        enabled: false,
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      // Evita CORS em desenvolvimento e mantém o front chamando caminhos relativos,
      // que é como ele roda em produção atrás de um único domínio.
      "/api": {
        // 8000 é o padrão do `.claude/launch.json`. `DECKO_API_PROXY` existe para quando
        // a porta já está ocupada por outra instância — acontece com a API deixada de pé
        // de uma sessão anterior, e aí o front conversa com o servidor errado sem avisar.
        target: process.env.DECKO_API_PROXY ?? "http://127.0.0.1:8000",
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
    /* O produto é brasileiro e as datas são lidas por quem está no Brasil. Sem fixar o
     * fuso, o teste que guarda a data local passaria por engano na esteira, que roda em
     * UTC: lá o dia local e o dia UTC coincidem, e o defeito que ele vigia desaparece. */
    env: { TZ: "America/Sao_Paulo" },
    restoreMocks: true,
  },
});
