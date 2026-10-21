import { useId, useState } from "react";
import type { InputHTMLAttributes } from "react";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  /** Pinta a dica como erro e marca o campo. A dica vira a explicação do problema. */
  invalid?: boolean;
  /** Acrescenta o botão de mostrar/ocultar. Ver nota abaixo. */
  revealable?: boolean;
}

export function TextField({
  label,
  hint,
  invalid = false,
  revealable = false,
  type,
  ...rest
}: Props) {
  const id = useId();
  const hintId = `${id}-hint`;
  const [revealed, setRevealed] = useState(false);

  const inputType = revealable ? (revealed ? "text" : "password") : type;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-base font-medium text-ink">
        {label}
      </label>

      <div className="relative">
        <input
          {...rest}
          id={id}
          type={inputType}
          aria-describedby={hint ? hintId : undefined}
          aria-invalid={invalid || undefined}
          className={
            "min-h-touch w-full rounded-dk border bg-surface px-4 text-lg " +
            "text-ink placeholder:text-ink-muted/70 " +
            "focus:border-brand-link focus:outline-none " +
            (invalid ? "border-danger " : "border-line ") +
            (revealable ? "pr-28" : "")
          }
        />

        {/* Mostrar a senha reduz erro de digitação, o que importa muito para o público
            deste produto — operadores de caixa e donos de loja, boa parte idosa. */}
        {revealable && (
          <button
            type="button"
            onClick={() => setRevealed((value) => !value)}
            className="absolute inset-y-0 right-2 my-1 rounded-dk px-3 text-base
                       font-medium text-brand-link hover:bg-brand-soft"
          >
            {revealed ? "Ocultar" : "Mostrar"}
          </button>
        )}
      </div>

      {/* Não é só cor: o campo recebe aria-invalid e a explicação vem escrita, porque
          cor sozinha não informa. Ver docs/BRAND.md. */}
      {hint && (
        <p id={hintId} className={invalid ? "text-base text-danger" : "text-sm text-ink-muted"}>
          {hint}
        </p>
      )}
    </div>
  );
}
