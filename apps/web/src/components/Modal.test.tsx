import { useState } from "react";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "./Modal";

/* O foco do diálogo.
 *
 * Estes testes existem porque um defeito real passou despercebido: no celular, digitar
 * uma letra em qualquer diálogo fechava o teclado, e era preciso tocar no campo de novo
 * a cada caractere. A causa não estava no campo nem na tela de clientes, onde apareceu,
 * mas no `Modal` — e por isso valia para todos os diálogos de uma vez.
 *
 * O que torna o teste capaz de pegar isso é o `Formulario` abaixo guardar estado. Um
 * `Modal` montado sozinho, com `onClose` estável, passaria mesmo com o defeito de volta:
 * é justamente o pai se re-renderizando a cada tecla, com um `onClose` novo em folha,
 * que reproduz a condição. Se alguém trocar o `Formulario` por uma montagem direta, o
 * teste continua verde e deixa de proteger. */

/** Um diálogo de formulário como os de verdade: estado a cada tecla, `onClose` embutido. */
function Formulario({ aoFechar = () => {} }: { aoFechar?: (nome: string) => void }) {
  const [nome, setNome] = useState("");

  return (
    <Modal open title="Novo cliente" onClose={() => aoFechar(nome)}>
      <label htmlFor="tipo">Tipo</label>
      <select id="tipo" defaultValue="fisica">
        <option value="fisica">Pessoa física</option>
        <option value="juridica">Empresa</option>
      </select>

      <label htmlFor="nome">Nome</label>
      <input id="nome" value={nome} onChange={(evento) => setNome(evento.target.value)} />
    </Modal>
  );
}

describe("Modal", () => {
  it("abre com o foco no primeiro campo, e não no botão de fechar", () => {
    render(<Formulario />);

    // O primeiro elemento focável do painel é o ✕ do cabeçalho. Abrir ali obrigaria
    // quem usa teclado a percorrer o formulário de trás para frente, e no celular não
    // levantaria o teclado.
    expect(document.activeElement).toBe(screen.getByLabelText("Tipo"));
  });

  it("não tira o foco do campo enquanto se digita", async () => {
    const usuario = userEvent.setup();
    render(<Formulario />);

    const nome = screen.getByLabelText("Nome");
    await usuario.click(nome);

    // Uma letra bastava para o defeito aparecer; o resto confirma que não é intermitente.
    for (const letra of "Padaria") {
      await usuario.keyboard(letra);
      expect(document.activeElement).toBe(nome);
    }

    expect((nome as HTMLInputElement).value).toBe("Padaria");
  });

  it("foca o próprio painel quando não há campo nenhum", () => {
    render(
      <Modal open title="Desinstalar" onClose={() => {}}>
        <p>Isto remove o aplicativo desta empresa.</p>
      </Modal>,
    );

    // Painel, e não o botão de confirmar: ação destrutiva não deve estar a um Enter
    // distraído de distância.
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
  });

  it("o Esc chama o fechar mais recente, não o do primeiro render", async () => {
    const usuario = userEvent.setup();
    const aoFechar = vi.fn();
    render(<Formulario aoFechar={aoFechar} />);

    await usuario.click(screen.getByLabelText("Nome"));
    await usuario.keyboard("Ana");
    await usuario.keyboard("{Escape}");

    // Guardar o `onClose` fora das dependências do efeito tem um risco próprio: prender
    // a versão do primeiro render, que enxergaria o nome ainda vazio. "Ana" prova que o
    // que rodou foi o fechar de agora.
    expect(aoFechar).toHaveBeenCalledWith("Ana");
  });

  it("devolve a rolagem do fundo ao fechar", () => {
    const { rerender } = render(
      <Modal open title="Novo cliente" onClose={() => {}}>
        <p>Qualquer coisa.</p>
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("hidden");

    rerender(
      <Modal open={false} title="Novo cliente" onClose={() => {}}>
        <p>Qualquer coisa.</p>
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("");
  });
});
