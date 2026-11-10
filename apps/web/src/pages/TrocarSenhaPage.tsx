import { useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { Card, CardBody } from "../components/Card";
import { TextField } from "../components/TextField";
import { equipe } from "../lib/api";

interface Props {
  /** Chamado depois da troca, para a aplicação reler a sessão e seguir. */
  onTrocada: () => void;
}

function motivoDoErro(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* A troca obrigatória da senha inicial.
 *
 * Não é tela de conveniência: é o que torna a credencial **da pessoa**. Enquanto o dono
 * souber a senha do operador, "quem fez" é sempre contestável, e a trilha inteira do PDV
 * vira enfeite — ver `docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 6.
 *
 * Por isso ela substitui a aplicação em vez de aparecer dentro dela: enquanto a senha for
 * a que o dono escolheu, não há mais nada a fazer no sistema.
 */
export function TrocarSenhaPage({ onTrocada }: Props) {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const curta = nova.length > 0 && nova.length < 8;
  const diferentes = repetida.length > 0 && nova !== repetida;
  const pronto = atual.length > 0 && nova.length >= 8 && nova === repetida;

  async function trocar() {
    setBusy(true);
    setErro(null);
    try {
      await equipe.trocarSenha(atual, nova);
      onTrocada();
    } catch (cause) {
      setErro(motivoDoErro(cause, "Não foi possível trocar a senha."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page>
      <PageHeader
        title="Escolha a sua senha"
        description="Você entrou com a senha que a loja definiu. Agora escolha a sua — só você vai saber."
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <Card>
        <CardBody>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (pronto) void trocar();
            }}
          >
            <TextField
              label="Senha atual"
              type="password"
              revealable
              autoFocus
              value={atual}
              onChange={(event) => setAtual(event.target.value)}
              hint="A que você recebeu da loja."
            />
            <TextField
              label="Senha nova"
              type="password"
              revealable
              value={nova}
              onChange={(event) => setNova(event.target.value)}
              invalid={curta}
              hint={curta ? "Ao menos 8 caracteres." : "Ao menos 8 caracteres."}
            />
            <TextField
              label="Repita a senha nova"
              type="password"
              revealable
              value={repetida}
              onChange={(event) => setRepetida(event.target.value)}
              invalid={diferentes}
              hint={diferentes ? "As duas não estão iguais." : undefined}
            />
            <Button type="submit" loading={busy} disabled={!pronto}>
              Trocar a senha
            </Button>
          </form>
        </CardBody>
      </Card>
    </Page>
  );
}
