import { useId } from "react";
import type { ReactNode } from "react";

interface Props {
  label: string;
  /** O porquê da opção, embaixo do rótulo. É aqui que a regra é explicada. */
  hint?: ReactNode;
  checked: boolean;
  /** Recebe o valor, não o evento: quem chama quase sempre quer só o valor. */
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/* Opção de ligar e desligar.
 *
 * Caixa de marcar de verdade, e não um botão que imita uma: `input[type=checkbox]` já
 * chega com estado anunciado a leitor de tela, barra de espaço, e o rótulo clicável que
 * aumenta a área de toque — tudo o que um `div` com `role` teria de reimplementar, e
 * normalmente reimplementa pela metade.
 *
 * A área toda tem a altura mínima de toque, porque o alvo do produto inclui celular
 * fraco e dedo com pressa — ver `docs/BRAND.md`.
 */
export function Checkbox({ label, hint, checked, onChange, disabled = false }: Props) {
  const id = useId();
  const hintId = `${id}-hint`;

  return (
    <div className="flex min-h-touch items-start gap-3">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-describedby={hint ? hintId : undefined}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 size-5 shrink-0 cursor-pointer rounded-sm accent-action
                   disabled:cursor-not-allowed disabled:opacity-50"
      />
      {/* A dica fica **fora** do rótulo, e ligada por `aria-describedby`.
          Dentro dele, o nome acessível da caixa viraria "Sangria" seguido da explicação
          inteira — quem usa leitor de tela ouviria um parágrafo onde precisa de um
          nome, e a descrição deixaria de ser descrição. */}
      <div className="py-0.5">
        <label htmlFor={id} className="block cursor-pointer select-none text-base text-ink">
          {label}
        </label>
        {hint && (
          <span id={hintId} className="mt-0.5 block text-sm text-ink-muted">
            {hint}
          </span>
        )}
      </div>
    </div>
  );
}
