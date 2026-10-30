import { useEffect, useState } from "react";

import { tenant } from "../lib/api";
import type { TenantProfile } from "../lib/api";
import { brl, num } from "../lib/format";
import { FORMAS } from "../lib/pdv";
import type { Venda } from "../lib/pdv";
import { recibo as preferencia } from "../lib/session";
import type { LarguraDoRecibo } from "../lib/session";

interface Props {
  venda: Venda;
  /** Vem da sessão, então existe sempre — o resto do cabeçalho é opcional. */
  empresa: string;
}

function quando(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function cnpjBr(digitos: string): string {
  if (digitos.length !== 14) return digitos;
  return digitos.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

/* O recibo que sai na impressora térmica.
 *
 * **Não é documento fiscal, e o papel diz isso.** Onde a nota é exigida, este recibo não a
 * substitui — ver docs/discovery/comercial-emissao-fiscal.md. A linha impressa existe para
 * que ninguém, nem o lojista nem o cliente, confunda os dois.
 *
 * Imprime pela impressora do sistema operacional, que é como a térmica de balcão aparece no
 * Windows. ESC/POS direto exigiria agente local ou WebUSB, e não resolveria nada que isto
 * não resolva.
 *
 * Os números vêm prontos do servidor, como tudo que é dinheiro no PDV (ADR 0008, decisão 3):
 * aqui só se desenha. */
export function Recibo({ venda, empresa }: Props) {
  const [perfil, setPerfil] = useState<TenantProfile | null>(null);

  useEffect(() => {
    // Quem opera o caixa pode não ter permissão de ler o cadastro da empresa. O recibo sai
    // do mesmo jeito, com o nome que a sessão já trouxe — menos cabeçalho, não menos venda.
    tenant
      .read()
      .then(setPerfil)
      .catch(() => setPerfil(null));
  }, []);

  const pagamentos = venda.pagamentos.map((pagamento) => ({
    label: FORMAS.find((forma) => forma.valor === pagamento.forma)?.label ?? pagamento.forma,
    valor: pagamento.valor,
  }));

  return (
    <div className="dk-recibo" aria-hidden="true">
      <header className="dk-recibo__centro">
        <p className="dk-recibo__forte">{empresa}</p>
        {perfil?.cnpj && <p>CNPJ {cnpjBr(perfil.cnpj)}</p>}
        {perfil?.inscricao_estadual && <p>IE {perfil.inscricao_estadual}</p>}
      </header>

      <hr className="dk-recibo__regua" />

      <p>
        Venda {venda.numero ?? "—"} · {quando(venda.fechada_em ?? venda.aberta_em)}
      </p>
      {venda.cliente_nome && <p>Cliente: {venda.cliente_nome}</p>}

      <hr className="dk-recibo__regua" />

      <table className="dk-recibo__itens">
        <tbody>
          {venda.itens.map((item) => (
            <tr key={item.id}>
              <td colSpan={2}>
                <span className="dk-recibo__nome">{item.descricao}</span>
                <span className="dk-recibo__linha">
                  <span>
                    {num(item.quantidade)} x {brl(item.preco_unitario)}
                  </span>
                  <span>{brl(item.total)}</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <hr className="dk-recibo__regua" />

      <p className="dk-recibo__linha">
        <span>Subtotal</span>
        <span>{brl(venda.soma_dos_itens)}</span>
      </p>
      {Number(venda.desconto) > 0 && (
        <p className="dk-recibo__linha">
          <span>Desconto</span>
          <span>-{brl(venda.desconto)}</span>
        </p>
      )}
      <p className="dk-recibo__linha dk-recibo__forte">
        <span>TOTAL</span>
        <span>{brl(venda.total)}</span>
      </p>

      {pagamentos.map((pagamento, indice) => (
        <p className="dk-recibo__linha" key={indice}>
          <span>{pagamento.label}</span>
          <span>{brl(pagamento.valor)}</span>
        </p>
      ))}
      {Number(venda.troco) > 0 && (
        <p className="dk-recibo__linha">
          <span>Troco</span>
          <span>{brl(venda.troco)}</span>
        </p>
      )}

      <hr className="dk-recibo__regua" />

      {/* A frase não é enfeite: é o que separa um comprovante de cortesia de um documento
          fiscal, para quem segura o papel. */}
      <p className="dk-recibo__centro dk-recibo__forte">NÃO É DOCUMENTO FISCAL</p>
      <p className="dk-recibo__centro">Comprovante de venda sem valor fiscal.</p>

      {perfil?.rodape && <p className="dk-recibo__centro">{perfil.rodape}</p>}
    </div>
  );
}

/** Escolha da largura do papel, por estação — a mesma regra do tema no `BRAND.md`. */
export function LarguraDoPapel({ onChange }: { onChange: (largura: LarguraDoRecibo) => void }) {
  const [largura, setLargura] = useState<LarguraDoRecibo>(preferencia.getLargura());

  function escolher(proxima: LarguraDoRecibo) {
    preferencia.setLargura(proxima);
    setLargura(proxima);
    onChange(proxima);
  }

  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted">
      <span>Papel:</span>
      {(["58mm", "80mm"] as const).map((opcao) => (
        <button
          key={opcao}
          type="button"
          onClick={() => escolher(opcao)}
          className={
            "min-h-touch rounded-dk px-3 transition-colors duration-150 ease-dk " +
            (largura === opcao
              ? "bg-sunken font-medium text-ink"
              : "text-ink-muted hover:text-ink")
          }
        >
          {opcao}
        </button>
      ))}
    </div>
  );
}
