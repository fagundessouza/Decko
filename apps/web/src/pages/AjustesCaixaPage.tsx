import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Checkbox } from "../components/Checkbox";
import { TextField } from "../components/TextField";
import { brl } from "../lib/format";
import { pdv } from "../lib/pdv";
import type { ConfiguracaoPdv } from "../lib/pdv";

interface Props {
  /** Sem isto a tela é só leitura: mostra o que a loja exige e não deixa mexer. */
  podeEditar: boolean;
}

function motivoDoErro(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* O que esta loja exige supervisor para fazer, e a partir de quanto.
 *
 * As quatro primeiras nascem **ligadas**, porque foi o que o dono do projeto escolheu em
 * 10/11/2026. As duas que dependem de um número nascem **desligadas**: ligá-las exige
 * escolher o limite, e inventar esse limite seria inventar regra de negócio — a regra 6
 * do `CLAUDE.md`. Ver `docs/adr/0020-operador-supervisor-e-papeis.md`, decisão 4.
 *
 * Vive dentro do ponto de venda, como as demais operações: é configuração do caixa, e é
 * no caixa que se procura por ela.
 */
export function AjustesCaixaPage({ podeEditar }: Props) {
  const [config, setConfig] = useState<ConfiguracaoPdv | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);
  const [busy, setBusy] = useState(false);

  /* Os dois limites são texto à parte, e não o campo do objeto.
   *
   * O servidor fala "0.00" e quem digita fala "0,00" — manter o valor do servidor no
   * campo faria o que a pessoa escreve grudar no fim do que veio ("0.005,00"), e ainda
   * mostraria ponto onde o Brasil usa vírgula. Zero vira campo vazio, para a pessoa
   * digitar o número em vez de corrigir o meu. */
  const [descontoLivre, setDescontoLivre] = useState("");
  const [diferencaLivre, setDiferencaLivre] = useState("");

  function emReais(valor: string): string {
    return Number(valor) === 0 ? "" : String(valor).replace(".", ",");
  }

  useEffect(() => {
    pdv
      .configuracao()
      .then((atual) => {
        setConfig(atual);
        setDescontoLivre(emReais(atual.desconto_livre));
        setDiferencaLivre(emReais(atual.diferenca_livre));
      })
      .catch((cause) => setErro(motivoDoErro(cause, "Não foi possível ler os ajustes.")));
  }, []);

  function mexer<K extends keyof ConfiguracaoPdv>(campo: K, valor: ConfiguracaoPdv[K]) {
    setSalvo(false);
    setConfig((atual) => (atual === null ? atual : { ...atual, [campo]: valor }));
  }

  async function salvar() {
    if (!config) return;
    setBusy(true);
    setErro(null);
    try {
      // Vírgula para ponto, como no resto do sistema. Vazio é zero: a exigência ligada com
      // limite zero quer dizer "qualquer valor pede supervisor", e é o padrão honesto para
      // quem ligou e não escolheu número.
      const salva = await pdv.salvarConfiguracao({
        ...config,
        desconto_livre: descontoLivre.replace(",", ".") || "0",
        diferenca_livre: diferencaLivre.replace(",", ".") || "0",
      });
      setConfig(salva);
      setDescontoLivre(emReais(salva.desconto_livre));
      setDiferencaLivre(emReais(salva.diferenca_livre));
      setSalvo(true);
    } catch (cause) {
      setErro(motivoDoErro(cause, "Não foi possível salvar os ajustes."));
    } finally {
      setBusy(false);
    }
  }

  if (config === null) {
    return erro ? (
      <Alert tone="danger">{erro}</Alert>
    ) : (
      <p className="animate-fade text-base text-ink-muted">Carregando…</p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {erro && <Alert tone="danger">{erro}</Alert>}
      {salvo && <Alert tone="success">Ajustes salvos.</Alert>}

      <div className="flex flex-col gap-4">
        <Checkbox
          label="Pedir o PIN ao abrir o ponto de venda"
          hint="O caixa abre no nome de quem vai operar. Desligue numa loja de uma pessoa só."
          checked={config.exige_pin_no_pdv}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_pin_no_pdv", v)}
        />
      </div>

      <div className="flex flex-col gap-4 border-t border-line-subtle pt-6">
        <p className="text-sm text-ink-muted">
          Ligado, o operador só conclui a ação com a credencial de alguém que possa
          liberá-la — e as duas pessoas ficam registradas.
        </p>

        <Checkbox
          label="Cancelar item da venda"
          hint="Tirar um produto da venda em andamento."
          checked={config.exige_cancelar_item}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_cancelar_item", v)}
        />
        <Checkbox
          label="Cancelar a venda inteira"
          checked={config.exige_cancelar_venda}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_cancelar_venda", v)}
        />
        <Checkbox
          label="Sangria"
          hint="Retirada de dinheiro da gaveta. Suprimento não pede: entrar dinheiro não é o que se desvia."
          checked={config.exige_sangria}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_sangria", v)}
        />
        <Checkbox
          label="Devolução"
          hint="Dinheiro saindo da gaveta sem venda por trás."
          checked={config.exige_devolucao}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_devolucao", v)}
        />
      </div>

      <div className="flex flex-col gap-4 border-t border-line-subtle pt-6">
        <Checkbox
          label="Desconto acima de um limite"
          hint="Abaixo do limite o operador desconta sozinho."
          checked={config.exige_desconto}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_desconto", v)}
        />
        {config.exige_desconto && (
          <TextField
            label="Desconto livre até"
            leading="R$"
            inputMode="decimal"
            disabled={!podeEditar}
            value={descontoLivre}
            onChange={(event) => {
              setSalvo(false);
              setDescontoLivre(event.target.value);
            }}
            hint={`Vazio quer dizer que qualquer desconto pede supervisor. Valendo agora: ${brl(
              config.desconto_livre,
            )}.`}
          />
        )}
      </div>

      <div className="flex flex-col gap-4 border-t border-line-subtle pt-6">
        <Checkbox
          label="Fechamento com diferença acima de um limite"
          hint="Continua sem impedir fechar: exige uma segunda pessoa, que é outra coisa."
          checked={config.exige_diferenca}
          disabled={!podeEditar}
          onChange={(v) => mexer("exige_diferenca", v)}
        />
        {config.exige_diferenca && (
          <TextField
            label="Diferença livre até"
            leading="R$"
            inputMode="decimal"
            disabled={!podeEditar}
            value={diferencaLivre}
            onChange={(event) => {
              setSalvo(false);
              setDiferencaLivre(event.target.value);
            }}
            hint={`Para mais ou para menos. Vazio pede supervisor em qualquer diferença. Valendo agora: ${brl(
              config.diferenca_livre,
            )}.`}
          />
        )}
      </div>

      {podeEditar ? (
        <Button loading={busy} onClick={() => void salvar()}>
          Salvar ajustes
        </Button>
      ) : (
        <p className="text-sm text-ink-muted">
          Só quem administra a loja muda isto. Você está vendo o que está valendo.
        </p>
      )}
    </div>
  );
}
