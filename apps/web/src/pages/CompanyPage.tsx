import { useEffect, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { tenant } from "../lib/api";
import type { TenantProfile } from "../lib/api";
import { documentProblem, formatCpfCnpj, stripMask } from "../lib/documents";

interface Props {
  onBack: () => void;
  /* Se esta empresa tem o módulo de pulverização.
   *
   * Registro no MAPA, CREA e CDA só existem para quem aplica defensivo: são o cabeçalho
   * que o Planejamento Operacional imprime e que a fiscalização procura. Numa padaria,
   * três campos assim no meio das inscrições não são só inúteis — são confusos, porque
   * parecem obrigatórios.
   *
   * Quem decide é a ativação do módulo, nunca a permissão: o administrador recebe as
   * permissões de todos os módulos instalados na plataforma — ver
   * docs/adr/0004-ativacao-de-modulo-por-empresa.md. */
  temAgro: boolean;
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

/* Identificação da empresa.
 *
 * É o cabeçalho que os documentos imprimem. Razão social, documento, inscrições e rodapé
 * valem para qualquer empresa; registro no MAPA, CREA e CDA só aparecem para quem tem o
 * módulo de pulverização, porque só lá eles significam alguma coisa.
 *
 * As três colunas de agro ainda moram em `tenant`, que é tabela do núcleo. Guardar dado de
 * um módulo na tabela de outro é o avesso da regra de fronteira do `CLAUDE.md`; esconder os
 * campos resolve a confusão de quem usa, não a de quem mantém. Mudar de lugar é migração
 * entre dois módulos, e precisa de ADR própria.
 *
 * Preenchido uma vez, na implantação, e raramente revisitado. Por isso é uma tela só, com
 * tudo à vista, em vez de um wizard: aqui ninguém está em pé no meio da lavoura. */
export function CompanyPage({ onBack, temAgro }: Props) {
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
    /* Campo em branco é ausência, e o servidor guarda nulo — menos a razão social, que é
     * obrigatória e por isso é texto sempre. Nulo ali derrubava a tela inteira no
     * `name.trim()` do botão, e o caminho para isso é o mais comum que existe: apagar o
     * campo para redigitá-lo. */
    const vazio = campo === "name" ? "" : null;
    setCampos((atual) => ({ ...atual, [campo]: valor === "" ? vazio : valor }));
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
    <Page>
      <PageHeader
        title="Dados da empresa"
        description="É o que sai impresso no cabeçalho dos documentos. Em branco, o documento sai sem a identificação de quem o emitiu."
        onBack={onBack}
      />

      <div className="flex flex-col gap-5">
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

        {/* O bloco de quem aplica defensivo. Separado e nomeado, porque estes três são de
            um ramo só — no meio das inscrições, pareciam exigência de toda empresa. */}
        {temAgro && (
          <fieldset className="flex flex-col gap-5 border-t border-line-subtle pt-5">
            {/* O nome do bloco é a `legend`, e não um título ao lado dela: a `legend` já é
                o nome acessível do grupo, e repeti-lo num `h2` faz o leitor de tela dizer
                duas vezes. */}
            <legend className="text-base font-semibold text-ink">
              Pulverização agrícola
              <span className="mt-1 block text-sm font-normal text-ink-muted">
                Sai no alto do Planejamento Operacional. É a identificação que a fiscalização
                procura.
              </span>
            </legend>

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
          </fieldset>
        )}

        {erro && <Alert tone="danger">{erro}</Alert>}

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
    </Page>
  );
}
