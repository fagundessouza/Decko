import { useEffect, useState } from "react";

import { TextField } from "../components/TextField";
import { Wizard } from "../components/Wizard";
import { agro } from "../lib/agro";
import type { AgroClient, AgroProperty, Plan } from "../lib/agro";
import { todayLocal } from "../lib/format";

const STEPS = ["Onde foi a aplicação", "O que foi aplicado", "Limites da aplicação"];

/* As mesmas opções impressas no talão, na mesma ordem. Texto livre aqui faria o operador
 * adivinhar a grafia que o sistema aceita, e o erro que voltava era o nome interno do
 * campo — ilegível para quem está no campo. */
const CULTURAS = [
  { value: "pastagens", label: "Pastagens" },
  { value: "cana_de_acucar", label: "Cana de Açúcar" },
  { value: "cafe", label: "Café" },
  { value: "milho", label: "Milho" },
  { value: "citrus", label: "Citrus" },
  { value: "eucalipto", label: "Eucalipto" },
  { value: "soja", label: "Soja" },
  { value: "outras", label: "Outras" },
];

interface Props {
  onCancel: () => void;
  onCreated: (plan: Plan) => void;
}

export function NewPlanWizard({ onCancel, onCreated }: Props) {
  const [step, setStep] = useState(0);
  const [clients, setClients] = useState<AgroClient[]>([]);
  const [properties, setProperties] = useState<AgroProperty[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [clientId, setClientId] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [dataAplicacao, setDataAplicacao] = useState(todayLocal);
  const [cultura, setCultura] = useState("");
  const [culturaOutras, setCulturaOutras] = useState("");
  const [areaHa, setAreaHa] = useState("");
  const [ventoMax, setVentoMax] = useState("10");
  const [temperaturaMax, setTemperaturaMax] = useState("30");
  const [umidadeMin, setUmidadeMin] = useState("50");

  useEffect(() => {
    Promise.all([agro.listClients(), agro.listProperties()])
      .then(([loadedClients, loadedProperties]) => {
        setClients(loadedClients);
        setProperties(loadedProperties);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, []);

  const propertiesOfClient = properties.filter((p) => p.client_id === clientId);

  function back() {
    setError(null);
    if (step === 0) onCancel();
    else setStep((value) => value - 1);
  }

  async function next() {
    setError(null);
    if (step < STEPS.length - 1) {
      setStep((value) => value + 1);
      return;
    }

    setBusy(true);
    try {
      const plan = await agro.createPlan({
        client_id: clientId,
        property_id: propertyId,
        data_aplicacao: dataAplicacao || null,
        cultura: cultura || null,
        cultura_outras_texto: cultura === "outras" ? culturaOutras || null : null,
        area_ha: areaHa ? Number(areaHa) : null,
        param_velocidade_vento_max_kmh: ventoMax ? Number(ventoMax) : null,
        param_temperatura_maxima_c: temperaturaMax ? Number(temperaturaMax) : null,
        param_umidade_relativa_min_pct: umidadeMin ? Number(umidadeMin) : null,
      });
      onCreated(plan);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar.");
    } finally {
      setBusy(false);
    }
  }

  const blocked = step === 0 && (!clientId || !propertyId);

  return (
    <div className="mx-auto w-full max-w-xl px-6 py-8">
      <Wizard
        steps={STEPS}
        current={step}
        onBack={back}
        onNext={next}
        nextLabel="Criar planejamento"
        nextDisabled={blocked}
        busy={busy}
      >
        {step === 0 && (
          <>
            <Select
              label="Contratante"
              value={clientId}
              onChange={(value) => {
                setClientId(value);
                setPropertyId("");
              }}
              options={clients.map((c) => ({ value: c.id, label: c.nome }))}
              empty="Nenhum contratante cadastrado ainda."
            />
            <Select
              label="Propriedade"
              value={propertyId}
              onChange={setPropertyId}
              options={propertiesOfClient.map((p) => ({
                value: p.id,
                label: `${p.nome} — ${p.municipio}/${p.uf}`,
              }))}
              empty={
                clientId
                  ? "Este contratante não tem propriedade cadastrada."
                  : "Escolha o contratante primeiro."
              }
            />
            <TextField
              label="Data da aplicação"
              type="date"
              value={dataAplicacao}
              onChange={(e) => setDataAplicacao(e.target.value)}
            />
          </>
        )}

        {step === 1 && (
          <>
            <Select
              label="Cultura"
              value={cultura}
              onChange={setCultura}
              options={CULTURAS}
              empty=""
            />
            {cultura === "outras" && (
              <TextField
                label="Qual cultura?"
                value={culturaOutras}
                onChange={(e) => setCulturaOutras(e.target.value)}
              />
            )}
            <TextField
              label="Tamanho da área (hectares)"
              type="number"
              inputMode="decimal"
              value={areaHa}
              onChange={(e) => setAreaHa(e.target.value)}
            />
          </>
        )}

        {step === 2 && (
          <>
            <p className="rounded-dk bg-brand-soft px-4 py-3 text-base text-ink">
              São os limites que o responsável técnico definiu. O sistema avisa quando a
              condição no campo passar deles.
            </p>
            <TextField
              label="Vento máximo (km/h)"
              hint="Acima disso há risco de deriva para a lavoura vizinha."
              type="number"
              inputMode="decimal"
              value={ventoMax}
              onChange={(e) => setVentoMax(e.target.value)}
            />
            <TextField
              label="Temperatura máxima (°C)"
              type="number"
              inputMode="decimal"
              value={temperaturaMax}
              onChange={(e) => setTemperaturaMax(e.target.value)}
            />
            <TextField
              label="Umidade relativa mínima (%)"
              type="number"
              inputMode="decimal"
              value={umidadeMin}
              onChange={(e) => setUmidadeMin(e.target.value)}
            />
          </>
        )}

        {error && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-dk bg-danger-soft px-4 py-3 text-base text-danger"
          >
            <span aria-hidden="true" className="font-bold">
              !
            </span>
            {error}
          </p>
        )}
      </Wizard>
    </div>
  );
}

interface SelectProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  empty: string;
}

function Select({ label, value, onChange, options, empty }: SelectProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-base font-medium text-ink">{label}</label>
      {options.length === 0 ? (
        <p className="rounded-dk border border-line bg-surface px-4 py-3 text-base text-ink-muted">
          {empty}
        </p>
      ) : (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink"
        >
          <option value="">Selecione…</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
