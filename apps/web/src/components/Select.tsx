import { useId } from "react";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  /** Texto da primeira opção, quando nada foi escolhido. */
  placeholder?: string;
  /** Mostrado no lugar da lista quando não há o que escolher. */
  empty?: string;
  disabled?: boolean;
}

/* Lista suspensa nativa, ao contrário dos botões grandes usados nas escolhas de duas
 * opções: estas listas crescem com o cadastro, e o seletor do próprio sistema operacional
 * é o que já funciona bem com luva e tela pequena.
 *
 * O estado vazio é parte do componente porque é onde o operador trava: uma lista vazia
 * sem explicação parece defeito do sistema. */
export function Select({
  label,
  value,
  onChange,
  options,
  placeholder = "Selecione…",
  empty,
  disabled = false,
}: Props) {
  const id = useId();

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-base font-medium text-ink">
        {label}
      </label>

      {options.length === 0 && empty !== undefined ? (
        <p className="rounded-dk border border-line bg-surface px-4 py-3 text-base text-ink-muted">
          {empty}
        </p>
      ) : (
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-touch w-full rounded-dk border border-line bg-surface px-4 text-lg text-ink focus:border-brand-link focus:outline-none"
        >
          <option value="">{placeholder}</option>
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
