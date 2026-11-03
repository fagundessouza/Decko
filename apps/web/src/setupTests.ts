import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/* Desmonta o que cada teste montou.
 *
 * A Testing Library faz isso sozinha quando `globals` do Vitest está ligado — ela se
 * pendura no `afterEach` global. Aqui os testes importam `describe`, `it` e `expect`
 * explicitamente, que é mais claro sobre de onde cada coisa vem, e o preço é este
 * gancho ter de ser declarado.
 *
 * Sem ele a árvore de um teste continua no documento durante o próximo. O sintoma não é
 * um erro honesto: é uma busca encontrando dois elementos iguais, ou pior, encontrando o
 * elemento do teste anterior e passando por engano. */
afterEach(cleanup);
