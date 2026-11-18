import { useRef, useState } from "react";

import { Alert } from "../components/Alert";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader, Row } from "../components/Card";
import { Modal } from "../components/Modal";
import { TextField } from "../components/TextField";
import { agro } from "../lib/agro";
import type {
  AplicacaoConfirmada,
  RegistroDeVooLido,
  VooAuxiliar,
  VooConfirmado,
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
  const [registrado, setRegistrado] = useState<VooRegistrado | null>(null);
  const campo = useRef<HTMLInputElement>(null);

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

  function comoVoo(
    linha: { comecou_em: string; terminou_em: string; comecou_em_ajustado: string; terminou_em_ajustado: string; duracao_segundos: number; equipamento_serie: string | null; aeronave: string; piloto: string | null; lugar: string | null },
    aircraftId: string | null,
  ): VooConfirmado {
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
        /* Um voo por aplicação na chamada: o servidor reconhece pelo instante do arquivo,
         * e o que ele precisa saber é quanto tempo a aplicação levou — que já está
         * somado. O detalhe voo a voo da aplicação fica no arquivo, que o operador
         * guarda; o que entra aqui é o que vai ao documento. */
        voos: [comoVoo(aplicacao, aplicacao.aircraft_id)],
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

  /** A aeronave do voo auxiliar, achada pelo série no horímetro que o servidor montou. */
  function aeronaveDoVoo(voo: VooAuxiliar): string | null {
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
                      {num(aplicacao.volume_l, 2)} L
                      {aplicacao.volume_por_ha
                        ? ` · ${num(aplicacao.volume_por_ha, 2)} L/ha`
                        : ""}
                    </span>
                    {aplicacao.aircraft_id === null && (
                      <Badge tone="warn">sem aeronave</Badge>
                    )}
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
