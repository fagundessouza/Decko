/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Origem da API quando ela não está atrás do mesmo domínio da tela.
   *
   *  Vazia em desenvolvimento: o proxy do Vite encaminha `/api` para a porta 8000, e o
   *  front segue chamando caminho relativo. Preenchida quando a tela é servida de outro
   *  lugar — `https://api.seudominio.com.br`, sem barra no fim. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
