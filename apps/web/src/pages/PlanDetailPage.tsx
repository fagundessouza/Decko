import { useEffect, useRef, useState } from "react";

import { Page, PageHeader } from "../components/AppShell";
import { Button } from "../components/Button";
import { PlanProducts } from "../components/PlanProducts";
import { TextField } from "../components/TextField";
import { agro, currentPosition } from "../lib/agro";
import type { CroquiLido, Plan, WeatherReading } from "../lib/agro";
import { dateBr, nowLocalTime, num, periodoOfNow, todayLocal, ventoBr } from "../lib/format";

const PERIODOS = [
  { value: "matutino", label: "Manhã" },
  { value: "vespertino", label: "Tarde" },
];
const MOMENTOS = [
  { value: "inicio", label: "Início" },
  { value: "final", label: "Fim" },
];

interface Props {
  plan: Plan;
  onBack: () => void;
}

export function PlanDetailPage({ plan, onBack }: Props) {
  const [readings, setReadings] = useState<WeatherReading[]>([]);
  const [alerts, setAlerts] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [usedGps, setUsedGps] = useState(false);

  const [data, setData] = useState(plan.data_aplicacao ?? todayLocal());
  const [periodo, setPeriodo] = useState<string>(periodoOfNow);
  const [momento, setMomento] = useState("inicio");
  const [hora, setHora] = useState(nowLocalTime);

  useEffect(() => {
    agro.listWeather(plan.id).then(setReadings).catch(() => undefined);
  }, [plan.id]);

  // A API devolve ordenado por data, período e momento; a última é a mais recente.
  const lastReading = readings.at(-1);

  async function capture() {
    setBusy(true);
    setError(null);
    setAlerts([]);
    setUsedGps(false);

    let position: { latitude: number; longitude: number } | undefined;
    try {
      position = await currentPosition();
      setUsedGps(true);
    } catch {
      // Sem GPS o servidor recai para a coordenada do planejamento ou da propriedade;
      // bloquear aqui impediria o registro justamente onde o sinal é pior.
      position = undefined;
    }

    try {
      const result = await agro.captureWeather(plan.id, {
        data,
        periodo,
        momento,
        hora,
        ...(position ?? {}),
      });
      setAlerts(result.alertas);
      setReadings(await agro.listWeather(plan.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível registrar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page wide>
      <PageHeader
        title={`Planejamento nº ${plan.numero}`}
        description={`Limites: vento ${num(plan.param_velocidade_vento_max_kmh)} km/h, temperatura ${num(plan.param_temperatura_maxima_c)} °C, umidade mínima ${num(plan.param_umidade_relativa_min_pct, 0)}%`}
        onBack={onBack}
      />

      <CroquiImport planId={plan.id} />

      <section className="mt-8 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle p-5">
        <h2 className="text-lg font-semibold text-ink">Registrar condição do tempo</h2>
        <p className="mt-1 text-base text-ink-muted">
          O sistema busca temperatura, umidade e vento do local e do horário informados.
        </p>

        <div className="mt-5 flex flex-col gap-4">
          <TextField
            label="Data"
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
          />
          <TextField
            label="Hora"
            type="time"
            value={hora}
            onChange={(e) => setHora(e.target.value)}
          />
          <Choice label="Período" value={periodo} onChange={setPeriodo} options={PERIODOS} />
          <Choice label="Momento" value={momento} onChange={setMomento} options={MOMENTOS} />

          <Button onClick={capture} loading={busy}>
            {busy ? "Buscando…" : "Registrar condição"}
          </Button>
        </div>

        {usedGps && !busy && (
          <p className="mt-3 text-base text-ink-muted">
            Localização obtida pelo aparelho.
          </p>
        )}

        {/* O alerta de deriva precisa ser impossível de ignorar: é o que evita o processo
            judicial, não apenas documentá-lo. */}
        {alerts.length > 0 && (
          <div
            role="alert"
            className="mt-5 rounded-dk border-2 border-warn bg-warn-soft px-4 py-4"
          >
            <p className="flex items-center gap-2 text-lg font-bold text-ink">
              <span aria-hidden="true">⚠</span>
              Condição fora do planejado
            </p>
            <ul className="mt-2 flex flex-col gap-1.5">
              {alerts.map((alert) => (
                <li key={alert} className="text-base text-ink">
                  {alert}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-base font-medium text-ink">
              Avalie adiar a aplicação. O registro fica guardado de qualquer forma.
            </p>
          </div>
        )}

        {/* O estado vem da última leitura gravada, não da captura desta sessão. Antes
            dependia da variável de alertas, que começa vazia: ao abrir a tela o sistema
            afirmava "dentro dos limites" mesmo com a última leitura violando o
            planejamento. Numa tela que existe para evitar deriva, essa é a falha errada
            de se ter. */}
        {alerts.length === 0 && !busy && lastReading?.violou_parametro && (
          <p className="mt-5 rounded-dk border-2 border-warn bg-warn-soft px-4 py-3 text-base font-medium text-ink">
            <span aria-hidden="true">⚠ </span>
            A última leitura registrada está fora dos limites planejados.
          </p>
        )}

        {alerts.length === 0 && !busy && lastReading && !lastReading.violou_parametro && (
          <p className="mt-5 rounded-dk bg-action-soft px-4 py-3 text-base text-ink">
            Última leitura dentro dos limites planejados.
          </p>
        )}

        {error && (
          <p
            role="alert"
            className="mt-5 flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger"
          >
            <span aria-hidden="true" className="font-bold">
              !
            </span>
            {error}
          </p>
        )}
      </section>

      <section className="mt-6 rounded-lg bg-surface shadow-sm ring-1 ring-inset ring-line-subtle p-5">
        <h2 className="text-lg font-semibold text-ink">
          Leituras registradas ({readings.length})
        </h2>
        {readings.length === 0 ? (
          <p className="mt-2 text-base text-ink-muted">
            Nenhuma ainda. Registre a condição no início e no fim de cada turno.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {readings.map((reading) => (
              <li
                key={reading.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3 last:border-0"
              >
                <div>
                  <p className="text-base font-medium text-ink">
                    {dateBr(reading.data)} · {reading.hora?.slice(0, 5)} ·{" "}
                    {reading.periodo === "matutino" ? "Manhã" : "Tarde"}{" "}
                    {reading.momento === "inicio" ? "início" : "fim"}
                  </p>
                  <p className="text-base text-ink-muted">
                    {num(reading.temperatura_c)} °C · {num(reading.umidade_relativa_pct, 0)}%
                    · {num(reading.velocidade_vento_kmh)} km/h
                    {reading.direcao_vento_graus !== null &&
                      ` · vento de ${ventoBr(reading.direcao_vento_graus)}`}
                  </p>
                </div>
                {reading.violou_parametro && (
                  <span className="rounded-dk bg-warn-soft px-3 py-1 text-sm font-medium text-ink">
                    ⚠ Fora do limite
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <PlanProducts planId={plan.id} prescriptionId={plan.prescription_id} />

      <div className="mt-6">
        <Button
          variant="ghost"
          onClick={() => {
            void agro.downloadPdf(plan.id, plan.numero);
          }}
        >
          Baixar relatório em PDF
        </Button>
      </div>
    </Page>
  );
}

interface ChoiceProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}

/* Botões grandes em vez de lista suspensa: o operador acerta com luva, sem mirar. */
function Choice({ label, value, onChange, options }: ChoiceProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-base font-medium text-ink">{label}</span>
      <div className="flex gap-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={value === option.value}
            className={
              "min-h-touch flex-1 rounded-dk border text-lg font-medium " +
              (value === option.value
                ? "border-action bg-action-soft text-ink"
                : "border-line bg-surface text-ink-muted")
            }
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}


/* Importação do croqui a partir do arquivo do voo.
 *
 * A área e a direção que saem daqui são **sugestão**: o documento leva o que o agrônomo
 * declarou, e um desenho não muda campo de documento legal. Por isso elas aparecem como
 * texto ao lado, e não preenchem nada sozinhas. */
function CroquiImport({ planId }: { planId: string }) {
  const arquivo = useRef<HTMLInputElement>(null);
  const [lido, setLido] = useState<CroquiLido | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function importar(file: File) {
    setBusy(true);
    setErro(null);
    try {
      // KMZ é zip: vai em base64, com o campo dizendo isso. KML vai como texto.
      const kmz = file.name.toLowerCase().endsWith(".kmz");
      const conteudo = kmz
        ? btoa(String.fromCharCode(...new Uint8Array(await file.arrayBuffer())))
        : await file.text();

      setLido(
        await agro.importarCroqui(planId, { kml: conteudo, base64: kmz, origem: file.name }),
      );
    } catch (cause) {
      setErro(
        cause instanceof Error && cause.message
          ? cause.message
          : "Não foi possível ler o arquivo.",
      );
    } finally {
      setBusy(false);
      if (arquivo.current) arquivo.current.value = "";
    }
  }

  return (
    <section className="mt-8 rounded-lg bg-surface p-5 shadow-sm ring-1 ring-inset ring-line-subtle">
      <h2 className="text-lg font-semibold text-ink">Croqui da área</h2>
      <p className="mt-1 text-base text-ink-muted">
        Envie a rota do voo exportada pelo aplicativo do drone, em KML ou KMZ. Ela vira o
        desenho do croqui no documento, com a direção dos tiros e a seta do vento.
      </p>

      <input
        ref={arquivo}
        type="file"
        accept=".kml,.kmz,application/vnd.google-earth.kml+xml,application/vnd.google-earth.kmz"
        className="hidden"
        onChange={(event) => {
          const escolhido = event.target.files?.[0];
          if (escolhido) void importar(escolhido);
        }}
      />

      <div className="mt-5 sm:max-w-xs">
        <Button variant="secondary" loading={busy} onClick={() => arquivo.current?.click()}>
          Escolher arquivo do voo
        </Button>
      </div>

      {erro && (
        <p className="mt-4 text-base text-danger">
          <span aria-hidden="true">⚠ </span>
          {erro}
        </p>
      )}

      {lido && (
        <div className="mt-4 text-base text-ink-muted">
          <p className="font-medium text-ink">Croqui importado.</p>
          <p>
            {lido.tem_limite ? "Contorno da área" : "Sem contorno"} ·{" "}
            {lido.faixas === 1 ? "1 faixa de voo" : `${lido.faixas} faixas de voo`}
          </p>
          {/* Sugestão, e dito como tal: quem declara a área é quem assina. */}
          {lido.area_sugerida_ha && (
            <p className="mt-2">
              Pelo desenho, a área dá {num(lido.area_sugerida_ha)} ha — confira com a que
              você declarou.
            </p>
          )}
          {lido.direcao_tiros_graus && (
            <p>Direção dos tiros: {ventoBr(lido.direcao_tiros_graus)}.</p>
          )}
        </div>
      )}
    </section>
  );
}
