import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /** Submodal: empilha acima de outro e some o fundo um pouco mais. */
  nested?: boolean;
  /** "ampla" para operação inteira dentro do diálogo — caixa, devolução, conferência.
   *  O padrão continua estreito, que é o certo para confirmar ou preencher três campos. */
  largura?: "normal" | "ampla";
  /** Trava: sem ✕, sem Esc, sem clicar fora. Para quando sair daqui não é uma opção —
   *  o ponto de venda pedindo quem está no caixa, por exemplo. A saída tem de estar no
   *  conteúdo, dita com todas as letras, e não escondida num gesto. */
  bloqueado?: boolean;
}

/* Sobreposição focada, para tarefa curta que não merece sair da tela.
 *
 * O que a faz funcionar não é a aparência: é fechar no Esc, devolver o foco a quem
 * abriu, travar a rolagem do fundo e anunciar-se como diálogo. Sem isso ela prende
 * quem navega por teclado e desaparece para quem usa leitor de tela. */
export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  nested = false,
  largura = "normal",
  bloqueado = false,
}: Props) {
  const painel = useRef<HTMLDivElement>(null);
  const anterior = useRef<HTMLElement | null>(null);

  /* O fechar mais recente, guardado fora da lista de dependências do efeito.
   *
   * Quem abre este diálogo escreve `onClose={() => setAberto(false)}`, uma função nova a
   * cada render. Se ela entrasse nas dependências, qualquer tecla digitada no formulário
   * refaria o efeito inteiro: a limpeza devolveria o foco a quem abriu e a montagem o
   * jogaria de volta no primeiro elemento do painel. No celular, foco saindo de um campo
   * de texto fecha o teclado — era preciso tocar no campo outra vez a cada letra. */
  const fechar = useRef(onClose);
  const travado = useRef(bloqueado);
  useEffect(() => {
    fechar.current = onClose;
    travado.current = bloqueado;
  });

  useEffect(() => {
    if (!open) return;

    anterior.current = document.activeElement as HTMLElement | null;
    const rolagem = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    /* Foco no primeiro campo; sem campo, no próprio painel, para o Esc funcionar.
     *
     * Botão fica fora da busca de propósito. O primeiro do painel é o X do cabeçalho, e
     * abrir um formulário com o foco no fechar obriga quem usa teclado a percorrer o
     * diálogo de trás para frente — e no celular não levanta o teclado. Em diálogo que
     * só confirma, sem campo nenhum, o foco vai para o painel e não para o botão de
     * confirmar: ação destrutiva não deve estar a um Enter distraído de distância. */
    const alvo = painel.current?.querySelector<HTMLElement>(
      "input:not([disabled]), select:not([disabled]), textarea:not([disabled])",
    );
    (alvo ?? painel.current)?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !travado.current) fechar.current();
    };
    document.addEventListener("keydown", onKey);

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = rolagem;
      anterior.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className={"fixed inset-0 flex items-end justify-center sm:items-center " + (nested ? "z-[60]" : "z-50")}>
      {bloqueado ? (
        <div
          aria-hidden="true"
          className={
            "absolute inset-0 animate-fade backdrop-blur-sm " +
            (nested ? "bg-brand-950/50" : "bg-brand-950/45")
          }
        />
      ) : (
        <button
          type="button"
          aria-label="Fechar"
          onClick={onClose}
          className={
            "absolute inset-0 animate-fade backdrop-blur-sm " +
            (nested ? "bg-brand-950/50" : "bg-brand-950/45")
          }
        />
      )}

      <div
        ref={painel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={
          "relative m-0 flex max-h-[92dvh] w-full animate-rise flex-col overflow-hidden " +
          "rounded-t-xl bg-surface shadow-lg ring-1 ring-line-subtle outline-none " +
          "sm:m-6 sm:rounded-xl " +
          (largura === "ampla" ? "sm:max-w-3xl" : "sm:max-w-lg")
        }
      >
        <header className="flex items-start justify-between gap-4 px-5 pt-5 sm:px-6 sm:pt-6">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-ink">{title}</h2>
            {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            hidden={bloqueado}
            className="-mr-1 -mt-1 flex size-9 shrink-0 items-center justify-center rounded-dk
                       text-ink-faint transition-colors duration-150 ease-dk
                       hover:bg-sunken hover:text-ink"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path
                d="m1 1 12 12M13 1 1 13"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-6 sm:py-6">{children}</div>

        {footer && (
          <footer className="border-t border-line-subtle bg-sunken px-5 py-4 sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
