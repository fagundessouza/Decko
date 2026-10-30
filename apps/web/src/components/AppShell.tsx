import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ThemeToggle } from "./ThemeToggle";

export interface NavItem {
  key: string;
  label: string;
  description?: string;
  icon: ReactNode;
  onSelect: () => void;
}

interface Props {
  tenantName: string;
  userName: string;
  items: NavItem[];
  activeKey: string;
  onHome: () => void;
  onSignOut: () => void;
  /** Abre a troca de empresa. Ausente quando a sessão não pode trocar. */
  onSwitchCompany?: () => void;
  children: ReactNode;
}

/* Navegação lateral em tela larga, gaveta no celular.
 *
 * Antes havia só uma barra fina no topo e uma coluna estreita centralizada: no desktop
 * isso é um layout de celular esticado, com a área útil vazia. O alvo do produto inclui
 * o computador do caixa, então a tela larga precisa de desenho próprio, não de sobra. */
export function AppShell({
  tenantName,
  userName,
  items,
  activeKey,
  onHome,
  onSignOut,
  onSwitchCompany,
  children,
}: Props) {
  const [drawer, setDrawer] = useState(false);

  // Fechar com Esc é o que se espera de qualquer sobreposição; sem isso ela prende quem
  // navega por teclado.
  useEffect(() => {
    if (!drawer) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawer(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawer]);

  const nav = (
    <nav className="flex flex-1 flex-col gap-1 p-3">
      {items.map((item) => {
        const active = item.key === activeKey;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => {
              item.onSelect();
              setDrawer(false);
            }}
            aria-current={active ? "page" : undefined}
            className={
              "flex min-h-touch items-center gap-3 rounded-dk px-3 text-left text-base " +
              "transition-colors duration-150 ease-dk " +
              (active
                ? "bg-white/10 font-semibold text-white"
                : "text-white/70 hover:bg-white/5 hover:text-white")
            }
          >
            <span aria-hidden="true" className="shrink-0 text-lg">
              {item.icon}
            </span>
            {item.label}
          </button>
        );
      })}
    </nav>
  );

  const identity = (
    <button type="button" onClick={onHome} className="block w-full px-5 py-5 text-left">
      <p className="text-xl font-bold tracking-tight text-white">Decko</p>
      <p className="mt-0.5 truncate text-sm text-white/60">{tenantName}</p>
    </button>
  );

  const footer = (
    <div className="border-t border-white/10 p-3">
      <div className="px-3 py-2">
        <p className="truncate text-sm font-medium text-white/90">{userName}</p>
      </div>
      <div className="mt-1 flex flex-col gap-1">
        <ThemeToggle onDark />
        {onSwitchCompany && (
          <button
            type="button"
            onClick={onSwitchCompany}
            className="min-h-touch rounded-dk px-3 text-left text-base text-white/70 hover:bg-white/5 hover:text-white"
          >
            Trocar de empresa
          </button>
        )}
        <button
          type="button"
          onClick={onSignOut}
          className="min-h-touch rounded-dk px-3 text-left text-base text-white/70 hover:bg-white/5 hover:text-white"
        >
          Sair
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh bg-bg lg:flex">
      {/* Lateral fixa a partir de 1024px. */}
      <aside className="hidden w-64 shrink-0 flex-col bg-brand-deep lg:flex lg:h-dvh lg:sticky lg:top-0">
        {identity}
        {nav}
        {footer}
      </aside>

      {/* Barra do celular. */}
      <header className="flex items-center justify-between gap-3 bg-brand-deep px-4 py-3 lg:hidden">
        <button type="button" onClick={onHome} className="min-w-0 text-left">
          <p className="text-lg font-bold tracking-tight text-white">Decko</p>
          <p className="truncate text-xs text-white/60">{tenantName}</p>
        </button>
        <button
          type="button"
          onClick={() => setDrawer(true)}
          aria-label="Abrir menu"
          aria-expanded={drawer}
          className="flex size-touch items-center justify-center rounded-dk text-white hover:bg-white/10"
        >
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
            <path
              d="M3 6h16M3 11h16M3 16h16"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>

      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Fechar menu"
            onClick={() => setDrawer(false)}
            className="absolute inset-0 animate-fade bg-brand-950/60 backdrop-blur-sm"
          />
          <div className="absolute inset-y-0 right-0 flex w-72 animate-rise flex-col bg-brand-deep shadow-lg">
            {identity}
            {nav}
            {footer}
          </div>
        </div>
      )}

      <main className="flex-1">{children}</main>
    </div>
  );
}

/* Largura de leitura. Formulário fica estreito; listagem respira mais. */
export function Page({
  children,
  wide = false,
}: {
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div
      className={
        "mx-auto w-full px-5 py-8 sm:px-8 sm:py-10 " + (wide ? "max-w-5xl" : "max-w-2xl")
      }
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
  onBack,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  onBack?: () => void;
}) {
  return (
    <header className="mb-8">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="mb-3 inline-flex min-h-touch items-center gap-1.5 text-sm font-medium text-brand-link hover:underline"
        >
          <span aria-hidden="true">←</span> Voltar
        </button>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
          {description && (
            <p className="mt-2 max-w-prose text-base text-ink-muted">{description}</p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </header>
  );
}
