import { authedJson } from "./api";

export type TipoPessoa = "fisica" | "juridica";

export interface Cliente {
  id: string;
  tipo: TipoPessoa;
  nome: string;
  apelido: string | null;
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
