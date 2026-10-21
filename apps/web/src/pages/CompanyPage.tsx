import { useEffect, useState } from "react";

import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { tenant } from "../lib/api";
import type { TenantProfile } from "../lib/api";
import { documentProblem, formatCpfCnpj, stripMask } from "../lib/documents";

interface Props {
  onBack: () => void;
}

type Campos = Omit<TenantProfile, "id" | "slug">;

/* O servidor guarda e devolve o documento sem máscara. Na tela ele volta formatado, que
 * é como a pessoa confere contra o papel — e é o mesmo que o PDF imprime. */
function paraTela({ id: _id, slug: _slug, ...perfil }: TenantProfile): Campos {
  return { ...perfil, cnpj: perfil.cnpj ? formatCpfCnpj(perfil.cnpj) : null };
}

const VAZIO: Campos = {
  name: "",
  cnpj: null,
  registro_mapa: null,
  crea: null,
  cda: null,
  inscricao_estadual: null,
  inscricao_municipal: null,
  rodape: null,
};

/* Identificação da empresa aplicadora.
 *
 * É o bloco que o Planejamento Operacional imprime no alto da página — registro no MAPA,
 * conselho e inscrições. Saía em branco: os campos não existiam e a permissão que os
 * editaria não tinha rota. Documento com cabeçalho vazio não substitui o talão.
 *
 * Preenchido uma vez, na implantação, e raramente revisitado. Por isso é uma tela só, com
 * tudo à vista, em vez de um wizard: aqui ninguém está em pé no meio da lavoura. */
export function CompanyPage({ onBack }: Props) {
  const [campos, setCampos] = useState<Campos>(VAZIO);
  const [carregando, setCarregando] = useState(true);
  const [salvo, setSalvo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    tenant
      .read()
      .then((perfil) => setCampos(paraTela(perfil)))
      .catch((causa) => setErro(causa instanceof Error ? causa.message : String(causa)))
      .finally(() => setCarregando(false));
  }, []);

  const problemaCnpj = campos.cnpj ? documentProblem(campos.cnpj) : null;

  function alterar<K extends keyof Campos>(campo: K, valor: string) {
    setSalvo(false);
    setCampos((atual) => ({ ...atual, [campo]: valor === "" ? null : valor }));
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const salvo = await tenant.save({
        ...campos,
        cnpj: campos.cnpj ? stripMask(campos.cnpj) : null,
      });
      setCampos(paraTela(salvo));
      setSalvo(true);
    } catch (causa) {
      setErro(causa instanceof Error ? causa.message : "Não foi possível salvar.");
    } finally {
      setSalvando(false);
    }
  }

  if (carregando) {
    return <p className="mx-auto max-w-xl px-6 py-10 text-lg text-ink-muted">Carregando…</p>;
  }

  return (
    <div className="mx-auto w-full max-w-xl px-6 py-8">
      <button
        type="button"
        onClick={onBack}
        className="min-h-touch text-base font-medium text-brand-link"
      >
        ← Voltar
      </button>

      <h1 className="mt-2 text-3xl font-bold text-ink">Dados da empresa</h1>
      <p className="mt-1 text-lg text-ink-muted">
        É o que sai impresso no cabeçalho do Planejamento Operacional. Em branco, o
        documento sai sem a identificação que a fiscalização procura.
      </p>

      <div className="mt-8 flex flex-col gap-5">
        <TextField
          label="Razão social"
          value={campos.name}
          onChange={(evento) => alterar("name", evento.target.value)}
        />
        <TextField
          label="CNPJ"
          hint={problemaCnpj ?? "Pode digitar com ponto e barra."}
          invalid={problemaCnpj !== null}
          autoCapitalize="characters"
          value={campos.cnpj ?? ""}
          onChange={(evento) => alterar("cnpj", evento.target.value)}
        />
        <TextField
          label="Nº de registro no MAPA"
          value={campos.registro_mapa ?? ""}
          onChange={(evento) => alterar("registro_mapa", evento.target.value)}
        />
        <TextField
          label="CREA"
          value={campos.crea ?? ""}
          onChange={(evento) => alterar("crea", evento.target.value)}
        />
        <TextField
          label="CDA"
          value={campos.cda ?? ""}
          onChange={(evento) => alterar("cda", evento.target.value)}
        />
        <TextField
          label="Inscrição estadual"
          value={campos.inscricao_estadual ?? ""}
          onChange={(evento) => alterar("inscricao_estadual", evento.target.value)}
        />
        <TextField
          label="Inscrição municipal"
          value={campos.inscricao_municipal ?? ""}
          onChange={(evento) => alterar("inscricao_municipal", evento.target.value)}
        />
        <TextField
          label="Rodapé do documento"
          hint="Endereço, telefone e e-mail como saem no rodapé do talão."
          value={campos.rodape ?? ""}
          onChange={(evento) => alterar("rodape", evento.target.value)}
        />

        {erro && (
          <p role="alert" className="rounded-dk bg-danger-soft px-4 py-3 text-base text-danger">
            {erro}
          </p>
        )}

        {/* Confirmação escrita, e não só o botão voltando ao normal: sem ela não dá para
            saber se o toque pegou. */}
        {salvo && !salvando && (
          <p role="status" className="rounded-dk bg-action-soft px-4 py-3 text-base text-ink">
            Dados da empresa salvos.
          </p>
        )}

        <Button
          onClick={() => void salvar()}
          loading={salvando}
          disabled={campos.name.trim() === "" || problemaCnpj !== null}
        >
          Salvar
        </Button>
      </div>
    </div>
  );
}
