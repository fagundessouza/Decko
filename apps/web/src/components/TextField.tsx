import { useId, useState } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  /** Pinta a dica como erro e marca o campo. A dica vira a explicação do problema. */
  invalid?: boolean;
  /** Acrescenta o botão de mostrar/ocultar. Ver nota abaixo. */
  revealable?: boolean;
  /** Texto fixo à esquerda, como "R$". Evita repetir a unidade dentro do valor.
   *  Não se chama `prefix` porque esse é um atributo HTML e o tipo colidiria. */
  leading?: ReactNode;
}

export function TextField({
  label,
  hint,
  invalid = false,
  revealable = false,
  leading,
  type,
  className = "",
  ...rest
}: Props) {
  const id = useId();
  const hintId = `${id}-hint`;
  const [revealed, setRevealed] = useState(false);

  const inputType = revealable ? (revealed ? "text" : "password") : type;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>

      <div
        className={
          "flex min-h-touch items-center gap-2 rounded-dk bg-surface px-4 shadow-xs " +
          "ring-1 transition-shadow duration-150 ease-dk " +
          "focus-within:ring-2 " +
          (invalid
            ? "ring-danger focus-within:ring-danger "
            : "ring-line hover:ring-ink-faint/40 focus-within:ring-brand-link ")
        }
      >
        {leading && (
          <span aria-hidden="true" className="shrink-0 text-base text-ink-faint">
            {leading}
          </span>
        )}

        <input
          {...rest}
          id={id}
          type={inputType}
          aria-describedby={hint ? hintId : undefined}
          aria-invalid={invalid || undefined}
          className={
            "min-w-0 flex-1 bg-transparent py-2 text-base text-ink outline-none " +
            "placeholder:text-ink-faint focus:shadow-none " +
            className
          }
        />

        {/* Mostrar a senha reduz erro de digitação, o que importa muito para o público
            deste produto — operadores de caixa e donos de loja, boa parte idosa. */}
        {revealable && (
          <button
            type="button"
            onClick={() => setRevealed((value) => !value)}
            className="shrink-0 rounded-sm px-2 py-1 text-sm font-medium text-brand-link hover:bg-brand-soft"
          >
            {revealed ? "Ocultar" : "Mostrar"}
          </button>
        )}
      </div>

      {/* Não é só cor: o campo recebe aria-invalid e a explicação vem escrita, porque
          cor sozinha não informa. Ver docs/BRAND.md. */}
      {hint && (
        <p id={hintId} className={invalid ? "text-sm text-danger" : "text-sm text-ink-muted"}>
          {hint}
        </p>
      )}
    </div>
  );
}
