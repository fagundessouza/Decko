/** Data de hoje no fuso do aparelho, no formato aceito por <input type="date">.
 *
 * `toISOString()` devolve a data em UTC. No Brasil, entre 21h e a meia-noite isso já é o
 * dia seguinte — e o documento sairia com a data errada justamente nos registros de fim
 * de turno. A data de um relatório de aplicação é a data de quem estava no campo.
 */
export function todayLocal(): string {
  const now = new Date();
  const mes = String(now.getMonth() + 1).padStart(2, "0");
  const dia = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${mes}-${dia}`;
}

/** Hora local em HH:MM. */
export function nowLocalTime(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

/** Turno correspondente ao horário, como ponto de partida — o operador pode trocar. */
export function periodoOfNow(): "matutino" | "vespertino" {
  return new Date().getHours() < 12 ? "matutino" : "vespertino";
}

/** Número no formato brasileiro: vírgula decimal e sem zeros à direita. */
export function num(value: string | number | null | undefined, casas = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(parsed)) return "—";
  return parsed.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

/** Valor em reais, sempre com dois decimais: dinheiro não esconde centavo. */
export function brl(value: string | number | null | undefined): string {
  const parsed = typeof value === "number" ? value : Number(value ?? NaN);
  if (Number.isNaN(parsed)) return "R$ 0,00";
  return parsed.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Data ISO (aaaa-mm-dd) como dd/mm/aaaa, sem passar por Date para não deslocar o fuso. */
export function dateBr(iso: string | null): string {
  if (!iso) return "—";
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}
