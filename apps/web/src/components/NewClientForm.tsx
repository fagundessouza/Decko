import { useState } from "react";

import type { AgroClient, AgroProperty } from "../lib/agro";
import { agro, currentPosition } from "../lib/agro";
import { documentProblem, stripMask } from "../lib/documents";
import { Button } from "./Button";
import { TextField } from "./TextField";

interface ClientProps {
  onCreated: (client: AgroClient) => void;
  onCancel: () => void;
}

/* Cadastro de contratante onde ele é escolhido.
 *
 * Antes disto o wizard dizia "Nenhum contratante cadastrado ainda" e parava ali: os
 * cadastros existiam só na API, de modo que uma empresa recém-criada não conseguia emitir
 * o primeiro planejamento sem alguém chamar a API por fora. */
export function NewClientForm({ onCreated, onCancel }: ClientProps) {
  const [nome, setNome] = useState("");
  const [documento, setDocumento] = useState("");
  const [telefone, setTelefone] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const limpo = stripMask(documento);
  // Só reclama depois que o campo tem conteúdo: avisar "inválido" enquanto a pessoa
  // ainda digita o primeiro algarismo é ruído, não ajuda.
  const problema = documento.trim() === "" ? null : documentProblem(documento);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await agro.createClient({
          nome: nome.trim(),
          cpf_cnpj: limpo,
          telefone: telefone.trim() || null,
          email: email.trim() || null,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível cadastrar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-dk ring-1 ring-inset ring-line bg-brand-soft/40 p-4">
      <p className="text-base font-medium text-ink">Novo contratante</p>

      <TextField
        label="Nome ou razão social"
        value={nome}
        onChange={(event) => setNome(event.target.value)}
      />
      {/* A máscara é digitada por quem cadastra e removida antes de gravar: o documento é
          copiado do papel do jeito que está impresso lá, com ponto e barra. */}
      {/* A conferência do dígito verificador acontece aqui e no servidor. Aqui porque o
          aparelho no campo costuma estar sem sinal, e descobrir o erro de digitação só
          na volta da chamada é tarde: a pessoa já guardou o papel. */}
      <TextField
        label="CPF ou CNPJ"
        hint={problema ?? "Pode digitar com ponto e barra."}
        invalid={problema !== null}
        inputMode="text"
        autoCapitalize="characters"
        value={documento}
        onChange={(event) => setDocumento(event.target.value)}
      />
      <TextField
        label="Telefone"
        type="tel"
        inputMode="tel"
        value={telefone}
        onChange={(event) => setTelefone(event.target.value)}
      />
      <TextField
        label="E-mail"
        type="email"
        inputMode="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />

      {error && (
        <p role="alert" className="rounded-dk bg-danger-soft px-4 py-3 text-base text-danger">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row-reverse">
        <Button
          disabled={nome.trim() === "" || problema !== null}
          loading={busy}
          onClick={() => void save()}
        >
          Cadastrar contratante
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

interface PropertyProps {
  clientId: string;
  onCreated: (property: AgroProperty) => void;
  onCancel: () => void;
}

export function NewPropertyForm({ clientId, onCreated, onCancel }: PropertyProps) {
  const [nome, setNome] = useState("");
  const [municipio, setMunicipio] = useState("");
  const [uf, setUf] = useState("");
  const [coords, setCoords] = useState<{ latitude: number; longitude: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);

  async function locate() {
    setLocating(true);
    setError(null);
    try {
      setCoords(await currentPosition());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível localizar.");
    } finally {
      setLocating(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await agro.createProperty({
          client_id: clientId,
          nome: nome.trim(),
          municipio: municipio.trim(),
          uf: uf.trim().toUpperCase(),
          latitude: coords?.latitude ?? null,
          longitude: coords?.longitude ?? null,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível cadastrar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-dk ring-1 ring-inset ring-line bg-brand-soft/40 p-4">
      <p className="text-base font-medium text-ink">Nova propriedade</p>

      <TextField
        label="Nome da propriedade"
        value={nome}
        onChange={(event) => setNome(event.target.value)}
      />
      <TextField
        label="Município"
        value={municipio}
        onChange={(event) => setMunicipio(event.target.value)}
      />
      <TextField
        label="UF"
        maxLength={2}
        autoCapitalize="characters"
        value={uf}
        onChange={(event) => setUf(event.target.value.toUpperCase())}
      />

      {/* A coordenada da propriedade é o que o sistema usa para buscar o tempo quando o
          aparelho não informa a posição. Capturá-la aqui aproveita que quem cadastra
          costuma estar na propriedade; digitá-la depois, de memória, não aconteceria. */}
      <div className="flex flex-col gap-2">
        <Button variant="ghost" onClick={() => void locate()} loading={locating}>
          {coords ? "Atualizar localização" : "Usar a localização daqui"}
        </Button>
        <p className="text-base text-ink-muted">
          {coords
            ? `Coordenada guardada: ${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`
            : "Sem coordenada, o tempo é buscado pela posição informada na captura."}
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-dk bg-danger-soft px-4 py-3 text-base text-danger">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row-reverse">
        <Button
          disabled={nome.trim() === "" || municipio.trim() === "" || uf.trim().length !== 2}
          loading={busy}
          onClick={() => void save()}
        >
          Cadastrar propriedade
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
