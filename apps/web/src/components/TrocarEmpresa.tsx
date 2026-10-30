import { useState } from "react";

import { switchCompany } from "../lib/api";
import type { SessionInfo } from "../lib/api";
import { session } from "../lib/session";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { Modal } from "./Modal";
import { TextField } from "./TextField";

interface Props {
  open: boolean;
  /** A empresa de agora, que não aparece como destino. */
  slugAtual: string;
  /** O e-mail de quem está na tela: quase sempre o mesmo na outra empresa. */
  emailAtual: string;
  onClose: () => void;
  onTrocado: (info: SessionInfo) => void;
}

/* Trocar de empresa.
 *
 * A lista é das empresas que já entraram **neste aparelho** — não existe rota que responda
 * em quais empresas um e-mail tem conta, e isso é decisão, não falta: a consulta exigiria
 * atravessar o isolamento com privilégio e devolveria um oráculo de enumeração. Ver
 * docs/adr/0012-troca-de-empresa.md.
 *
 * A senha é pedida porque as contas são independentes, com hashes independentes. Aceitar a
 * sessão de uma empresa como prova para entrar na outra faria o token de uma valer na
 * outra, que é a travessia que o isolamento existe para impedir. */
export function TrocarEmpresa({ open, slugAtual, emailAtual, onClose, onTrocado }: Props) {
  const [destino, setDestino] = useState<string | null>(null);
  const [outroSlug, setOutroSlug] = useState("");
  const [email, setEmail] = useState(emailAtual);
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [entrando, setEntrando] = useState(false);

  const conhecidas = session.getCompanies().filter((item) => item.slug !== slugAtual);
  const slug = destino === "" ? outroSlug.trim().toLowerCase() : (destino ?? "");

  function fechar() {
    setDestino(null);
    setOutroSlug("");
    setSenha("");
    setErro(null);
    onClose();
  }

  async function entrar() {
    if (!slug || !email.trim() || !senha) return;
    setEntrando(true);
    setErro(null);
    try {
      const info = await switchCompany({ tenantSlug: slug, email, password: senha });
      setSenha("");
      setDestino(null);
      onTrocado(info);
    } catch (causa) {
      setErro(causa instanceof Error ? causa.message : "Não foi possível entrar.");
    } finally {
      setEntrando(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Trocar de empresa"
      description="Cada empresa tem a sua conta, com a sua senha."
      onClose={fechar}
      footer={
        destino !== null ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setDestino(null)}>
              Voltar
            </Button>
            <Button
              inline
              loading={entrando}
              disabled={!slug || !email.trim() || !senha}
              onClick={() => void entrar()}
            >
              Entrar
            </Button>
          </div>
        ) : undefined
      }
    >
      {erro && (
        <div className="mb-4">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {destino === null ? (
        <div className="flex flex-col gap-2">
          {conhecidas.map((empresa) => (
            <button
              key={empresa.slug}
              type="button"
              onClick={() => setDestino(empresa.slug)}
              className="flex min-h-touch items-center justify-between gap-3 rounded-dk
                         px-4 py-3 text-left ring-1 ring-line transition-colors
                         duration-150 ease-dk hover:bg-sunken"
            >
              <span className="min-w-0">
                <span className="block truncate text-base font-medium text-ink">
                  {empresa.name}
                </span>
                <span className="block truncate text-sm text-ink-faint">{empresa.slug}</span>
              </span>
              <span aria-hidden="true" className="text-ink-faint">
                →
              </span>
            </button>
          ))}

          {conhecidas.length === 0 && (
            <p className="text-base leading-relaxed text-ink-muted">
              Nenhuma outra empresa entrou neste aparelho ainda. Informe o código da
              empresa abaixo para entrar nela.
            </p>
          )}

          <button
            type="button"
            onClick={() => {
              setDestino("");
              setOutroSlug("");
            }}
            className="min-h-touch rounded-dk px-4 py-3 text-left text-base text-ink-muted
                       ring-1 ring-dashed ring-line transition-colors duration-150 ease-dk
                       hover:bg-sunken hover:text-ink"
          >
            Outra empresa…
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {destino === "" && (
            <TextField
              label="Código da empresa"
              value={outroSlug}
              autoCapitalize="none"
              onChange={(evento) => setOutroSlug(evento.target.value)}
              hint="O mesmo código que se usa para entrar nela."
            />
          )}

          <TextField
            label="E-mail"
            type="email"
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
            hint="A conta daquela empresa pode usar outro endereço."
          />

          <TextField
            label="Senha"
            type="password"
            revealable
            value={senha}
            onChange={(evento) => setSenha(evento.target.value)}
            hint="Pedida porque a conta de cada empresa é separada, com senha própria."
          />
        </div>
      )}
    </Modal>
  );
}
