import { SemRedeError } from "./api";
import { clientes, type Cliente, type ClienteIn } from "./clientes";
import { enfileirar, pendentes, type Pendente } from "./fila";
import { gravar, gravarVarios, lerTodos, LocalIndisponivelError } from "./local";

/* A carteira de clientes, com ou sem rede.
 *
 * É a fatia 2 da docs/adr/0022-offline-first-as-respostas.md. O que esta camada faz é o
 * que a ADR 0019 chama de "a escrita nasce no aparelho": a tela não espera a rede para
 * confirmar o que a pessoa fez.
 *
 * A regra aqui é uma só, e vale para tudo: **tenta a rede primeiro**. Sem rede não é o
 * caso comum, nem no campo — é o caso que não pode quebrar. Gravar sempre localmente e
 * sincronizar depois atrasaria todo mundo para servir a minoria dos momentos.
 */

/** O que a tela recebe: a lista, o que ainda não subiu, e se veio de cache. */
export interface Visao {
  clientes: Cliente[];
  /** Ids com alteração esperando o servidor. */
  pendentes: Set<string>;
  /** Ids que o servidor **recusou**, com o motivo. */
  recusados: Map<string, string>;
  /** A lista veio do aparelho, e não do servidor: pode estar atrasada. */
  doCache: boolean;
}

function comoCliente(corpo: ClienteIn, id: string): Cliente {
  return {
    id,
    tipo: corpo.tipo,
    nome: corpo.nome,
    apelido: corpo.apelido ?? null,
    tenant_assinante_id: corpo.tenant_assinante_id ?? null,
    cpf_cnpj: corpo.cpf_cnpj ?? null,
    inscricao_estadual: corpo.inscricao_estadual ?? null,
    email: corpo.email ?? null,
    telefone: corpo.telefone ?? null,
    cep: corpo.cep ?? null,
    logradouro: corpo.logradouro ?? null,
    numero: corpo.numero ?? null,
    complemento: corpo.complemento ?? null,
    bairro: corpo.bairro ?? null,
    cidade: corpo.cidade ?? null,
    uf: corpo.uf ?? null,
    observacao: corpo.observacao ?? null,
    ativo: true,
  };
}

/** Põe por cima da lista do servidor o que ainda está na fila.
 *
 * Sem isto, o cadastro feito sem rede sumiria da tela assim que ela recarregasse — a
 * pessoa digitaria tudo de novo, e teríamos dois cadastros quando a fila subisse. */
function sobrepor(base: Cliente[], fila: Pendente[]): Cliente[] {
  const porId = new Map(base.map((cliente) => [cliente.id, cliente]));

  for (const item of fila) {
    const corpo = item.corpo as ClienteIn;
    const existente = porId.get(item.id);
    porId.set(item.id, existente ? { ...existente, ...comoCliente(corpo, item.id) } : comoCliente(corpo, item.id));
  }

  return [...porId.values()].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
}

function filtrar(lista: Cliente[], busca: string | undefined, incluirInativos: boolean): Cliente[] {
  const termo = busca?.trim().toLowerCase();
  return lista.filter((cliente) => {
    if (!incluirInativos && !cliente.ativo) return false;
    if (!termo) return true;
    const campos = [cliente.nome, cliente.apelido ?? "", cliente.cpf_cnpj ?? ""];
    return campos.some((campo) => campo.toLowerCase().includes(termo));
  });
}

/* Armazenamento local pode simplesmente não existir: janela anônima, site bloqueado,
 * cota estourada. Quem está com rede não pode perder a tela por causa disso — sem o
 * aparelho, o Decko volta a ser o que era antes desta fatia, e isso funciona. */
async function semQuebrar<T>(trabalho: Promise<T>, vazio: T): Promise<T> {
  try {
    return await trabalho;
  } catch (causa) {
    if (causa instanceof LocalIndisponivelError) return vazio;
    throw causa;
  }
}

async function marcasDaFila(empresa: string) {
  const fila = await semQuebrar(pendentes(empresa), [] as Pendente[]);
  return {
    fila,
    marcas: new Set(fila.filter((item) => !item.erro).map((item) => item.id)),
    recusados: new Map(
      fila.filter((item) => item.erro).map((item) => [item.id, item.erro as string]),
    ),
  };
}

export async function listar(
  empresa: string,
  busca?: string,
  incluirInativos = false,
): Promise<Visao> {
  const { fila, marcas, recusados } = await marcasDaFila(empresa);

  try {
    const doServidor = await clientes.listar(busca, incluirInativos);
    // Guarda para a próxima abertura sem rede. A busca filtra o que vem, então só a
    // lista inteira alimenta o cache — lista parcial viraria cache parcial.
    if (!busca?.trim() && incluirInativos) {
      await semQuebrar(gravarVarios(empresa, "clientes", doServidor), undefined);
    }
    return { clientes: sobrepor(doServidor, fila), pendentes: marcas, recusados, doCache: false };
  } catch (causa) {
    if (!(causa instanceof SemRedeError)) throw causa;

    const guardados = await semQuebrar(lerTodos<Cliente>(empresa, "clientes"), [] as Cliente[]);
    return {
      clientes: filtrar(sobrepor(guardados, fila), busca, incluirInativos),
      pendentes: marcas,
      recusados,
      doCache: true,
    };
  }
}

/** Mantém o cache em dia com o que o servidor acabou de confirmar. */
async function guardar(empresa: string, cliente: Cliente): Promise<void> {
  await semQuebrar(gravar(empresa, "clientes", cliente), undefined);
}

export interface Salvo {
  cliente: Cliente;
  /** Ficou na fila em vez de ir ao servidor. */
  pendente: boolean;
}

export async function salvar(
  empresa: string,
  corpo: ClienteIn,
  editando?: Cliente,
): Promise<Salvo> {
  // A identidade nasce aqui quando o cadastro é novo. É o que torna o reenvio idempotente
  // do outro lado — ADR 0019, decisão 2, implementada na fatia 1.
  const id = editando?.id ?? corpo.id ?? crypto.randomUUID();
  const comIdentidade: ClienteIn = { ...corpo, id };

  try {
    const cliente = editando
      ? await clientes.atualizar(id, comIdentidade)
      : await clientes.criar(comIdentidade);
    await guardar(empresa, cliente);
    return { cliente, pendente: false };
  } catch (causa) {
    if (!(causa instanceof SemRedeError)) throw causa;

    await enfileirar(empresa, {
      id,
      acao: editando ? "cliente.atualizar" : "cliente.criar",
      corpo: comIdentidade,
    });
    // O que a tela mostra enquanto espera. Para edição, parte do que já existia: o corpo
    // do formulário é completo, mas `ativo` e o que vier a mais vivem no registro antigo.
    const otimista = editando
      ? { ...editando, ...comoCliente(comIdentidade, id) }
      : comoCliente(comIdentidade, id);
    return { cliente: otimista, pendente: true };
  }
}

/** Manda ao servidor um cadastro que estava na fila.
 *
 * Quem chama é `sincronia.enviarPendentes`, que esvazia a fila inteira: ela guarda
 * cadastro de cliente e venda de balcão juntos, na ordem em que aconteceram.
 */
export async function enviarCliente(empresa: string, item: Pendente): Promise<void> {
  const corpo = item.corpo as ClienteIn;
  // O corpo guardado na fila já é o cadastro inteiro: o `PUT` substitui, e mandar
  // parcial apagaria o resto. Por isso a fila guarda corpo, e não diferença.
  const cliente =
    item.acao === "cliente.criar"
      ? await clientes.criar(corpo)
      : await clientes.atualizar(item.id, corpo);
  await guardar(empresa, cliente);
}
