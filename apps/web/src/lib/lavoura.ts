import { SemRedeError } from "./api";
import { agro, type AgroClient, type AgroProperty, type Plan } from "./agro";
import { enfileirar, pendentes, type Pendente } from "./fila";
import { gravarVarios, lerTodos, LocalIndisponivelError } from "./local";

/* A pulverização com ou sem rede.
 *
 * Fatia 6 da `docs/adr/0022-offline-first-as-respostas.md`, a terceira das três telas que
 * a resposta 5 daquela ADR põe no escopo — e a que o piloto usa de verdade onde não há
 * sinal. O planejamento operacional é preenchido **na lavoura**: é o talão de papel que o
 * Nathan usa em campo e depois passa para o Excel.
 *
 * A regra é a mesma da carteira de clientes: **tenta a rede primeiro**. Sem rede não é o
 * caso comum, nem no campo; é o caso que não pode quebrar.
 *
 * O que fica guardado no aparelho é o que o formulário precisa para ser preenchido —
 * contratantes, propriedades e os planejamentos recentes. É a resposta 3 da ADR 0022.
 */

export const ACAO_PLANO = "plano.criar" as const;

/** O corpo do planejamento, como o formulário monta. */
export interface PlanoNovo {
  id?: string;
  client_id: string;
  property_id: string;
  data_aplicacao: string | null;
  cultura: string | null;
  cultura_outras_texto: string | null;
  area_ha: number | null;
  param_velocidade_vento_max_kmh: number | null;
  param_temperatura_maxima_c: number | null;
  param_umidade_relativa_min_pct: number | null;
}

async function semQuebrar<T>(trabalho: Promise<T>, vazio: T): Promise<T> {
  try {
    return await trabalho;
  } catch (causa) {
    if (causa instanceof LocalIndisponivelError) return vazio;
    throw causa;
  }
}

/** O que o planejamento guardado mostra enquanto não tem número do servidor. */
function comoPlano(corpo: PlanoNovo, id: string): Plan {
  return {
    id,
    // Nulo até sincronizar: o número é do servidor, e é ele que vai no documento do
    // produtor. Inventar um aqui faria dois aparelhos emitirem o mesmo número.
    numero: null,
    status: "rascunho",
    client_id: corpo.client_id,
    property_id: corpo.property_id,
    prescription_id: null,
    data_aplicacao: corpo.data_aplicacao,
    cultura: corpo.cultura,
    area_ha: corpo.area_ha === null ? null : String(corpo.area_ha),
    param_temperatura_maxima_c:
      corpo.param_temperatura_maxima_c === null ? null : String(corpo.param_temperatura_maxima_c),
    param_umidade_relativa_min_pct:
      corpo.param_umidade_relativa_min_pct === null
        ? null
        : String(corpo.param_umidade_relativa_min_pct),
    param_velocidade_vento_max_kmh:
      corpo.param_velocidade_vento_max_kmh === null
        ? null
        : String(corpo.param_velocidade_vento_max_kmh),
  };
}

export interface VisaoDosPlanos {
  planos: Plan[];
  /** Ids de planejamento que ainda esperam o servidor. */
  pendentes: Set<string>;
  /** Ids que o servidor **recusou**, com o motivo. */
  recusados: Map<string, string>;
  /** A lista veio do aparelho: pode estar atrasada. */
  doCache: boolean;
}

async function marcasDaFila(empresa: string) {
  const fila = (await semQuebrar(pendentes(empresa), [] as Pendente[])).filter(
    (item) => item.acao === ACAO_PLANO,
  );
  return {
    fila,
    marcas: new Set(fila.filter((item) => !item.erro).map((item) => item.id)),
    recusados: new Map(
      fila.filter((item) => item.erro).map((item) => [item.id, item.erro as string]),
    ),
  };
}

/** Põe por cima da lista do servidor os planejamentos que ainda não subiram.
 *
 * Sem isto, o planejamento preenchido na lavoura sumiria da tela ao recarregar, e o
 * piloto preencheria tudo de novo — virando dois quando a fila subisse.
 */
function sobrepor(base: Plan[], fila: Pendente[]): Plan[] {
  const porId = new Map(base.map((plano) => [plano.id, plano]));
  for (const item of fila) {
    if (!porId.has(item.id)) {
      porId.set(item.id, comoPlano(item.corpo as PlanoNovo, item.id));
    }
  }
  // Os que ainda não têm número vão primeiro: são os do dia, e são os que pedem atenção.
  return [...porId.values()].sort((a, b) => (b.numero ?? Infinity) - (a.numero ?? Infinity));
}

export async function listarPlanos(empresa: string): Promise<VisaoDosPlanos> {
  const { fila, marcas, recusados } = await marcasDaFila(empresa);

  try {
    const doServidor = await agro.listPlans();
    await semQuebrar(gravarVarios(empresa, "planos", doServidor), undefined);
    return { planos: sobrepor(doServidor, fila), pendentes: marcas, recusados, doCache: false };
  } catch (causa) {
    if (!(causa instanceof SemRedeError)) throw causa;

    const guardados = await semQuebrar(lerTodos<Plan>(empresa, "planos"), [] as Plan[]);
    return { planos: sobrepor(guardados, fila), pendentes: marcas, recusados, doCache: true };
  }
}

export interface Cadastros {
  contratantes: AgroClient[];
  propriedades: AgroProperty[];
  doCache: boolean;
}

/** Os vínculos que o formulário precisa: quem contratou e onde fica a área.
 *
 * Guardados no aparelho porque sem eles não há planejamento nenhum — o `client_id` e o
 * `property_id` são obrigatórios, e na lavoura não há como consultar a lista.
 */
export async function cadastros(empresa: string): Promise<Cadastros> {
  try {
    const [contratantes, propriedades] = await Promise.all([
      agro.listClients(),
      agro.listProperties(),
    ]);
    await semQuebrar(gravarVarios(empresa, "contratantes", contratantes), undefined);
    await semQuebrar(gravarVarios(empresa, "propriedades", propriedades), undefined);
    return { contratantes, propriedades, doCache: false };
  } catch (causa) {
    if (!(causa instanceof SemRedeError)) throw causa;

    return {
      contratantes: await semQuebrar(
        lerTodos<AgroClient>(empresa, "contratantes"),
        [] as AgroClient[],
      ),
      propriedades: await semQuebrar(
        lerTodos<AgroProperty>(empresa, "propriedades"),
        [] as AgroProperty[],
      ),
      doCache: true,
    };
  }
}

export interface PlanoSalvo {
  plano: Plan;
  /** Ficou na fila em vez de ir ao servidor. */
  pendente: boolean;
}

/** Cria o planejamento. Sem rede, ele fica na fila e a tela segue.
 *
 * A identidade nasce aqui, e é o que torna o reenvio inofensivo: o servidor reconhece a
 * segunda chegada do mesmo pacote em vez de gastar outro número de documento.
 */
export async function salvarPlano(empresa: string, corpo: PlanoNovo): Promise<PlanoSalvo> {
  const id = corpo.id ?? crypto.randomUUID();
  const comIdentidade: PlanoNovo = { ...corpo, id };

  try {
    const plano = await agro.createPlan(comIdentidade as unknown as Record<string, unknown>);
    return { plano, pendente: false };
  } catch (causa) {
    if (!(causa instanceof SemRedeError)) throw causa;

    await enfileirar(empresa, { id, acao: ACAO_PLANO, corpo: comIdentidade });
    return { plano: comoPlano(comIdentidade, id), pendente: true };
  }
}

/** Manda ao servidor um planejamento que estava na fila. */
export async function enviar(_empresa: string, item: Pendente): Promise<void> {
  await agro.createPlan(item.corpo as Record<string, unknown>);
}

/** Baixa e guarda o que a lavoura vai precisar. Chamada ao abrir a tela, com rede. */
export async function atualizar(empresa: string): Promise<void> {
  await cadastros(empresa);
  await listarPlanos(empresa);
}
