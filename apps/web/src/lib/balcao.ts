import type { Cliente } from "./clientes";
import type { Produto } from "./comercial";
import {
  CASAS_PRECO,
  CASAS_QUANTIDADE,
  dinheiro,
  emReais,
  escalar,
  escrever,
  somar,
  totalDaLinha,
} from "./dinheiro";
import { enfileirar, pendentes, type Pendente } from "./fila";
import { apagar, gravar, ler, lerTodos, LocalIndisponivelError } from "./local";
import type {
  ConfiguracaoPdv,
  FormaPagamento,
  ItemVenda,
  PagamentoVenda,
  Venda,
} from "./pdv";
import { pdv } from "./pdv";

/* A venda composta no aparelho, sem rede.
 *
 * Fatia 4 da `docs/adr/0022-offline-first-as-respostas.md`, a metade do aparelho — a do
 * servidor é `POST /pdv/vendas/do-aparelho`. O dono do projeto foi explícito sobre o que
 * se espera daqui, em 17/11/2026:
 *
 *   "O lance do offline-first não é só abrir, é continuar fazendo a operação: entrar,
 *    cadastrando clientes, operando PDV. Tem que manter a operação, não pode morrer ou
 *    travar ou parar."
 *
 * O que este módulo produz é uma `Venda` com a **mesma forma** da que vem do servidor.
 * Isso é de propósito: a tela do balcão desenha a venda local sem saber que é local, e
 * não existe uma segunda tela de caixa para manter igual à primeira.
 *
 * A diferença que importa é de tempo verbal. A venda do servidor está sendo feita e pode
 * ser recusada; a venda daqui **foi feita** — o cliente levou a mercadoria e foi embora.
 * Por isso ela sobe inteira, num pacote só, e o servidor registra o que aconteceu.
 */

export class BalcaoError extends Error {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = "BalcaoError";
  }
}

export const ACAO_VENDA = "venda.sincronizar" as const;

/** O pacote que sobe. Mesma forma do `VendaDoAparelhoIn` do servidor. */
export interface VendaDoAparelho {
  id: string;
  registrada_no_aparelho_em: string;
  itens: {
    id: string;
    produto_id: string;
    unidade_id: string;
    lote_id: string | null;
    quantidade: string;
    preco_unitario: string;
    desconto: string;
    descricao: string;
  }[];
  pagamentos: {
    id: string;
    forma: FormaPagamento;
    valor: string;
    conta_id: string | null;
  }[];
  desconto: string;
  cliente_id: string | null;
}

/** O que o servidor achou de errado depois de registrar — e registrou mesmo assim. */
export interface Divergencia {
  produto_id: string;
  descricao: string;
  vendido: string;
  saldo_depois: string;
}

/** Uma venda que subiu com divergência, guardada para alguém ver.
 *
 * O servidor também põe isso na trilha de auditoria, que é onde o dono da loja olha. Este
 * aviso é para quem está no balcão: ele vendeu o que não tinha, e precisa saber hoje.
 */
export interface Aviso {
  id: string;
  numero: number | null;
  quando: string;
  divergencias: Divergencia[];
}

function agora(): string {
  return new Date().toISOString();
}

/** Uma venda nova, nascida no aparelho.
 *
 * A identidade vem daqui (fatia 1 da ADR 0022), e é o que torna o reenvio inofensivo: o
 * servidor reconhece a segunda chegada do mesmo pacote.
 *
 * `numero` fica nulo, e continua nulo até sincronizar. Dois caixas sem rede não têm como
 * combinar um contador — o número é do servidor, e a ADR 0019 já dizia isso.
 */
export function vendaNova(): Venda {
  return {
    id: crypto.randomUUID(),
    numero: null,
    status: "aberta",
    aberta_em: agora(),
    fechada_em: null,
    observacao: null,
    cliente_id: null,
    cliente_nome: null,
    itens: [],
    pagamentos: [],
    soma_dos_itens: "0.00",
    desconto: "0.00",
    total: "0.00",
    pago: "0.00",
    falta: "0.00",
    troco: "0.00",
  };
}

/** Refaz as contas da venda inteira. Mesmas fórmulas do `_ver` do servidor. */
function recontar(venda: Venda): Venda {
  const soma = somar(venda.itens.map((item) => dinheiro(item.total)));
  const desconto = dinheiro(venda.desconto);
  const total = soma - desconto;
  const pago = somar(venda.pagamentos.map((pagamento) => dinheiro(pagamento.valor)));

  return {
    ...venda,
    soma_dos_itens: emReais(soma),
    total: emReais(total),
    pago: emReais(pago),
    falta: emReais(total > pago ? total - pago : 0n),
    troco: emReais(pago > total ? pago - total : 0n),
  };
}

/** Lança um item, com o preço do catálogo guardado no aparelho.
 *
 * As recusas são as mesmas do servidor, e de propósito: produto sem preço não vai a zero,
 * e produto que controla lote não é vendido sem lote. Deixar passar aqui só adiaria a
 * recusa para a sincronização — com a mercadoria já na sacola do cliente.
 */
export function lancar(venda: Venda, produto: Produto, quantidade: string): Venda {
  if (venda.status !== "aberta") throw new BalcaoError("Esta venda já foi fechada.");

  const q = escalar(quantidade || "1", CASAS_QUANTIDADE);
  if (q <= 0n) throw new BalcaoError("A quantidade precisa ser maior que zero.");

  if (produto.preco_venda === null) {
    throw new BalcaoError(`“${produto.nome}” não tem preço de venda cadastrado.`);
  }
  if (produto.controla_lote) {
    // Sem rede não há saldo por lote para escolher, e inventar um lote faria o estoque
    // mentir sobre validade — que é justamente para o que o controle de lote existe.
    throw new BalcaoError(
      `“${produto.nome}” controla lote, e sem rede não dá para escolher o lote.`,
    );
  }

  const preco = escalar(produto.preco_venda, CASAS_PRECO);
  const item: ItemVenda = {
    id: crypto.randomUUID(),
    produto_id: produto.id,
    lote_id: null,
    unidade_id: produto.unidade_id,
    descricao: produto.nome,
    quantidade: escrever(q, CASAS_QUANTIDADE),
    preco_unitario: escrever(preco, CASAS_PRECO),
    desconto: "0.00",
    total: emReais(totalDaLinha(q, preco, 0n)),
  };

  return recontar({ ...venda, itens: [...venda.itens, item] });
}

export function retirar(venda: Venda, itemId: string): Venda {
  const itens = venda.itens.filter((item) => item.id !== itemId);
  if (itens.length === venda.itens.length) {
    throw new BalcaoError("Item não encontrado nesta venda.");
  }
  // Desconto maior do que a venda que sobrou deixaria de fechar; volta a zero junto.
  const sobrou = somar(itens.map((item) => dinheiro(item.total)));
  const desconto = dinheiro(venda.desconto) > sobrou ? "0.00" : venda.desconto;
  return recontar({ ...venda, itens, desconto });
}

export function pagar(
  venda: Venda,
  pagamento: {
    forma: FormaPagamento;
    valor: string;
    conta_id?: string | null;
    conta_nome?: string | null;
  },
): Venda {
  if (venda.status !== "aberta") throw new BalcaoError("Esta venda já foi fechada.");

  const valor = dinheiro(pagamento.valor);
  if (valor <= 0n) throw new BalcaoError("O valor do pagamento precisa ser maior que zero.");

  const linha: PagamentoVenda = {
    id: crypto.randomUUID(),
    forma: pagamento.forma,
    valor: emReais(valor),
    conta_id: pagamento.conta_id ?? null,
    conta_nome: pagamento.conta_nome ?? null,
  };
  return recontar({ ...venda, pagamentos: [...venda.pagamentos, linha] });
}

export function retirarPagamento(venda: Venda, pagamentoId: string): Venda {
  const pagamentos = venda.pagamentos.filter((item) => item.id !== pagamentoId);
  if (pagamentos.length === venda.pagamentos.length) {
    throw new BalcaoError("Pagamento não encontrado nesta venda.");
  }
  return recontar({ ...venda, pagamentos });
}

export function definirDesconto(venda: Venda, valor: string): Venda {
  if (venda.status !== "aberta") throw new BalcaoError("Esta venda já foi fechada.");

  const desconto = dinheiro(valor || "0");
  if (desconto > somar(venda.itens.map((item) => dinheiro(item.total)))) {
    throw new BalcaoError("O desconto é maior que a venda.");
  }
  return recontar({ ...venda, desconto: emReais(desconto) });
}

export function identificar(venda: Venda, cliente: Cliente): Venda {
  return { ...venda, cliente_id: cliente.id, cliente_nome: cliente.nome };
}

export function desidentificar(venda: Venda): Venda {
  return { ...venda, cliente_id: null, cliente_nome: null };
}

/** Fecha a venda no aparelho. As conferências são as do `finalizar_venda` do servidor.
 *
 * Elas estão aqui porque uma venda que o servidor vai recusar depois é pior do que uma
 * recusa agora: agora o operador ainda tem o cliente na frente dele.
 */
export function fechar(venda: Venda): Venda {
  if (venda.status !== "aberta") throw new BalcaoError("Esta venda já foi fechada.");
  if (venda.itens.length === 0) throw new BalcaoError("Não dá para fechar uma venda sem itens.");

  const falta = dinheiro(venda.falta);
  if (falta > 0n) throw new BalcaoError(`Falta receber R$ ${emReais(falta)}.`);

  const troco = dinheiro(venda.troco);
  if (troco > 0n) {
    const emEspecie = somar(
      venda.pagamentos
        .filter((pagamento) => pagamento.forma === "dinheiro")
        .map((pagamento) => dinheiro(pagamento.valor)),
    );
    if (troco > emEspecie) {
      throw new BalcaoError("Só pagamento em dinheiro devolve troco; confira os valores.");
    }
  }

  return { ...venda, status: "finalizada", fechada_em: agora() };
}

export function corpoDaVenda(venda: Venda): VendaDoAparelho {
  return {
    id: venda.id,
    registrada_no_aparelho_em: venda.fechada_em ?? agora(),
    itens: venda.itens.map((item) => ({
      id: item.id,
      produto_id: item.produto_id,
      unidade_id: item.unidade_id,
      lote_id: item.lote_id,
      quantidade: item.quantidade,
      preco_unitario: item.preco_unitario,
      desconto: item.desconto,
      descricao: item.descricao,
    })),
    pagamentos: venda.pagamentos.map((pagamento) => ({
      id: pagamento.id,
      forma: pagamento.forma,
      valor: pagamento.valor,
      conta_id: pagamento.conta_id,
    })),
    desconto: venda.desconto,
    cliente_id: venda.cliente_id,
  };
}

async function semQuebrar<T>(trabalho: Promise<T>, vazio: T): Promise<T> {
  try {
    return await trabalho;
  } catch (causa) {
    if (causa instanceof LocalIndisponivelError) return vazio;
    throw causa;
  }
}

/** Põe a venda fechada na fila. A chave é o id da venda, então reenfileirar não duplica. */
export async function enfileirarVenda(empresa: string, venda: Venda): Promise<void> {
  await enfileirar(empresa, { id: venda.id, acao: ACAO_VENDA, corpo: corpoDaVenda(venda) });
}

/** Manda uma venda da fila ao servidor, e guarda a divergência que voltar.
 *
 * Erro de rede sobe sem tocar em nada: a fila sabe parar e tentar depois. Recusa do
 * servidor também sobe — a fila guarda o motivo, e a tela do caixa mostra.
 */
export async function enviar(empresa: string, item: Pendente): Promise<void> {
  const resposta = await pdv.sincronizarVenda(item.corpo as VendaDoAparelho);
  if (resposta.divergencias.length === 0) return;

  await semQuebrar(
    gravar<Aviso>(empresa, "avisos", {
      id: resposta.venda.id,
      numero: resposta.venda.numero,
      quando: agora(),
      divergencias: resposta.divergencias,
    }),
    undefined,
  );
}

/** As vendas que ainda não subiram, da mais antiga para a mais nova. */
export async function vendasNaFila(empresa: string): Promise<Pendente[]> {
  const fila = await semQuebrar(pendentes(empresa), [] as Pendente[]);
  return fila.filter((item) => item.acao === ACAO_VENDA);
}

export async function avisos(empresa: string): Promise<Aviso[]> {
  return semQuebrar(lerTodos<Aviso>(empresa, "avisos"), [] as Aviso[]);
}

export async function esquecerAviso(empresa: string, id: string): Promise<void> {
  await semQuebrar(apagar(empresa, "avisos", id), undefined);
}

/* A configuração do caixa guardada no aparelho.
 *
 * Ela é lida do servidor a cada abertura do PDV. Sem rede, o que o aparelho guardou é a
 * única coisa que diz o que esta loja exige supervisor para fazer.
 */
const CHAVE_CONFIG = "pdv";

export async function guardarConfiguracao(
  empresa: string,
  config: ConfiguracaoPdv,
): Promise<void> {
  await semQuebrar(gravar(empresa, "configuracao", { id: CHAVE_CONFIG, ...config }), undefined);
}

export async function configuracaoGuardada(empresa: string): Promise<ConfiguracaoPdv | null> {
  return semQuebrar(ler<ConfiguracaoPdv>(empresa, "configuracao", CHAVE_CONFIG), null);
}

/** Dá para fazer esta ação sem rede, ou ela depende de liberação de supervisor?
 *
 * Sem rede não há a quem pedir liberação: a credencial do supervisor é conferida **no
 * servidor**, na mesma requisição que executa a ação — ADR 0020, decisão 4. Conferir no
 * aparelho seria teatro, e destravar a tela por conta própria seria passar por cima da
 * regra que a loja configurou.
 *
 * Então a resposta vem do que a loja declarou, lido da última sincronização. Sem
 * configuração guardada a resposta é "não": o aparelho nunca soube a regra desta loja, e
 * supor "pode" é inventar permissão.
 *
 * Isto é um remendo honesto, e está anotado como questão em aberto na ADR 0022: liberar
 * supervisor sem rede é decisão de negócio, e o dono do projeto ainda não a tomou.
 */
export function podeSemLiberacao(
  config: ConfiguracaoPdv | null,
  acao: "cancelar_item" | "cancelar_venda" | "desconto",
  valor?: string,
): boolean {
  if (config === null) return false;
  switch (acao) {
    case "cancelar_item":
      return !config.exige_cancelar_item;
    case "cancelar_venda":
      return !config.exige_cancelar_venda;
    case "desconto":
      return !config.exige_desconto || dinheiro(valor || "0") <= dinheiro(config.desconto_livre);
  }
}
