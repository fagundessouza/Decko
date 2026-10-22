import { useId } from "react";

interface Props {
  label: string;
  hint?: string;
  options: { value: string; label: string }[];
  value: string;
  /** Recebe o valor, não o evento: quem chama quase sempre quer só o valor. */
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Mostrado no lugar do campo quando não há o que escolher, com a saída dita. */
  empty?: string;
}

export function Select({
  label,
  hint,
  options,
  value,
  onChange,
  placeholder,
  disabled = false,
  empty,
}: Props) {
  const id = useId();
  const hintId = `${id}-hint`;

  if (options.length === 0 && empty) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-ink">{label}</span>
        <p className="rounded-dk bg-sunken px-4 py-3 text-base text-ink-muted ring-1 ring-inset ring-line-subtle">
          {empty}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>

      {/* A seta é desenhada por nós: a nativa muda de forma em cada sistema e é o
          detalhe que entrega interface sem acabamento. */}
      <div className="relative">
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={hint ? hintId : undefined}
          className="min-h-touch w-full appearance-none rounded-dk bg-surface px-4 pr-11 text-base
                     text-ink shadow-xs ring-1 ring-line transition-shadow duration-150 ease-dk
                     hover:ring-ink-faint/40 focus:outline-none focus:ring-2 focus:ring-brand-link
                     disabled:cursor-not-allowed disabled:text-ink-faint"
        >
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-ink-faint"
        >
          <svg width="12" height="8" viewBox="0 0 12 8" fill="none">
            <path
              d="M1 1.5 6 6.5l5-5"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </div>

      {hint && (
        <p id={hintId} className="text-sm text-ink-muted">
          {hint}
        </p>
      )}
    </div>
  );
}
