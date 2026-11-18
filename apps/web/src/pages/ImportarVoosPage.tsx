import { useEffect, useRef, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader, Row } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { TextField } from "../components/TextField";
import { agro } from "../lib/agro";
import { comercial } from "../lib/comercial";
import type { Produto } from "../lib/comercial";
import { escalar, escrever, aoCentavo } from "../lib/dinheiro";
import type {
  AgroProperty,
  AplicacaoConfirmada,
  Plan,
  PlanProduct,
  Product as ProdutoDoReceituario,
  RegistroDeVooLido,
  VooConfirmado,
  VooDoRegistro,
  VooRegistrado,
} from "../lib/agro";
import { dateBr, num } from "../lib/format";

interface Props {
  onBack: () => void;
}

/* A importação do registro de voo do equipamento.
 *
 * O pedido é do Nathan, em 13/11/2026 — não redigitar horário de início, fim e área
 * aplicada. A forma é a da entrada por nota do módulo `compras`: o sistema lê, mostra o
 * que entendeu, e **a pessoa confirma**. Nada é gravado antes disso, e o motivo está no
 * destino do dado: o relatório mensal vai ao MAPA, e divergência ali custa dinheiro.
 *
 * Três coisas desta tela não são enfeite:
 *
 * - **O controle de fuso.** O arquivo não declara fuso. O servidor manda os dois horários,
 *   e aqui se escolhe qual vale — sem nova requisição, porque os dois já vieram.
 * - **O cadastro rápido da aeronave.** O arquivo identifica o equipamento pelo número de
 *   série; quem identifica a ARP para o MAPA é o prefixo, que vive no cadastro.
 * - **A lista de voos auxiliares.** Translado e calibração não vão ao relatório e vão ao
 *   horímetro. Mostrá-los é o que explica a diferença entre o arquivo e o documento.
 */
export function ImportarVoosPage({ onBack }: Props) {
  const [lido, setLido] = useState<RegistroDeVooLido | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [arrastando, setArrastando] = useState(false);
  /* O horário que vale: o ajustado pelo fuso sugerido, ou o do arquivo como está.
   *
   * Começa no ajustado porque é a leitura mais provável — ver a seção 7.5 do discovery —,
   * e a troca não refaz a requisição: os dois horários já vieram. */
  const [usarAjustado, setUsarAjustado] = useState(true);
  const [cadastrando, setCadastrando] = useState<string | null>(null);
  /* O defensivo que saiu do estoque em cada aplicação, escolhido por quem confirma.
   *
   * Fica por aplicação, e não uma escolha para o arquivo inteiro: um dia de voo pode ter
   * passado inseticida num talhão e fungicida no outro, e uma escolha só poria a baixa no
   * produto errado. Vazio é válido — aplicação de quem não controla estoque de defensivo
   * não deve travar a importação. */
  const [insumos, setInsumos] = useState<Record<string, Insumo>>({});
  const [produtos, setProdutos] = useState<Produto[]>([]);
  /* O planejamento vinculado a cada aplicação. Opcional: voo avulso existe, e exigir
   * planejamento faria o operador inventar um para poder registrar o que aconteceu. */
  const [planos, setPlanos] = useState<Record<string, string>>({});
  const [planejamentos, setPlanejamentos] = useState<Plan[]>([]);
  const [propriedades, setPropriedades] = useState<AgroProperty[]>([]);
  const [doReceituario, setDoReceituario] = useState<ProdutoDoReceituario[]>([]);
  const [registrado, setRegistrado] = useState<VooRegistrado | null>(null);
  const campo = useRef<HTMLInputElement>(null);

  /* Os produtos do estoque, para a escolha do defensivo.
   *
   * Falha em silêncio de propósito: a empresa pode não ter o estoque montado, e sem
   * produto a importação continua valendo — ela só não dá baixa em nada. */
  useEffect(() => {
    comercial
      .listProdutos()
      .then(setProdutos)
      .catch(() => setProdutos([]));
  }, []);

  /* Os planejamentos para vincular, as propriedades para sugerir pelo nome do talhão, e o
   * cadastro de produtos do receituário para dizer qual defensivo foi prescrito.
   *
   * Falha em silêncio pelo mesmo motivo do estoque: sem planejamento a importação continua
   * valendo — ela só não vincula nada. */
  useEffect(() => {
    void Promise.all([agro.listPlans(), agro.listProperties(), agro.listProducts()])
      .then(([abertos, areas, cadastro]) => {
        setPlanejamentos(abertos);
        setPropriedades(areas);
        setDoReceituario(cadastro);
      })
      .catch(() => undefined);
  }, []);

  async function importar(arquivo: File) {
    setBusy(true);
    setErro(null);
    try {
      const bytes = new Uint8Array(await arquivo.arrayBuffer());
      let binario = "";
      for (const byte of bytes) binario += String.fromCharCode(byte);
      setLido(await agro.lerRegistroDeVoo(btoa(binario)));
      setRegistrado(null);
    } catch (cause) {
      setErro(
        cause instanceof Error ? cause.message : "Não foi possível ler o registro de voo.",
      );
    } finally {
      setBusy(false);
      // Sem isto, escolher o mesmo arquivo de novo não dispara o evento.
      if (campo.current) campo.current.value = "";
    }
  }

  /** O instante que vai ao servidor, a partir do relógio de parede escolhido.
   *
   * O horário escolhido é lido como horário **deste aparelho** — `new Date` com texto sem
   * fuso faz isso — e vai em ISO com deslocamento explícito. É o servidor que recusa
   * horário sem fuso, e está certo: fuso implícito é o erro que esta tela existe para não
   * repetir. */
  function instante(ajustado: string, doArquivo: string): string {
    return new Date(usarAjustado ? ajustado : doArquivo).toISOString();
  }

  function comoVoo(linha: VooDoRegistro, aircraftId: string | null): VooConfirmado {
    return {
      comecou_em: instante(linha.comecou_em_ajustado, linha.comecou_em),
      terminou_em: instante(linha.terminou_em_ajustado, linha.terminou_em),
      // O instante do arquivo vai cru: é ele que faz a reimportação ser reconhecida.
      comecou_em_arquivo: linha.comecou_em,
      duracao_segundos: linha.duracao_segundos,
      equipamento_serie: linha.equipamento_serie,
      equipamento_apelido: linha.aeronave,
      piloto: linha.piloto,
      lugar: linha.lugar,
      aircraft_id: aircraftId,
    };
  }

  async function confirmar() {
    if (!lido) return;
    setBusy(true);
    setErro(null);
    try {
      const aplicacoes: AplicacaoConfirmada[] = lido.aplicacoes.map((aplicacao) => ({
        plot_id: aplicacao.plot_id,
        talhao: aplicacao.talhao,
        aircraft_id: aplicacao.aircraft_id,
        area_ha: aplicacao.area_ha,
        volume_l: aplicacao.volume_l,
        largura_faixa_m: aplicacao.largura_faixa_m,
        altura_voo_m: aplicacao.altura_voo_m,
        /* Todos os voos da aplicação, um por bateria. Cinco baterias são cinco pousos e
         * cinco decolagens, e mandar uma linha só faria o horímetro da aeronave mentir
         * sobre o uso — mesmo com o total de horas certo. */
        voos: aplicacao.voos_detalhados.map((voo) =>
          comoVoo(voo, aplicacao.aircraft_id),
        ),
        plan_id: planos[chaveDaAplicacao(aplicacao)] || null,
        insumos: insumoDaAplicacao(aplicacao),
      }));

      const resultado = await agro.confirmarRegistroDeVoo({
        aplicacoes,
        voos_auxiliares: lido.voos_auxiliares.map((voo) =>
          comoVoo(voo, aeronaveDoVoo(voo)),
        ),
      });
      setRegistrado(resultado);
      setLido(null);
    } catch (cause) {
      setErro(cause instanceof Error ? cause.message : "Não foi possível registrar.");
    } finally {
      setBusy(false);
    }
  }

  /** Quanto do defensivo saiu: a dose por hectare vezes a área que o drone mediu.
   *
   * A conta é em inteiros, pela mesma razão do caixa: dose com casas decimais vezes área
   * com casas decimais em ponto flutuante erra na última casa, e aqui a última casa é
   * litro de defensivo saindo do estoque de alguém.
   *
   * O que sai é **o produto**, nunca a calda: calda é mistura, e quase toda ela é água.
   * Dar baixa dos litros de calda poria no estoque uma saída que não aconteceu.
   */
  function quantidadeDoInsumo(dosePorHa: string, areaHa: string): string | null {
    try {
      const dose = escalar(dosePorHa, 4);
      const area = escalar(areaHa, 4);
      if (dose <= 0n) return null;
      return escrever(aoCentavo(dose * area, 10_000n), 4);
    } catch {
      // Dose que não é número ainda está sendo digitada; não é erro de tela.
      return null;
    }
  }

  function insumoDaAplicacao(aplicacao: {
    plot_id: string;
    dia: string;
    area_ha: string;
  }): { produto_id: string; quantidade: string }[] {
    const escolha = insumos[chaveDaAplicacao(aplicacao)];
    if (!escolha?.produtoId) return [];
    const quantidade = quantidadeDoInsumo(escolha.dosePorHa, aplicacao.area_ha);
    return quantidade === null ? [] : [{ produto_id: escolha.produtoId, quantidade }];
  }

  /** Os planejamentos que podem receber uma aplicação importada.
   *
   * Assinado e enviado ficam de fora: mudar a área de um documento assinado quebraria a
   * correspondência com a assinatura, e o servidor recusa fazer isso — oferecer na tela o
   * que vai ser recusado é desperdiçar o tempo de quem está conferindo.
   */
  const vinculaveis = planejamentos.filter(
    (plano) => plano.status === "rascunho" || plano.status === "concluido",
  );

  /** O planejamento cuja propriedade tem o nome do talhão do arquivo.
   *
   * Sugestão, e só: o nome do talhão no aplicativo é livre ("Ronan milho 1"), e o do
   * cadastro é da propriedade. Quando um só bate, ele aparece marcado — mas **não é
   * escolhido sozinho**, porque vincular troca a área de um documento, e isso é decisão de
   * quem está conferindo.
   */
  function sugerido(talhao: string | null): string | null {
    if (!talhao) return null;
    const alvo = semAcento(talhao);
    const batem = vinculaveis.filter((plano) => {
      const propriedade = propriedades.find((area) => area.id === plano.property_id);
      if (!propriedade) return false;
      const nome = semAcento(propriedade.nome);
      return nome.length > 2 && (alvo.includes(nome) || nome.includes(alvo));
    });
    return batem.length === 1 ? batem[0].id : null;
  }

  /** Vincula o planejamento e traz dele a dose e o defensivo do receituário. */
  async function vincular(chave: string, planId: string, areaHa: string) {
    setPlanos((atual) => ({ ...atual, [chave]: planId }));
    if (!planId) return;

    try {
      const linhas = await agro.listPlanProducts(planId);
      const prescrito = linhas.find((linha) => linha.dosagem_ha !== null) ?? linhas[0];
      if (!prescrito) return;
      mexerNoInsumo(chave, {
        dosePorHa: prescrito.dosagem_ha ?? "",
        produtoId: doEstoque(prescrito) ?? "",
      });
    } catch {
      /* Receituário que não carrega não impede o vínculo: a dose fica para quem confirma
       * digitar, como era antes desta fatia. */
    }
    void areaHa;
  }

  /** O produto do estoque que tem o mesmo nome do prescrito no receituário.
   *
   * O cadastro do receituário e o do estoque são tabelas diferentes, e não há vínculo
   * entre elas — então o que existe é o nome. A correspondência é **exata**, e fica à
   * vista para quem confirma: adivinhar por semelhança daria baixa no produto errado, que
   * é o tipo de erro que só aparece na contagem do estoque, semanas depois.
   */
  function doEstoque(linha: PlanProduct): string | null {
    const prescrito = doReceituario.find((item) => item.id === linha.product_id);
    if (!prescrito) return null;
    const alvo = semAcento(prescrito.nome_comercial);
    return produtos.find((produto) => semAcento(produto.nome) === alvo)?.id ?? null;
  }

  function mexerNoInsumo(chave: string, parte: Partial<Insumo>) {
    setInsumos((atual) => {
      const anterior: Insumo = atual[chave] ?? { produtoId: "", dosePorHa: "" };
      return { ...atual, [chave]: { ...anterior, ...parte } };
    });
  }

  /** A aeronave do voo auxiliar, achada pelo série no horímetro que o servidor montou. */
  function aeronaveDoVoo(voo: VooDoRegistro): string | null {
    const horas = lido?.horimetro.find(
      (linha) => linha.equipamento_serie === voo.equipamento_serie,
    );
    return horas?.aircraft_id ?? null;
  }

  async function cadastrarAeronave(prefixo: string, modelo: string, fabricante: string) {
    if (!cadastrando) return;
    setBusy(true);
    setErro(null);
    try {
      await agro.createAircraft({
        prefixo,
        modelo: modelo || null,
        fabricante: fabricante || null,
        numero_serie: cadastrando,
      });
      setCadastrando(null);
      // A leitura é refeita para o casamento acontecer: a aeronave agora existe.
      setErro("Aeronave cadastrada. Importe o arquivo de novo para ele achar a aeronave.");
      setLido(null);
    } catch (cause) {
      setErro(cause instanceof Error ? cause.message : "Não foi possível cadastrar.");
    } finally {
      setBusy(false);
    }
  }

  const entrada = (
    <input
      ref={campo}
      type="file"
      accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      className="hidden"
      onChange={(event) => {
        const escolhido = event.target.files?.[0];
        if (escolhido) void importar(escolhido);
      }}
    />
  );

  return (
    <Page wide>
      <PageHeader
        title="Importar voos"
        description="O registro que o aplicativo do drone exporta, lido e conferido antes de entrar."
        onBack={onBack}
      />

      {entrada}

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {registrado && (
        <div className="mb-6">
          <Alert tone="success" title="Registrado">
            <span className="flex flex-col gap-1">
              <span>
                {registrado.aplicacoes} aplicação(ões) e {registrado.voos_gravados} voo(s)
                entraram
                {registrado.baixas_de_estoque > 0
                  ? `, com ${registrado.baixas_de_estoque} baixa(s) de estoque`
                  : ""}
                .
              </span>
              {registrado.avisos.map((aviso) => (
                <span key={aviso} className="text-ink-muted">
                  {aviso}
                </span>
              ))}
            </span>
          </Alert>
        </div>
      )}

      {lido === null && (
        <Card muted>
          <CardBody>
            <div
              role="presentation"
              onDragOver={(event) => {
                event.preventDefault();
                setArrastando(true);
              }}
              onDragLeave={() => setArrastando(false)}
              onDrop={(event) => {
                event.preventDefault();
                setArrastando(false);
                const arquivo = event.dataTransfer.files?.[0];
                if (arquivo) void importar(arquivo);
              }}
              onClick={() => campo.current?.click()}
              className={
                "flex cursor-pointer flex-col items-center gap-3 rounded-dk border-2 border-dashed px-5 py-12 text-center transition-colors duration-150 ease-dk " +
                (arrastando ? "border-brand-link bg-brand-soft" : "border-line")
              }
            >
              <p className="text-base font-medium text-ink">
                Arraste aqui o arquivo de voos, ou toque para escolher
              </p>
              <p className="max-w-prose text-sm text-ink-muted">
                É o `.xlsx` ou `.csv` que o aplicativo do drone exporta. Nada é gravado
                agora: o que o sistema entender aparece para você conferir antes.
              </p>
              <div className="mt-2">
                <Button inline loading={busy}>
                  Escolher arquivo
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {lido !== null && (
        <>
          {lido.avisos.map((aviso) => (
            <div className="mb-3" key={aviso}>
              <Alert tone="warn">{aviso}</Alert>
            </div>
          ))}

          {lido.series_sem_aeronave.length > 0 && (
            <div className="mb-6">
              <Alert tone="warn" title="Equipamento sem aeronave cadastrada">
                <span className="flex flex-wrap items-center gap-2">
                  <span>
                    O relatório do MAPA identifica a aeronave pelo prefixo, e este
                    equipamento ainda não tem cadastro:
                  </span>
                  {lido.series_sem_aeronave.map((serie) => (
                    <Button
                      key={serie}
                      variant="secondary"
                      inline
                      onClick={() => setCadastrando(serie)}
                    >
                      Cadastrar {serie}
                    </Button>
                  ))}
                </span>
              </Alert>
            </div>
          )}

          <div className="mb-6 flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              inline
              onClick={() => setUsarAjustado((atual) => !atual)}
            >
              {usarAjustado ? "Mostrando horário local" : "Mostrando horário do arquivo"}
            </Button>
            <span className="text-sm text-ink-muted">
              {usarAjustado
                ? `O arquivo não diz o fuso; estes horários têm ${lido.fuso_minutos / 60}h aplicadas.`
                : "Estes são os horários como estão no arquivo, sem conversão."}
            </span>
          </div>

          <Card>
            <CardHeader
              title="Aplicações"
              description="Os voos do mesmo talhão no mesmo dia, somados. É o que vai ao relatório."
            />
            <ul>
              {lido.aplicacoes.map((aplicacao) => (
                <Row key={`${aplicacao.plot_id}-${aplicacao.dia}`}>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-base font-medium text-ink">
                      {aplicacao.talhao ?? "Talhão sem nome"}
                      {aplicacao.prefixo ? ` · ${aplicacao.prefixo}` : ""}
                    </p>
                    <p className="text-sm text-ink-muted">
                      {dateBr(aplicacao.dia)} · {hora(aplicacao, usarAjustado)} ·{" "}
                      {aplicacao.voos} voo(s) · {duracao(aplicacao.duracao_segundos)}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-right">
                    <span className="text-base font-semibold tabular-nums text-ink">
                      {num(aplicacao.area_ha, 2)} ha
                    </span>
                    <span className="text-sm tabular-nums text-ink-muted">
                      {num(aplicacao.volume_l, 2)} L de calda
                      {aplicacao.volume_por_ha
                        ? ` · ${num(aplicacao.volume_por_ha, 2)} L/ha`
                        : ""}
                    </span>
                    {aplicacao.aircraft_id === null && (
                      <Badge tone="warn">sem aeronave</Badge>
                    )}
                  </div>

                  {/* A escolha do defensivo fica junto da aplicação a que ela pertence:
                      um dia de voo pode ter passado inseticida num talhão e fungicida no
                      outro, e uma escolha só para o arquivo poria a baixa no produto
                      errado. */}
                  <div className="w-full basis-full">
                    <Planejamento
                      chave={chaveDaAplicacao(aplicacao)}
                      escolhido={planos[chaveDaAplicacao(aplicacao)] ?? ""}
                      opcoes={vinculaveis}
                      sugerido={sugerido(aplicacao.talhao)}
                      areaMedida={aplicacao.area_ha}
                      onVincular={(chave, planId) =>
                        void vincular(chave, planId, aplicacao.area_ha)
                      }
                    />
                    <Insumos
                      chave={chaveDaAplicacao(aplicacao)}
                      areaHa={aplicacao.area_ha}
                      produtos={produtos}
                      escolha={insumos[chaveDaAplicacao(aplicacao)]}
                      quantidade={quantidadeDoInsumo(
                        insumos[chaveDaAplicacao(aplicacao)]?.dosePorHa ?? "",
                        aplicacao.area_ha,
                      )}
                      onMudar={mexerNoInsumo}
                    />
                  </div>
                </Row>
              ))}
            </ul>
          </Card>

          {lido.voos_auxiliares.length > 0 && (
            <div className="mt-6">
              <Card>
                <CardHeader
                  title="Voos que não pulverizaram"
                  description="Translado, calibração e teste. Não vão ao relatório do MAPA; vão ao horímetro da aeronave."
                />
                <ul>
                  {lido.voos_auxiliares.map((voo) => (
                    <Row key={voo.comecou_em}>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-base text-ink">
                          {voo.aeronave || "Equipamento sem apelido"}
                        </p>
                        <p className="text-sm text-ink-muted">
                          {hora(voo, usarAjustado)}
                          {voo.piloto ? ` · ${voo.piloto}` : ""}
                        </p>
                      </div>
                      <span className="shrink-0 text-sm tabular-nums text-ink-muted">
                        {duracao(voo.duracao_segundos)}
                      </span>
                    </Row>
                  ))}
                </ul>
              </Card>
            </div>
          )}

          <div className="mt-6">
            <Card>
              <CardHeader
                title="Horímetro"
                description="O que cada equipamento voou neste arquivo, aplicando e sem aplicar."
              />
              <ul>
                {lido.horimetro.map((horas) => (
                  <Row key={horas.equipamento_serie ?? horas.aeronave}>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-base text-ink">
                        {horas.prefixo ?? horas.aeronave}
                      </p>
                      <p className="truncate text-sm text-ink-faint">
                        {horas.equipamento_serie ?? "sem número de série"}
                      </p>
                    </div>
                    <span className="shrink-0 text-sm tabular-nums text-ink-muted">
                      {duracao(horas.duracao_total_segundos)} ·{" "}
                      {duracao(horas.duracao_aplicando_segundos)} aplicando
                    </span>
                  </Row>
                ))}
              </ul>
            </Card>
          </div>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="secondary" inline onClick={() => setLido(null)}>
              Descartar
            </Button>
            <Button inline loading={busy} onClick={() => void confirmar()}>
              Confirmar e registrar aplicação
            </Button>
          </div>
        </>
      )}

      <CadastroRapido
        serie={cadastrando}
        onClose={() => setCadastrando(null)}
        onSalvar={cadastrarAeronave}
        busy={busy}
      />
    </Page>
  );
}

/** "18:51 → 18:58", no horário que está sendo mostrado. */
function hora(
  linha: {
    comecou_em: string;
    terminou_em: string;
    comecou_em_ajustado: string;
    terminou_em_ajustado: string;
  },
  ajustado: boolean,
): string {
  const corte = (texto: string) => texto.slice(11, 16);
  return ajustado
    ? `${corte(linha.comecou_em_ajustado)} → ${corte(linha.terminou_em_ajustado)}`
    : `${corte(linha.comecou_em)} → ${corte(linha.terminou_em)}`;
}

function duracao(segundos: number): string {
  const horas = Math.floor(segundos / 3600);
  const minutos = Math.round((segundos % 3600) / 60);
  return horas > 0 ? `${horas}h${String(minutos).padStart(2, "0")}` : `${minutos} min`;
}

/* O cadastro da aeronave feito de dentro da importação.
 *
 * O equipamento aparece no arquivo antes de alguém cadastrá-lo, e mandar a pessoa para
 * outra tela no meio da conferência é perder o que ela já revisou. Pede o mínimo: o
 * prefixo, que é o que identifica a ARP para o MAPA, e marca e modelo, que são do
 * equipamento. O número de série vem do arquivo. */
function CadastroRapido({
  serie,
  onClose,
  onSalvar,
  busy,
}: {
  serie: string | null;
  onClose: () => void;
  onSalvar: (prefixo: string, modelo: string, fabricante: string) => void;
  busy: boolean;
}) {
  const [prefixo, setPrefixo] = useState("");
  const [modelo, setModelo] = useState("");
  const [fabricante, setFabricante] = useState("");

  return (
    <Modal
      open={serie !== null}
      title="Cadastrar a aeronave"
      description="O arquivo traz o número de série; o relatório do MAPA pede o prefixo."
      onClose={onClose}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="secondary" inline onClick={onClose}>
            Cancelar
          </Button>
          <Button
            inline
            loading={busy}
            disabled={!prefixo.trim()}
            onClick={() => onSalvar(prefixo.trim(), modelo.trim(), fabricante.trim())}
          >
            Cadastrar
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <TextField
          label="Prefixo (ANAC/SISANT)"
          value={prefixo}
          autoFocus
          onChange={(event) => setPrefixo(event.target.value)}
          hint="É o que identifica a aeronave no relatório mensal."
        />
        <TextField
          label="Marca"
          value={fabricante}
          onChange={(event) => setFabricante(event.target.value)}
        />
        <TextField
          label="Modelo"
          value={modelo}
          onChange={(event) => setModelo(event.target.value)}
        />
        <p className="text-sm text-ink-faint">Número de série: {serie}</p>
      </div>
    </Modal>
  );
}

/** O defensivo escolhido para uma aplicação, como a tela o guarda. */
interface Insumo {
  produtoId: string;
  dosePorHa: string;
}

/** A chave da aplicação na tela: talhão mais dia, que é como o servidor a agrupa. */
function chaveDaAplicacao(aplicacao: { plot_id: string; dia: string }): string {
  return `${aplicacao.plot_id}-${aplicacao.dia}`;
}

/* A escolha do defensivo que saiu do estoque nesta aplicação.
 *
 * Pede dose por hectare, e não quantidade total, porque dose é o que está no receituário
 * e o que o piloto sabe de cabeça. O total é conta do sistema, com a área que o
 * equipamento mediu — e aparece à vista, porque é ele que vai sair do estoque.
 *
 * Deixar em branco é válido: quem não controla estoque de defensivo no Decko importa os
 * voos sem dar baixa em nada. Travar aqui seria impedir o registro do que aconteceu por
 * causa de um cadastro que talvez não exista. */
function Insumos({
  chave,
  areaHa,
  produtos,
  escolha,
  quantidade,
  onMudar,
}: {
  chave: string;
  areaHa: string;
  produtos: Produto[];
  escolha: Insumo | undefined;
  quantidade: string | null;
  onMudar: (chave: string, parte: Partial<Insumo>) => void;
}) {
  if (produtos.length === 0) return null;

  return (
    <div className="mt-3 flex flex-col gap-3 border-t border-line-subtle pt-3 sm:flex-row sm:items-end">
      <div className="min-w-0 flex-1">
        <Select
          label="Defensivo usado"
          value={escolha?.produtoId ?? ""}
          onChange={(valor) => onMudar(chave, { produtoId: valor })}
          options={produtos.map((produto) => ({
            value: produto.id,
            label: produto.nome,
          }))}
          placeholder="Não dar baixa"
          hint="Sai do estoque na confirmação."
        />
      </div>
      <div className="w-full sm:w-36">
        <TextField
          label="Dose por ha"
          inputMode="decimal"
          value={escolha?.dosePorHa ?? ""}
          onChange={(event) => onMudar(chave, { dosePorHa: event.target.value })}
          disabled={!escolha?.produtoId}
        />
      </div>
      <p className="text-sm text-ink-muted sm:w-48 sm:pb-3">
        {escolha?.produtoId && quantidade !== null
          ? `Sai do estoque: ${num(quantidade, 3)} para ${num(areaHa, 2)} ha.`
          : "A quantidade é a dose vezes a área medida pelo equipamento."}
      </p>
    </div>
  );
}

/** Sem acento, minúsculo e sem espaço nas pontas: é como dois nomes digitados em lugares
 *  diferentes conseguem ser comparados sem fingir precisão que não existe. */
function semAcento(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toLowerCase();
}

/* O vínculo da aplicação importada com um planejamento.
 *
 * É opcional de propósito: voo avulso existe, e exigir planejamento faria o operador
 * inventar um para poder registrar o que aconteceu — o oposto do que esta tela serve.
 *
 * Vincular tem consequência: o servidor põe no planejamento a área que o equipamento
 * mediu, porque o executado prevalece sobre o planejado. Por isso o número da área medida
 * aparece aqui, ao lado da escolha, e por isso nada é escolhido sozinho. */
function Planejamento({
  chave,
  escolhido,
  opcoes,
  sugerido,
  areaMedida,
  onVincular,
}: {
  chave: string;
  escolhido: string;
  opcoes: Plan[];
  sugerido: string | null;
  areaMedida: string;
  onVincular: (chave: string, planId: string) => void;
}) {
  if (opcoes.length === 0) return null;

  return (
    <div className="mt-3 flex flex-col gap-3 border-t border-line-subtle pt-3 sm:flex-row sm:items-end">
      <div className="min-w-0 flex-1">
        <Select
          label="Planejamento"
          value={escolhido}
          onChange={(valor) => onVincular(chave, valor)}
          options={opcoes.map((plano) => ({
            value: plano.id,
            label:
              `Nº ${plano.numero ?? "—"}` +
              (plano.cultura ? ` · ${plano.cultura}` : "") +
              (plano.area_ha ? ` · ${num(plano.area_ha, 2)} ha` : "") +
              (plano.id === sugerido ? " · sugerido pelo talhão" : ""),
          }))}
          placeholder="Voo sem planejamento"
          hint={
            escolhido
              ? `A área do planejamento passa a ser a medida: ${num(areaMedida, 2)} ha.`
              : "Vincular traz a dose do receituário e atualiza a área do documento."
          }
        />
      </div>
    </div>
  );
}
