/* O armazenamento do aparelho, em IndexedDB.
 *
 * Escrito à mão, sem biblioteca, por dois motivos. O peso é requisito pela regra 5 do
 * CLAUDE.md, e o que o Decko precisa é uma fração do que qualquer invólucro de IndexedDB
 * oferece: abrir, ler, gravar, apagar e listar. O resto seria peso carregado por um PC de
 * caixa antigo para nunca ser usado.
 *
 * Tudo aqui é por empresa. O isolamento entre empresas no servidor é feito pelo
 * PostgreSQL, e aqui não existe Row Level Security nenhuma — então a separação é no nome
 * do banco. Trocar de empresa no mesmo aparelho não pode fazer o cadastro de uma aparecer
 * na tela da outra.
 *
 * Nada disto é garantido: navegador em janela anônima, armazenamento bloqueado e cota
 * estourada são reais. Toda leitura devolve vazio quando falha, e toda escrita avisa quem
 * chamou — quem decide o que fazer é a tela, não esta camada.
 */

/* Sobe quando um armazém entra ou sai: `onupgradeneeded` só roda quando a versão muda, e
 * sem isso o armazém novo não existe no aparelho de quem já usou o sistema antes. */
const VERSAO = 3;

export type Armazem = "fila" | "clientes" | "produtos" | "avisos" | "configuracao";

const ARMAZENS: Armazem[] = ["fila", "clientes", "produtos", "avisos", "configuracao"];

/** Falha de armazenamento local. Quem chama decide se isso é fatal para a operação. */
export class LocalIndisponivelError extends Error {
  constructor(causa?: unknown) {
    super("O armazenamento deste aparelho não está disponível.");
    this.name = "LocalIndisponivelError";
    this.cause = causa;
  }
}

let aberto: { chave: string; db: IDBDatabase } | null = null;

function nomeDoBanco(empresa: string): string {
  return `decko:${empresa}`;
}

async function abrir(empresa: string): Promise<IDBDatabase> {
  const chave = nomeDoBanco(empresa);
  if (aberto?.chave === chave) return aberto.db;

  if (typeof indexedDB === "undefined") throw new LocalIndisponivelError();

  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    let pedido: IDBOpenDBRequest;
    try {
      pedido = indexedDB.open(chave, VERSAO);
    } catch (causa) {
      reject(new LocalIndisponivelError(causa));
      return;
    }
    pedido.onupgradeneeded = () => {
      for (const armazem of ARMAZENS) {
        if (!pedido.result.objectStoreNames.contains(armazem)) {
          pedido.result.createObjectStore(armazem, { keyPath: "id" });
        }
      }
    };
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(new LocalIndisponivelError(pedido.error));
    // Outra aba segurando uma versão antiga. Não trava a tela esperando por ela.
    pedido.onblocked = () => reject(new LocalIndisponivelError("outra aba está aberta"));
  });

  aberto = { chave, db };
  return db;
}

function promessaDe<T>(pedido: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(new LocalIndisponivelError(pedido.error));
  });
}

/** Grava, substituindo o que houver com a mesma chave. */
export async function gravar<T extends { id: string }>(
  empresa: string,
  armazem: Armazem,
  valor: T,
): Promise<void> {
  const db = await abrir(empresa);
  const transacao = db.transaction(armazem, "readwrite");
  await promessaDe(transacao.objectStore(armazem).put(valor));
}

/** Grava vários de uma vez. Uma transação só: meia lista gravada é pior do que nenhuma. */
export async function gravarVarios<T extends { id: string }>(
  empresa: string,
  armazem: Armazem,
  valores: T[],
): Promise<void> {
  if (valores.length === 0) return;
  const db = await abrir(empresa);
  const transacao = db.transaction(armazem, "readwrite");
  const alvo = transacao.objectStore(armazem);
  await Promise.all(valores.map((valor) => promessaDe(alvo.put(valor))));
}

export async function ler<T>(empresa: string, armazem: Armazem, id: string): Promise<T | null> {
  const db = await abrir(empresa);
  const transacao = db.transaction(armazem, "readonly");
  const achado = await promessaDe<T | undefined>(transacao.objectStore(armazem).get(id));
  return achado ?? null;
}

export async function lerTodos<T>(empresa: string, armazem: Armazem): Promise<T[]> {
  const db = await abrir(empresa);
  const transacao = db.transaction(armazem, "readonly");
  return promessaDe<T[]>(transacao.objectStore(armazem).getAll());
}

export async function apagar(empresa: string, armazem: Armazem, id: string): Promise<void> {
  const db = await abrir(empresa);
  const transacao = db.transaction(armazem, "readwrite");
  await promessaDe(transacao.objectStore(armazem).delete(id));
}

export async function esvaziar(empresa: string, armazem: Armazem): Promise<void> {
  const db = await abrir(empresa);
  const transacao = db.transaction(armazem, "readwrite");
  await promessaDe(transacao.objectStore(armazem).clear());
}

/** Esquece a conexão aberta. Usado ao trocar de empresa e pelos testes. */
export function fechar(): void {
  aberto?.db.close();
  aberto = null;
}
