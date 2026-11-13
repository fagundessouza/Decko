import { authedJson } from "./api";

export type TipoPessoa = "fisica" | "juridica";

export interface Cliente {
  id: string;
  tipo: TipoPessoa;
  nome: string;
  apelido: string | null;
  /** Qual empresa **da plataforma** este contato é, quando ele é uma. Nulo é o caso
   *  normal: quem compra no balcão não é empresa nenhuma. Ver ADR 0021, decisão 4. */
  tenant_assinante_id: string | null;
  /** Só os dígitos. A máscara é posta na leitura. */
  cpf_cnpj: string | null;
  inscricao_estadual: string | null;
  email: string | null;
  telefone: string | null;
  cep: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  cidade: string | null;
  uf: string | null;
  observacao: string | null;
  ativo: boolean;
}

/** O que a tela manda. Campo em branco vira nulo antes de sair daqui. */
export interface ClienteIn {
  tipo: TipoPessoa;
  nome: string;
  apelido?: string | null;
  tenant_assinante_id?: string | null;
  cpf_cnpj?: string | null;
  inscricao_estadual?: string | null;
  email?: string | null;
  telefone?: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  uf?: string | null;
  observacao?: string | null;
}

/* O `PUT` substitui o cadastro inteiro: campo que não vai na requisição volta a nulo.
 *
 * Isto existe para quem precisa mexer em **um** campo de um contato já carregado — ligar
 * a empresa da plataforma, por exemplo — sem apagar o resto por omissão. O formulário de
 * cliente monta o corpo dele a partir dos campos da tela, e lá a conta é outra. */
export function comoEntrada(cliente: Cliente, mudanca: Partial<ClienteIn> = {}): ClienteIn {
  return {
    tipo: cliente.tipo,
    nome: cliente.nome,
    apelido: cliente.apelido,
    tenant_assinante_id: cliente.tenant_assinante_id,
    cpf_cnpj: cliente.cpf_cnpj,
    inscricao_estadual: cliente.inscricao_estadual,
    email: cliente.email,
    telefone: cliente.telefone,
    cep: cliente.cep,
    logradouro: cliente.logradouro,
    numero: cliente.numero,
    complemento: cliente.complemento,
    bairro: cliente.bairro,
    cidade: cliente.cidade,
    uf: cliente.uf,
    observacao: cliente.observacao,
    ...mudanca,
  };
}

export const clientes = {
  listar: (busca?: string, incluirInativos = false): Promise<Cliente[]> => {
    const parametros = new URLSearchParams();
    if (busca?.trim()) parametros.set("busca", busca.trim());
    if (incluirInativos) parametros.set("incluir_inativos", "true");
    const consulta = parametros.toString();
    return authedJson(`/clientes/clientes${consulta ? `?${consulta}` : ""}`);
  },

  criar: (body: ClienteIn): Promise<Cliente> =>
    authedJson("/clientes/clientes", { method: "POST", body }),

  atualizar: (clienteId: string, body: ClienteIn): Promise<Cliente> =>
    authedJson(`/clientes/clientes/${clienteId}`, { method: "PUT", body }),

  desativar: (clienteId: string): Promise<Cliente> =>
    authedJson(`/clientes/clientes/${clienteId}/desativar`, { method: "POST" }),

  reativar: (clienteId: string): Promise<Cliente> =>
    authedJson(`/clientes/clientes/${clienteId}/reativar`, { method: "POST" }),
};
