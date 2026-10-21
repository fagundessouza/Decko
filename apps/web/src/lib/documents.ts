/* Conferência de CPF e CNPJ pelo dígito verificador.
 *
 * Espelha `apps/api/src/decko/documents.py`, que é a validação que vale — esta existe
 * para o operador saber do erro enquanto digita, sem depender de ida ao servidor num
 * aparelho que, no campo, costuma estar sem sinal.
 *
 * A regra é da Receita Federal. Desde julho de 2026 as doze primeiras posições do CNPJ
 * aceitam letras maiúsculas; os dois dígitos verificadores seguem numéricos. Cada
 * caractere entra na conta pelo valor ASCII menos 48, de modo que os algarismos mantêm o
 * próprio valor e "A" vale 17.
 */

const CPF_LENGTH = 11;
const CNPJ_LENGTH = 14;
const ASCII_OFFSET = 48;

const CPF_FIRST_WEIGHTS = [10, 9, 8, 7, 6, 5, 4, 3, 2];
const CPF_SECOND_WEIGHTS = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_FIRST_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_SECOND_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];

/** Remove a formatação, preservando as letras do CNPJ alfanumérico. */
export function stripMask(raw: string): string {
  return raw.toUpperCase().replace(/[^0-9A-Z]/g, "");
}

function checkDigit(values: number[], weights: number[]): number {
  const total = values.reduce((sum, value, index) => sum + value * weights[index], 0);
  const remainder = total % 11;
  return remainder < 2 ? 0 : 11 - remainder;
}

function valuesOf(document: string): number[] {
  return [...document].map((character) => character.charCodeAt(0) - ASCII_OFFSET);
}

function isRepeated(document: string): boolean {
  return new Set(document).size === 1;
}

export function isValidCpf(document: string): boolean {
  if (document.length !== CPF_LENGTH || !/^\d+$/.test(document)) return false;
  if (isRepeated(document)) return false;

  const values = valuesOf(document);
  const first = checkDigit(values.slice(0, 9), CPF_FIRST_WEIGHTS);
  const second = checkDigit([...values.slice(0, 9), first], CPF_SECOND_WEIGHTS);
  return values[9] === first && values[10] === second;
}

export function isValidCnpj(document: string): boolean {
  if (document.length !== CNPJ_LENGTH) return false;
  const base = document.slice(0, 12);
  const verifiers = document.slice(12);
  if (!/^[0-9A-Z]{12}$/.test(base) || !/^\d{2}$/.test(verifiers)) return false;
  if (isRepeated(document)) return false;

  const values = valuesOf(base);
  const first = checkDigit(values, CNPJ_FIRST_WEIGHTS);
  const second = checkDigit([...values, first], CNPJ_SECOND_WEIGHTS);
  return verifiers === `${first}${second}`;
}

/** Devolve o que está errado com o documento, ou null quando ele passa. */
export function documentProblem(raw: string): string | null {
  const document = stripMask(raw);

  if (document.length !== CPF_LENGTH && document.length !== CNPJ_LENGTH) {
    return `${document.length} caracteres: o CPF tem ${CPF_LENGTH} e o CNPJ tem ${CNPJ_LENGTH}.`;
  }
  if (document.length === CPF_LENGTH) {
    if (!/^\d+$/.test(document)) return "CPF só tem números.";
    return isValidCpf(document) ? null : "CPF inválido: confira os números.";
  }
  return isValidCnpj(document) ? null : "CNPJ inválido: confira os números.";
}
