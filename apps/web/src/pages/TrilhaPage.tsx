import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { platform } from "../lib/profiles";
import type { AuditEntry } from "../lib/profiles";

const POR_PAGINA = 50;

/* O que cada ação quer dizer, em português.
 *
 * A tradução mora aqui e não no servidor: texto de tela no backend obrigaria a soltar
 * versão do servidor para corrigir uma palavra. Ação que esta versão não conhece aparece
 * com o nome técnico — é feio e é honesto, melhor que esconder a linha. */
const ACOES: Record<string, string> = {
  "tenant.bootstrap": "Empresa cadastrada",
  "auth.login": "Entrou no sistema",
  "auth.login.failed": "Tentativa de entrada recusada",
  "auth.logout": "Saiu do sistema",
  "auth.refresh.reused": "Token de sessão reapresentado",
  "module.activate": "Aplicativo instalado",
  "module.deactivate": "Aplicativo desinstalado",
  "module.seed": "Itens iniciais trazidos",
  "profile.activate": "Ramo contratado",
  "cliente.create": "Cliente cadastrado",
  "cliente.update": "Cliente alterado",
  "cliente.activate": "Cliente reativado",
  "cliente.deactivate": "Cliente desativado",
};

/* Por que a tentativa recusada foi recusada. Vocabulário interno do servidor. */
const MOTIVOS: Record<string, string> = {
  senha: "senha incorreta",
  usuario_desconhecido: "e-mail não cadastrado nesta empresa",
  usuario_inativo: "usuário desativado",
  token_reutilizado: "token de sessão já encerrado",
};

const GRUPOS = [
  { rotulo: "Tudo", prefixo: "" },
  { rotulo: "Entradas e saídas", prefixo: "auth." },
  { rotulo: "Aplicativos", prefixo: "module." },
  { rotulo: "Clientes", prefixo: "cliente." },
];

/** O que aconteceu, em uma frase, a partir do que a linha guarda. */
function detalhe(entrada: AuditEntry): string | null {
  const dados = entrada.data ?? {};

  const motivo = dados.motivo;
  if (typeof motivo === "string") {
    return MOTIVOS[motivo] ?? motivo;
  }

  const instalados = dados.instalados ?? dados.modulos;
  if (Array.isArray(instalados)) {
    return instalados.join(", ");
  }

  const criados = dados.criados;
  if (Array.isArray(criados)) {
    // Zero é resposta, não ausência de resposta: foi pedido e nada faltava.
    return criados.length === 0 ? "nada faltava" : `${criados.length} item(ns)`;
  }

  const campos = dados.campos_alterados;
  if (Array.isArray(campos)) {
    return `campos: ${campos.join(", ")}`;
  }

  const nome = dados.nome;
  if (typeof nome === "string") return nome;

  const slug = dados.slug;
  if (typeof slug === "string") return slug;

  /* Sem detalhe. Antes isto caía no `entity_id`, e entrar no sistema aparecia como
   * "Lucas · b015be81-3e64-…" — identificador interno que não diz nada a quem lê. A
   * ação e o autor já contam a linha inteira. */
  return null;
}

function quando(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface Props {
  onBack: () => void;
}

/* A trilha de auditoria desta empresa.
 *
 * Existe porque escrever a trilha sem poder consultá-la atende a LGPD pela metade: o
 * titular tem direito de saber o que foi feito com o dado dele, e isso exige alguém
 * conseguindo olhar sem abrir o banco. */
export function TrilhaPage({ onBack }: Props) {
  const [entradas, setEntradas] = useState<AuditEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [prefixo, setPrefixo] = useState("");
  const [pagina, setPagina] = useState(0);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let atual = true;
    platform
      .readAudit({ prefixo, limit: POR_PAGINA, offset: pagina * POR_PAGINA })
      .then((resposta) => {
        if (!atual) return;
        setEntradas(resposta.entries);
        setTotal(resposta.total);
      })
      .catch((causa) => {
        if (!atual) return;
        setEntradas([]);
        setErro(causa instanceof Error ? causa.message : String(causa));
      });
    return () => {
      atual = false;
    };
  }, [prefixo, pagina]);

  const primeira = pagina * POR_PAGINA + 1;
  const ultima = Math.min((pagina + 1) * POR_PAGINA, total);

  return (
    <Page wide>
      <button
        type="button"
        onClick={onBack}
        className="mb-4 text-sm text-ink-muted transition-colors duration-150 ease-dk
                   hover:text-ink"
      >
        ← Voltar
      </button>

      <PageHeader
        title="Trilha de auditoria"
        description={
          entradas === null
            ? "Carregando…"
            : total === 0
              ? "Nada registrado ainda com esse filtro."
              : `Mostrando ${primeira}–${ultima} de ${total}. A trilha só recebe inclusão: nada aqui é editado nem apagado.`
        }
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <div className="mb-6 flex flex-wrap gap-2">
        {GRUPOS.map((grupo) => (
          <Button
            key={grupo.prefixo}
            inline
            variant={grupo.prefixo === prefixo ? "primary" : "secondary"}
            onClick={() => {
              setPrefixo(grupo.prefixo);
              setPagina(0);
            }}
          >
            {grupo.rotulo}
          </Button>
        ))}
      </div>

      {entradas !== null && entradas.length === 0 && (
        <Card muted>
          <p className="px-6 py-10 text-center text-base text-ink-muted">
            Nada registrado ainda com esse filtro.
          </p>
        </Card>
      )}

      {entradas !== null && entradas.length > 0 && (
        <Card>
          <ul className="divide-y divide-line">
            {entradas.map((entrada) => (
              <li key={entrada.id} className="flex flex-col gap-1 px-5 py-4 sm:px-6">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-base font-medium text-ink">
                    {ACOES[entrada.action] ?? entrada.action}
                  </span>
                  {entrada.action.endsWith(".failed") ||
                  entrada.action.endsWith(".reused") ? (
                    <Badge tone="danger" icon="!">
                      Recusado
                    </Badge>
                  ) : null}
                  <span className="text-sm text-ink-faint">{quando(entrada.created_at)}</span>
                </div>

                <p className="text-sm text-ink-muted">
                  {/* Sem autor quando a tentativa não chegou a uma conta, ou quando o
                      usuário foi removido depois — a trilha sobrevive a quem a gerou. */}
                  <span className="font-medium">{entrada.author ?? "—"}</span>
                  {detalhe(entrada) && <> · {detalhe(entrada)}</>}
                  {entrada.ip_address && (
                    <span className="text-ink-faint"> · {entrada.ip_address}</span>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {total > POR_PAGINA && (
        <div className="mt-6 flex items-center justify-between gap-3">
          <Button
            inline
            variant="secondary"
            disabled={pagina === 0}
            onClick={() => setPagina((atual) => Math.max(atual - 1, 0))}
          >
            Mais recentes
          </Button>
          <Button
            inline
            variant="secondary"
            disabled={ultima >= total}
            onClick={() => setPagina((atual) => atual + 1)}
          >
            Mais antigas
          </Button>
        </div>
      )}
    </Page>
  );
}
