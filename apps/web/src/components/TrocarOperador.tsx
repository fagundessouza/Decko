import { useEffect, useRef, useState } from "react";

import { entrarPorPin, operadores } from "../lib/api";
import type { Operador, SessionInfo } from "../lib/api";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { Modal } from "./Modal";
import { Select } from "./Select";
import { TextField } from "./TextField";

interface Props {
  open: boolean;
  onClose: () => void;
  /** A sessão passa a ser de quem entrou. */
  onTrocado: (info: SessionInfo) => void;
  /** Trava de abertura do caixa: não dá para fechar sem dizer quem está operando.
   *  A saída é sair do PDV, e ela fica escrita no próprio diálogo. */
  travado?: boolean;
  /** Sair do ponto de venda. Só com `travado`, e é a única saída dali. */
  onSair?: () => void;
  /** Abre a definição do PIN para quem ainda não tem. */
  onDefinirPin?: () => void;
}

/* A troca de operador no balcão.
 *
 * **O crachá identifica; o PIN autentica.** O crachá é um código impresso, lido pelo
 * mesmo leitor de código de barras das vendas — que se apresenta como teclado, por isso
 * não exige periférico novo. Sozinho ele não entra: cartão perdido não pode ser a conta
 * de ninguém.
 *
 * Isto só funciona a partir de uma estação **já autenticada** nesta empresa, e é o que
 * sustenta um PIN de quatro dígitos: o login completo diz "este aparelho é da loja", e o
 * PIN diz apenas quem está nele agora. Ver `docs/adr/0020-operador-supervisor-e-papeis.md`,
 * decisão 1.
 */
export function TrocarOperador({
  open,
  onClose,
  onTrocado,
  travado = false,
  onSair,
  onDefinirPin,
}: Props) {
  const [quem, setQuem] = useState<Operador[]>([]);
  const [escolhido, setEscolhido] = useState("");
  const [cracha, setCracha] = useState("");
  const [pin, setPin] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const campoPin = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setErro(null);
    setPin("");
    setCracha("");
    operadores()
      .then((lista) => {
        setQuem(lista);
        setEscolhido((atual) => atual || lista[0]?.id || "");
      })
      .catch(() => setQuem([]));
  }, [open]);

  async function entrar() {
    setBusy(true);
    setErro(null);
    try {
      // O crachá tem precedência: se foi lido, é quem está ali — e não o nome que ficou
      // escolhido de uma troca anterior.
      const info = await entrarPorPin(
        cracha.trim() ? { cracha: cracha.trim(), pin } : { user_id: escolhido, pin },
      );
      onTrocado(info);
      onClose();
    } catch (cause) {
      setErro(cause instanceof Error && cause.message ? cause.message : "Não foi possível entrar.");
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  const pronto = pin !== "" && (cracha.trim() !== "" || escolhido !== "");

  return (
    <Modal
      open={open}
      bloqueado={travado}
      title={travado ? "Quem está no caixa?" : "Trocar de operador"}
      description={
        travado
          ? "O caixa abre no nome de quem vai operar, para o que acontecer aqui ter dono."
          : "Passe o crachá ou escolha o nome, e digite o PIN."
      }
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          {travado ? (
            <Button variant="secondary" inline onClick={onSair}>
              Sair do caixa
            </Button>
          ) : (
            <Button variant="secondary" inline onClick={onClose}>
              Cancelar
            </Button>
          )}
          <Button inline loading={busy} disabled={!pronto} onClick={() => void entrar()}>
            Entrar
          </Button>
        </div>
      }
    >
      {erro && (
        <div className="mb-4">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (pronto) void entrar();
        }}
      >
        <TextField
          label="Crachá"
          autoFocus
          value={cracha}
          onChange={(event) => setCracha(event.target.value)}
          onKeyDown={(event) => {
            // O leitor digita o código e dá Enter. Em vez de enviar com o PIN vazio, o
            // foco vai para ele: é a sequência que a mão faz no balcão.
            if (event.key === "Enter" && pin === "") {
              event.preventDefault();
              campoPin.current?.focus();
            }
          }}
          hint="Passe o cartão no leitor, ou deixe vazio e escolha o nome abaixo."
        />
        <Select
          label="Nome"
          value={escolhido}
          onChange={setEscolhido}
          options={quem.map((pessoa) => ({ value: pessoa.id, label: pessoa.nome }))}
          empty="Ninguém definiu PIN ainda nesta empresa."
        />
        <TextField
          label="PIN"
          type="password"
          inputMode="numeric"
          ref={campoPin}
          value={pin}
          onChange={(event) => setPin(event.target.value)}
          hint="Só números. Errar cinco vezes bloqueia por alguns minutos."
        />
        {onDefinirPin && (
          <button
            type="button"
            onClick={onDefinirPin}
            className="self-start text-sm font-medium text-brand-link hover:underline"
          >
            Ainda não tenho PIN
          </button>
        )}
      </form>
    </Modal>
  );
}
