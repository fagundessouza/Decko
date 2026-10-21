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

/** Data ISO (aaaa-mm-dd) como dd/mm/aaaa, sem passar por Date para não deslocar o fuso. */
export function dateBr(iso: string | null): string {
  if (!iso) return "—";
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

/** Tira a máscara do CPF/CNPJ, preservando as letras do CNPJ alfanumérico.
 *
 * Desde julho de 2026 as doze primeiras posições do CNPJ aceitam letras; só os dois
 * dígitos verificadores seguem numéricos. Descartar letras aqui corromperia o documento
 * de empresa aberta de lá para cá.
 */
export function onlyDocumentChars(value: string): string {
  return value.toUpperCase().replace(/[^0-9A-Z]/g, "");
}
