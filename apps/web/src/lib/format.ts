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

/** NCM como se lê no edital: 8 dígitos viram 0000.00.00.
 *
 * O comprador confere esse número contra o edital, dígito a dígito. Oito caracteres
 * corridos é o formato que faz errar. Vale também enquanto a pessoa digita: o campo
 * mostra o ponto na hora certa e não aceita o nono dígito.
 */
export function ncmMask(value: string): string {
  const d = value.replace(/\D/g, "").slice(0, 8);
  if (d.length <= 4) return d;
  if (d.length <= 6) return `${d.slice(0, 4)}.${d.slice(4)}`;
  return `${d.slice(0, 4)}.${d.slice(4, 6)}.${d.slice(6)}`;
}

/** CEST: 7 dígitos viram 00.000.00. */
export function cestMask(value: string): string {
  const d = value.replace(/\D/g, "").slice(0, 7);
  if (d.length <= 2) return d;
  if (d.length <= 5) return `${d.slice(0, 2)}.${d.slice(2)}`;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`;
}

const ROSA = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"];

/** Direção do vento em graus, como quem está no campo lê: "135° (SE)".
 *
 * Grau sozinho não se lê de relance, e quem confere o documento pensa em rumo, não em
 * número. Os dois juntos: o grau é o dado, a letra é a leitura.
 */
export function ventoBr(graus: string | number | null | undefined): string {
  // Ausência é testada antes da conversão: `Number(null)` é 0, e zero grau é norte —
  // uma leitura sem direção sairia como "0° (N)", que é um dado inventado.
  if (graus === null || graus === undefined || graus === "") return "—";
  const valor = Number(graus);
  if (Number.isNaN(valor)) return "—";
  const rumo = ROSA[Math.round(((valor % 360) + 360) % 360 / 45) % 8];
  return `${Math.round(valor)}° (${rumo})`;
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
