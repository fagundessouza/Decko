import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Modal } from "../components/Modal";
import { LarguraDoPapel, Recibo } from "../components/Recibo";
import { TextField } from "../components/TextField";
import { clientes } from "../lib/clientes";
import type { Cliente } from "../lib/clientes";
import { comercial } from "../lib/comercial";
import type { Produto } from "../lib/comercial";
import { brl, num } from "../lib/format";
import { FORMAS, pdv } from "../lib/pdv";
import type { FormaPagamento, Venda } from "../lib/pdv";

interface Props {
  onBack: () => void;
  /** Nome da empresa, para o cabeçalho do recibo. Vem da sessão, então existe sempre. */
  empresa: string;
  /** Só quando a empresa tem o módulo de clientes e quem opera pode identificar.
   *
   *  O PDV passou a depender de `clientes`, mas empresa que já tinha o PDV sem ele não
   *  recebe o módulo sozinha — instalar na empresa dos outros sem pedido é o que a ADR
   *  0010 recusa para a semente. Então a tela simplesmente não oferece. */
  podeIdentificar: boolean;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* A tela do balcão.
 *
 * Tudo o que é dinheiro vem calculado do servidor: total, falta e troco chegam prontos a
 * cada resposta — ver docs/adr/0008-ponto-de-venda.md, decisão 3. A tela só desenha.
 *
 * O campo de código fica com o foco o tempo inteiro, porque o leitor de código de barras
 * digita e dá Enter. Perder o foco depois de cada item faria o operador pegar no mouse a
 * cada produto, que é o que torna um PDV lento. */
export function PdvPage({ onBack, empresa, podeIdentificar }: Props) {
  const [venda, setVenda] = useState<Venda | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [codigo, setCodigo] = useState("");
  const [quantidade, setQuantidade] = useState("1");
  const [achados, setAchados] = useState<Produto[] | null>(null);

  const [cobrando, setCobrando] = useState<FormaPagamento | null>(null);
  const [valorRecebido, setValorRecebido] = useState("");
  const [concluida, setConcluida] = useState<Venda | null>(null);

  const [identificando, setIdentificando] = useState(false);
  const [buscaCliente, setBuscaCliente] = useState("");
  const [achadosCliente, setAchadosCliente] = useState<Cliente[] | null>(null);

  const campoCodigo = useRef<HTMLInputElement>(null);

  const focarCodigo = useCallback(() => {
    // Depois do render, senão o foco corre antes de o campo voltar a existir.
    requestAnimationFrame(() => campoCodigo.current?.focus());
  }, []);

  /* Retoma a venda aberta em vez de começar outra: recarregar a página não pode perder o
   * que já foi bipado. */
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const abertas = await pdv.listVendas("aberta");
        if (!vivo) return;
        const atual = abertas[0] ? await pdv.ver(abertas[0].id) : await pdv.abrir();
        if (!vivo) return;
        setVenda(atual);
      } catch (cause) {
        if (vivo) setErro(motivo(cause, "Não foi possível abrir o caixa."));
      } finally {
        if (vivo) {
          setCarregando(false);
          focarCodigo();
        }
      }
    })();
    return () => {
      vivo = false;
    };
  }, [focarCodigo]);

  async function lancar(produto: Produto) {
    if (!venda) return;
    setBusy(true);
    setErro(null);
    try {
      const atual = await pdv.adicionarItem(venda.id, {
        produto_id: produto.id,
        quantidade: quantidade.replace(",", ".") || "1",
      });
      setVenda(atual);
      setCodigo("");
      setQuantidade("1");
      setAchados(null);
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível lançar o item."));
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  async function procurar() {
    const termo = codigo.trim();
    if (termo === "" || !venda) return;

    setBusy(true);
    setErro(null);
    try {
      const produtos = (await comercial.listProdutos(termo)).filter((item) => item.ativo);
      if (produtos.length === 0) {
        setErro(`Nenhum produto para “${termo}”.`);
        setAchados(null);
      } else if (produtos.length === 1) {
        // Caso do leitor de código de barras: achou um, lança e segue.
        await lancar(produtos[0]);
      } else {
        setAchados(produtos);
      }
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível procurar o produto."));
    } finally {
      setBusy(false);
    }
  }

  async function procurarCliente() {
    setErro(null);
    try {
      setAchadosCliente(await clientes.listar(buscaCliente));
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível procurar o cliente."));
    }
  }

  async function escolherCliente(cliente: Cliente) {
    setIdentificando(false);
    setBuscaCliente("");
    setAchadosCliente(null);
    if (!venda) return;
    await operar(
      () => pdv.identificar(venda.id, cliente.id),
      "Não foi possível identificar a venda.",
    );
  }

  async function operar(acao: () => Promise<Venda>, padrao: string) {
    setBusy(true);
    setErro(null);
    try {
      setVenda(await acao());
    } catch (cause) {
      setErro(motivo(cause, padrao));
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  async function cobrar() {
    if (!venda || cobrando === null) return;
    const valor = valorRecebido.replace(",", ".");
    setCobrando(null);
    setValorRecebido("");
    await operar(
      () => pdv.pagar(venda.id, { forma: cobrando, valor }),
      "Não foi possível registrar o pagamento.",
    );
  }

  async function finalizar() {
    if (!venda) return;
    setBusy(true);
    setErro(null);
    try {
      const fechada = await pdv.finalizar(venda.id);
      setConcluida(fechada);
      setVenda(null);
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível fechar a venda."));
    } finally {
      setBusy(false);
    }
  }

  async function novaVenda() {
    setConcluida(null);
    setBusy(true);
    setErro(null);
    try {
      setVenda(await pdv.abrir());
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível abrir outra venda."));
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  if (carregando) {
    return (
      <Page wide>
        <p className="animate-fade text-base text-ink-muted">Abrindo o caixa…</p>
      </Page>
    );
  }

  if (concluida) {
    return (
      <Page>
        <PageHeader title="Venda concluída" onBack={onBack} />
        <Card>
          <CardBody className="text-center">
            <p className="text-sm uppercase tracking-wide text-ink-faint">Venda</p>
            <p className="mt-1 text-5xl font-bold tabular-nums tracking-tight text-ink">
              {concluida.numero}
            </p>

            <dl className="mt-8 flex flex-col gap-3 text-left">
              <Linha rotulo="Total" valor={brl(concluida.total)} />
              <Linha rotulo="Recebido" valor={brl(concluida.pago)} />
              {Number(concluida.troco) > 0 && (
                <Linha rotulo="Troco" valor={brl(concluida.troco)} destaque />
              )}
            </dl>

            <div className="mt-8 flex flex-col gap-3">
              <Button onClick={() => void novaVenda()} loading={busy}>
                Nova venda
              </Button>
              {/* O recibo é opcional: muito balcão não imprime nada, e obrigar a passar
                  por um diálogo de impressão a cada venda atrasaria a fila. */}
              <Button variant="secondary" onClick={() => window.print()}>
                Imprimir recibo
              </Button>
              <div className="flex justify-center">
                <LarguraDoPapel onChange={() => undefined} />
              </div>
            </div>
          </CardBody>
        </Card>

        <Recibo venda={concluida} empresa={empresa} />
      </Page>
    );
  }

  if (!venda) {
    return (
      <Page>
        <PageHeader title="Ponto de venda" onBack={onBack} />
        {erro && <Alert tone="danger">{erro}</Alert>}
        <div className="mt-6">
          <Button onClick={() => void novaVenda()} loading={busy}>
            Abrir venda
          </Button>
        </div>
      </Page>
    );
  }

  const falta = Number(venda.falta);
  const temItem = venda.itens.length > 0;

  return (
    <Page wide>
      <PageHeader
        title="Ponto de venda"
        description="Bipe o código de barras ou digite o código do produto e dê Enter."
        onBack={onBack}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardBody>
              <form
                className="flex flex-col gap-4 sm:flex-row sm:items-end"
                onSubmit={(event) => {
                  event.preventDefault();
                  void procurar();
                }}
              >
                <div className="flex-1">
                  <TextField
                    ref={campoCodigo}
                    label="Código, código de barras ou nome"
                    leading="⌕"
                    autoFocus
                    autoComplete="off"
                    value={codigo}
                    onChange={(event) => setCodigo(event.target.value)}
                    /* O Enter é tratado aqui, e não só pelo submit do formulário: o
                     * leitor de código de barras termina a leitura com Enter, e deixar
                     * isso por conta do envio implícito do formulário é frágil demais
                     * para o que mais se repete no caixa. */
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void procurar();
                      }
                    }}
                    placeholder="Bipe ou digite"
                  />
                </div>
                <div className="w-full sm:w-28">
                  <TextField
                    label="Qtd."
                    inputMode="decimal"
                    value={quantidade}
                    onChange={(event) => setQuantidade(event.target.value)}
                  />
                </div>
                <Button type="submit" inline loading={busy}>
                  Lançar
                </Button>
              </form>
            </CardBody>
          </Card>

          {podeIdentificar && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-base">
              {venda.cliente_nome ? (
                <>
                  <span className="text-ink-muted">Cliente:</span>
                  <span className="font-medium text-ink">{venda.cliente_nome}</span>
                  <Button variant="ghost" inline disabled={busy} onClick={() => setIdentificando(true)}>
                    Trocar
                  </Button>
                  <Button
                    variant="ghost"
                    inline
                    disabled={busy}
                    onClick={() =>
                      void operar(
                        () => pdv.desidentificar(venda.id),
                        "Não foi possível tirar o cliente da venda.",
                      )
                    }
                  >
                    Tirar
                  </Button>
                </>
              ) : (
                <>
                  {/* Venda anônima é o caso normal, e a frase diz isso em vez de parecer
                      um campo por preencher. */}
                  <span className="text-ink-muted">Venda anônima.</span>
                  <Button variant="ghost" inline disabled={busy} onClick={() => setIdentificando(true)}>
                    Identificar cliente
                  </Button>
                </>
              )}
            </div>
          )}

          <Card>
            <CardHeader
              title="Itens"
              description={temItem ? undefined : "Nada lançado ainda nesta venda."}
            />
            {temItem && (
              <ul className="mt-2">
                {venda.itens.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center gap-4 border-b border-line-subtle px-5 py-3 last:border-0 sm:px-6"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-base font-medium text-ink">
                        {item.descricao}
                      </p>
                      <p className="text-sm tabular-nums text-ink-muted">
                        {num(item.quantidade, 3)} × {brl(item.preco_unitario)}
                      </p>
                    </div>
                    <p className="shrink-0 text-base font-semibold tabular-nums text-ink">
                      {brl(item.total)}
                    </p>
                    <button
                      type="button"
                      aria-label={`Retirar ${item.descricao}`}
                      disabled={busy}
                      onClick={() =>
                        void operar(
                          () => pdv.removerItem(venda.id, item.id),
                          "Não foi possível retirar o item.",
                        )
                      }
                      className="shrink-0 rounded-dk px-2 py-1 text-lg leading-none text-ink-faint
                                 transition-colors duration-150 ease-dk hover:bg-danger-soft hover:text-danger
                                 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardBody>
              <dl className="flex flex-col gap-2.5">
                <Linha rotulo="Subtotal" valor={brl(venda.soma_dos_itens)} />
                {Number(venda.desconto) > 0 && (
                  <Linha rotulo="Desconto" valor={`− ${brl(venda.desconto)}`} />
                )}
              </dl>

              <div className="mt-5 border-t border-line-subtle pt-5">
                <p className="text-sm uppercase tracking-wide text-ink-faint">A pagar</p>
                <p className="mt-1 text-4xl font-bold tabular-nums tracking-tight text-ink">
                  {brl(venda.total)}
                </p>
              </div>

              {venda.pagamentos.length > 0 && (
                <ul className="mt-5 flex flex-col gap-2 border-t border-line-subtle pt-5">
                  {venda.pagamentos.map((pagamento) => (
                    <li
                      key={pagamento.id}
                      className="flex items-center justify-between gap-3 text-sm"
                    >
                      <span className="capitalize text-ink-muted">{pagamento.forma}</span>
                      <span className="flex items-center gap-2">
                        <span className="tabular-nums text-ink">{brl(pagamento.valor)}</span>
                        <button
                          type="button"
                          aria-label="Retirar pagamento"
                          disabled={busy}
                          onClick={() =>
                            void operar(
                              () => pdv.removerPagamento(venda.id, pagamento.id),
                              "Não foi possível retirar o pagamento.",
                            )
                          }
                          className="rounded-dk px-1.5 leading-none text-ink-faint
                                     transition-colors duration-150 ease-dk hover:text-danger
                                     disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          ×
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              <div className="mt-5 border-t border-line-subtle pt-5">
                {falta > 0 ? (
                  <Linha rotulo="Falta" valor={brl(venda.falta)} destaque />
                ) : (
                  <Linha rotulo="Troco" valor={brl(venda.troco)} destaque />
                )}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Receber" />
            <CardBody className="pt-4">
              <div className="grid grid-cols-2 gap-3">
                {FORMAS.map((forma) => (
                  <Button
                    key={forma.valor}
                    variant="secondary"
                    disabled={!temItem || busy}
                    onClick={() => {
                      setCobrando(forma.valor);
                      // O caso comum é receber exatamente o que falta.
                      setValorRecebido(venda.falta);
                    }}
                  >
                    {forma.label}
                  </Button>
                ))}
              </div>

              <div className="mt-5 flex flex-col gap-3">
                <Button
                  disabled={!temItem || falta > 0}
                  loading={busy}
                  onClick={() => void finalizar()}
                >
                  Fechar venda
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    void operar(() => pdv.cancelar(venda.id), "Não foi possível cancelar.").then(
                      () => setVenda(null),
                    )
                  }
                >
                  Cancelar venda
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>

      <Modal
        open={identificando}
        title="Identificar a venda"
        description="Procure por nome, apelido ou documento."
        onClose={() => {
          setIdentificando(false);
          setBuscaCliente("");
          setAchadosCliente(null);
          focarCodigo();
        }}
      >
        <form
          className="flex gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void procurarCliente();
          }}
        >
          <div className="flex-1">
            <TextField
              label="Cliente"
              leading="⌕"
              autoFocus
              autoComplete="off"
              value={buscaCliente}
              onChange={(event) => setBuscaCliente(event.target.value)}
              placeholder="Nome, apelido ou CPF"
            />
          </div>
          <div className="self-end">
            <Button type="submit" inline>
              Procurar
            </Button>
          </div>
        </form>

        {achadosCliente !== null && achadosCliente.length === 0 && (
          <p className="mt-4 text-base text-ink-muted">
            Nenhum cliente encontrado. Cadastre em Clientes e volte aqui.
          </p>
        )}

        {achadosCliente !== null && achadosCliente.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2">
            {achadosCliente.map((cliente) => (
              <li key={cliente.id}>
                <button
                  type="button"
                  onClick={() => void escolherCliente(cliente)}
                  className="flex min-h-touch w-full items-center justify-between gap-3
                             rounded-dk px-4 py-3 text-left ring-1 ring-line
                             transition-colors duration-150 ease-dk hover:bg-sunken"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-base font-medium text-ink">
                      {cliente.nome}
                    </span>
                    {(cliente.apelido || cliente.cpf_cnpj) && (
                      <span className="block truncate text-sm text-ink-faint">
                        {[cliente.apelido, cliente.cpf_cnpj].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </span>
                  <span aria-hidden="true" className="text-ink-faint">
                    →
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Modal>

      <Modal
        open={achados !== null}
        title="Qual produto?"
        description="Mais de um produto bate com o que foi digitado."
        onClose={() => {
          setAchados(null);
          focarCodigo();
        }}
      >
        <ul className="flex flex-col gap-2">
          {(achados ?? []).map((produto) => (
            <li key={produto.id}>
              <button
                type="button"
                onClick={() => void lancar(produto)}
                className="flex w-full items-center justify-between gap-4 rounded-dk px-4 py-3 text-left
                           ring-1 ring-line-subtle transition-colors duration-150 ease-dk hover:bg-sunken"
              >
                <span className="min-w-0">
                  <span className="block truncate text-base text-ink">{produto.nome}</span>
                  <span className="block text-sm tabular-nums text-ink-faint">
                    {produto.codigo}
                  </span>
                </span>
                <span className="shrink-0 text-base font-semibold tabular-nums text-ink">
                  {produto.preco_venda ? brl(produto.preco_venda) : "sem preço"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Modal>

      <Modal
        open={cobrando !== null}
        title={`Receber em ${FORMAS.find((f) => f.valor === cobrando)?.label ?? ""}`}
        onClose={() => setCobrando(null)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setCobrando(null)}>
              Cancelar
            </Button>
            <Button inline onClick={() => void cobrar()}>
              Receber
            </Button>
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void cobrar();
          }}
        >
          <TextField
            label="Valor recebido"
            leading="R$"
            inputMode="decimal"
            value={valorRecebido}
            onChange={(event) => setValorRecebido(event.target.value)}
          />
          <p className="mt-3 text-sm text-ink-muted">
            Falta {brl(venda.falta)}. Troco só sai de pagamento em dinheiro.
          </p>
        </form>
      </Modal>

      <p className="mt-8 flex items-center gap-2 text-sm text-ink-faint">
        <Badge>Sem emissão fiscal</Badge>
        Esta venda registra a saída no estoque. A emissão de cupom fiscal entra com o
        módulo fiscal.
      </p>
    </Page>
  );
}

function Linha({
  rotulo,
  valor,
  destaque = false,
}: {
  rotulo: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className={destaque ? "text-base text-ink" : "text-sm text-ink-muted"}>{rotulo}</dt>
      <dd
        className={
          "tabular-nums " +
          (destaque ? "text-xl font-semibold text-ink" : "text-base text-ink")
        }
      >
        {valor}
      </dd>
    </div>
  );
}
