import { useEffect, useRef, useState } from "react";

/** Uma linha do traço: pontos numa caixa de 0 a 1. */
export type Linha = [number, number][];

interface Props {
  onChange: (traco: Linha[]) => void;
  disabled?: boolean;
}

/* Onde se assina com o dedo.
 *
 * Usa eventos de ponteiro, e não de toque ou de mouse: é o mesmo código para dedo,
 * caneta e mouse, que é exatamente o caso aqui — o produtor assina no celular do
 * agrônomo, e o agrônomo confere no computador.
 *
 * O traço sai normalizado de 0 a 1. A tela que assinou não entra no documento: o mesmo
 * rabisco feito num celular estreito e num tablet grande precisa imprimir igual. */
export function SignaturePad({ onChange, disabled = false }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const desenhando = useRef(false);

  // Redesenha sempre que o traço muda — inclusive ao limpar.
  useEffect(() => {
    const elemento = canvas.current;
    const contexto = elemento?.getContext("2d");
    if (!elemento || !contexto) return;

    // Densidade do aparelho: sem isto o traço sai serrilhado no celular.
    const escala = window.devicePixelRatio || 1;
    const { width, height } = elemento.getBoundingClientRect();
    elemento.width = width * escala;
    elemento.height = height * escala;
    contexto.scale(escala, escala);

    contexto.clearRect(0, 0, width, height);
    contexto.lineWidth = 2;
    contexto.lineCap = "round";
    contexto.lineJoin = "round";
    contexto.strokeStyle = getComputedStyle(elemento).color;

    for (const linha of linhas) {
      if (linha.length < 2) continue;
      contexto.beginPath();
      linha.forEach(([x, y], indice) => {
        const ponto: [number, number] = [x * width, y * height];
        if (indice === 0) contexto.moveTo(...ponto);
        else contexto.lineTo(...ponto);
      });
      contexto.stroke();
    }
  }, [linhas]);

  function posicao(evento: React.PointerEvent<HTMLCanvasElement>): [number, number] {
    const caixa = evento.currentTarget.getBoundingClientRect();
    return [
      Math.min(Math.max((evento.clientX - caixa.left) / caixa.width, 0), 1),
      Math.min(Math.max((evento.clientY - caixa.top) / caixa.height, 0), 1),
    ];
  }

  function comecar(evento: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    // Captura o ponteiro: sem isto, arrastar para fora do quadro corta o traço no meio.
    evento.currentTarget.setPointerCapture(evento.pointerId);
    desenhando.current = true;
    setLinhas((atual) => [...atual, [posicao(evento)]]);
  }

  function seguir(evento: React.PointerEvent<HTMLCanvasElement>) {
    if (!desenhando.current) return;
    setLinhas((atual) => {
      const copia = [...atual];
      copia[copia.length - 1] = [...copia[copia.length - 1], posicao(evento)];
      return copia;
    });
  }

  function terminar() {
    if (!desenhando.current) return;
    desenhando.current = false;
    setLinhas((atual) => {
      onChange(atual);
      return atual;
    });
  }

  function limpar() {
    setLinhas([]);
    onChange([]);
  }

  return (
    <div className="flex flex-col gap-2">
      <canvas
        ref={canvas}
        // `touch-none` é o que impede a página de rolar enquanto o dedo desenha.
        className="h-40 w-full touch-none rounded-dk bg-surface text-ink ring-1 ring-line
                   disabled:opacity-60"
        onPointerDown={comecar}
        onPointerMove={seguir}
        onPointerUp={terminar}
        onPointerCancel={terminar}
        // Sem rótulo acessível o quadro é um retângulo mudo para quem usa leitor de tela.
        role="img"
        aria-label="Quadro de assinatura. Desenhe com o dedo, a caneta ou o mouse."
      />

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-ink-faint">Assine no quadro acima.</p>
        <button
          type="button"
          onClick={limpar}
          disabled={disabled || linhas.length === 0}
          className="rounded-dk px-3 py-1 text-sm font-medium text-ink-muted
                     transition-colors duration-150 ease-dk hover:bg-sunken hover:text-ink
                     disabled:cursor-not-allowed disabled:opacity-50"
        >
          Limpar
        </button>
      </div>
    </div>
  );
}
