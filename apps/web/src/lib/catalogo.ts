import { SemRedeError } from "./api";
import { comercial, type Produto } from "./comercial";
import { gravarVarios, lerTodos, LocalIndisponivelError } from "./local";
import { pdv } from "./pdv";

/* O catálogo que o aparelho guarda para o balcão não parar.
 *
 * Fatia 3 da `docs/adr/0022-offline-first-as-respostas.md`. O recorte — o que vem e por
 * quê — é decidido no servidor, em `pdv.catalogo_do_aparelho`: uma distribuidora tem
 * dezenas de milhares de itens, e o alvo inclui celular fraco.
 *
 * Aqui só ficam duas coisas: guardar o que o servidor mandou, e procurar no que está
 * guardado quando não há rede.
 */

async function semQuebrar<T>(trabalho: Promise<T>, vazio: T): Promise<T> {
  try {
    return await trabalho;
  } catch (causa) {
    if (causa instanceof LocalIndisponivelError) return vazio;
    throw causa;
  }
}

/** Baixa o recorte e guarda. Chamado ao abrir o PDV, com rede. */
export async function atualizar(empresa: string): Promise<number> {
  const produtos = await pdv.catalogoDoAparelho();
  await semQuebrar(gravarVarios(empresa, "produtos", produtos), undefined);
  return produtos.length;
}

/** O mesmo campo de busca do servidor, aplicado ao que está no aparelho.
 *
 * Código e código de barras batem inteiros — é o leitor passando o produto, e acerto
 * parcial aí lançaria o item errado. Nome é por pedaço, que é como se procura digitando.
 */
function combina(produto: Produto, termo: string): boolean {
  const alvo = termo.trim().toLowerCase();
  if (!alvo) return true;
  if (produto.codigo.toLowerCase() === alvo) return true;
  // `gtin` é o código de barras. O leitor passa o número inteiro, e é assim que ele bate.
  if (produto.gtin?.toLowerCase() === alvo) return true;
  return produto.nome.toLowerCase().includes(alvo);
}

export interface Achado {
  produtos: Produto[];
  /** Veio do aparelho, e não do servidor. */
  doAparelho: boolean;
}

/** Procura no servidor; sem rede, procura no que o aparelho guardou. */
export async function procurar(empresa: string, termo: string): Promise<Achado> {
  try {
    return { produtos: await comercial.listProdutos(termo), doAparelho: false };
  } catch (causa) {
    if (!(causa instanceof SemRedeError)) throw causa;

    const guardados = await semQuebrar(lerTodos<Produto>(empresa, "produtos"), [] as Produto[]);
    return {
      produtos: guardados
        .filter((produto) => combina(produto, termo))
        .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR")),
      doAparelho: true,
    };
  }
}
