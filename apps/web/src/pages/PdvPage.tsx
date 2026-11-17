import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { Alert } from "../components/Alert";
import { useAutorizacao } from "../components/Autorizacao";
import { MeuPin } from "../components/MeuPin";
import { TrocarOperador } from "../components/TrocarOperador";
import { Page, PageHeader } from "../components/AppShell";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card, CardBody, CardHeader } from "../components/Card";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { LarguraDoPapel, Recibo } from "../components/Recibo";
import { TextField } from "../components/TextField";
import type { Cliente } from "../lib/clientes";
import { listar as listarCarteira } from "../lib/carteira";
import * as balcao from "../lib/balcao";
import { EVENTO_FILA, type Pendente } from "../lib/fila";
import { enviarPendentes } from "../lib/sincronia";
import { financeiro } from "../lib/financeiro";
import type { ContaRecebimento } from "../lib/financeiro";
import type { Produto } from "../lib/comercial";
import { brl, num } from "../lib/format";
import { FORMAS, pdv } from "../lib/pdv";
import * as catalogo from "../lib/catalogo";
import { session } from "../lib/session";
import { SemRedeError, type SessionInfo } from "../lib/api";
import type {
  ConfiguracaoPdv,
  Credencial,
  FormaPagamento,
  ItemVenda,
  Venda,
} from "../lib/pdv";

/* As operações de caixa vivem **dentro** do ponto de venda, sobrepostas.
 *
 * Eram telas irmãs no menu lateral, e isso estava errado por dois motivos: virava uma
 * lista de itens que pareciam módulos diferentes, e tirava o operador do balcão para
 * fazer uma sangria. Agora são diálogos que travam a tela de trás enquanto a operação
 * acontece — ver docs/adr/0020-operador-supervisor-e-papeis.md, decisão 5.
 *
 * Continuam carregando sob demanda: quem só vende nunca baixa o código delas. */
const MeuCaixaPage = lazy(() =>
  import("./MeuCaixaPage").then((m) => ({ default: m.MeuCaixaPage })),
);
const DevolucaoPage = lazy(() =>
  import("./DevolucaoPage").then((m) => ({ default: m.DevolucaoPage })),
);
const CaixaPage = lazy(() =>
  import("./CaixaPage").then((m) => ({ default: m.CaixaPage })),
);
const AjustesCaixaPage = lazy(() =>
  import("./AjustesCaixaPage").then((m) => ({ default: m.AjustesCaixaPage })),
);

type Operacao = "meu-caixa" | "devolucao" | "conferencia" | "ajustes";

interface Props {
  onBack: () => void;
  /** Nome da empresa, para o cabeçalho do recibo. Vem da sessão, então existe sempre. */
  empresa: string;
  /** Só quando a empresa tem o módulo de clientes e quem opera pode identificar.
   *
   *  O PDV passou a depender de `clientes`, mas empresa que já tinha o PDV sem ele não
   *  recebe o módulo sozinha — instalar na empresa dos outros sem pedido é o que a ADR
   *  0010 recusa para a semente. Então a tela simplesmente não oferece. */
  podeIdentificar: boolean;
  /** Operações que esta pessoa alcança. O que ela não pode nem aparece como botão. */
  podeAbrirCaixa: boolean;
  podeDevolver: boolean;
  podeConferir: boolean;
  /** Mexer no que a loja exige supervisor para fazer. Sem isto, a tela é só leitura. */
  podeAjustar: boolean;
  /** Já tem PIN: a tela diz "trocar" em vez de "definir". */
  jaTemPin: boolean;
  /** O turno passou: a sessão agora é de quem assumiu a estação. */
  onOperadorTrocado: (info: SessionInfo) => void;
}

function motivo(cause: unknown, padrao: string): string {
  return cause instanceof Error && cause.message ? cause.message : padrao;
}

/* A tela do balcão.
 *
 * Tudo o que é dinheiro vem calculado do servidor: total, falta e troco chegam prontos a
 * cada resposta — ver docs/adr/0008-ponto-de-venda.md, decisão 3. A tela só desenha.
 *
 * O campo de código fica com o foco o tempo inteiro, porque o leitor de código de barras
 * digita e dá Enter. Perder o foco depois de cada item faria o operador pegar no mouse a
 * cada produto, que é o que torna um PDV lento. */
export function PdvPage({
  onBack,
  empresa,
  podeIdentificar,
  podeAbrirCaixa,
  podeDevolver,
  podeConferir,
  podeAjustar,
  jaTemPin,
  onOperadorTrocado,
}: Props) {
  const [venda, setVenda] = useState<Venda | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [codigo, setCodigo] = useState("");
  const [quantidade, setQuantidade] = useState("1");
  const [achados, setAchados] = useState<Produto[] | null>(null);

  const [cobrando, setCobrando] = useState<FormaPagamento | null>(null);
  const [contas, setContas] = useState<ContaRecebimento[]>([]);
  /* A conta fica lembrada entre pagamentos da mesma sessão: num balcão o Pix cai quase
   * sempre no mesmo lugar, e escolher a cada venda seria atrito por nada. */
  const [conta, setConta] = useState("");
  const [valorRecebido, setValorRecebido] = useState("");
  const [concluida, setConcluida] = useState<Venda | null>(null);

  const [descontando, setDescontando] = useState(false);
  const [valorDesconto, setValorDesconto] = useState("");

  // A liberação do supervisor: a tela tenta a ação, e só pede a credencial se o servidor
  // disser que falta — ver docs/adr/0020-operador-supervisor-e-papeis.md, decisão 4.
  const autorizacao = useAutorizacao();

  const [operacao, setOperacao] = useState<Operacao | null>(null);
  /* Troca de operador e PIN moram **aqui**, e não no rodapé do menu.
   *
   * Passar o turno é operação de balcão: quem faz isso está na tela de venda, com fila,
   * e procurar no menu lateral é sair de onde se está. O PIN anda junto porque é ele que
   * destrava a troca — separá-los mandaria a pessoa a dois lugares para uma coisa só. */
  const [trocandoOperador, setTrocandoOperador] = useState(false);
  const [definindoPin, setDefinindoPin] = useState(false);

  /* A trava de abertura: o caixa abre no nome de quem vai operar.
   *
   * `null` é "ainda não sei", e nesse estado nada é desenhado — nem a trava, nem a venda.
   * Perguntar depois de já ter aberto uma venda poria o começo do turno na conta de quem
   * passou antes, que é exatamente o que a trava existe para evitar.
   *
   * Falha de rede ao ler a configuração **destrava**: isto organiza o turno, não guarda
   * dinheiro, e uma loja parada por um soluço de rede seria pior do que o problema. */
  const [travado, setTravado] = useState<boolean | null>(null);
  /* A busca veio do aparelho, e não do servidor. Quem está vendendo precisa saber: o
   * preço é o da última sincronização, e produto cadastrado hoje pode não estar ali. */
  const [semRede, setSemRede] = useState(false);
  /* **Esta venda está sendo composta no aparelho.**
   *
   * É o coração da fatia 4 da ADR 0022. Enquanto é falso, quem manda é o servidor e a
   * tela só desenha — a decisão 3 da ADR 0008 valendo como sempre valeu. Vira verdadeiro
   * na primeira operação que a rede recusar, e aí a venda continua aqui: o item entra, o
   * pagamento entra, o total é somado neste aparelho e a venda inteira sobe num pacote
   * quando a conexão voltar.
   *
   * Não volta a falso no meio da venda, nem se a rede voltar. A venda local tem itens com
   * identidade daqui, e metade dela no servidor seria pior do que ela inteira aqui — ela
   * sobe inteira no fechamento, que é quando a conta vira fato. */
  const [local, setLocal] = useState(false);
  /* O que esta loja exige supervisor para fazer, guardado no aparelho.
   *
   * Sem rede não há a quem pedir liberação, e é esta configuração que diz se a ação
   * depende de alguém — ver `balcao.podeSemLiberacao`. */
  const [config, setConfig] = useState<ConfiguracaoPdv | null>(null);
  /* Vendas deste aparelho que ainda não chegaram ao servidor, e vendas que chegaram com
   * divergência de estoque. As duas listas são para quem está no balcão: a primeira diz
   * "a venda não se perdeu"; a segunda, "você vendeu o que não tinha". */
  const [naFila, setNaFila] = useState<Pendente[]>([]);
  const [avisos, setAvisos] = useState<balcao.Aviso[]>([]);
  /* O identificador da empresa, e não o nome: `empresa` acima é o nome que sai no recibo.
   * O armazenamento do aparelho é separado por identificador, o mesmo que a carteira de
   * clientes usa — duas empresas no mesmo balcão não podem misturar catálogo. */
  const chaveLocal = session.getTenantSlug();

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const doServidor = await pdv.configuracao();
        await balcao.guardarConfiguracao(chaveLocal, doServidor);
        if (!vivo) return;
        setConfig(doServidor);
        setTravado(doServidor.exige_pin_no_pdv);
      } catch {
        /* Sem rede, a regra da loja é a da última sincronização — e a trava destrava, como
         * já destravava antes desta fatia. O PIN é conferido no servidor, então honrar a
         * trava aqui deixaria a estação fechada sem caminho para entrar. Entrar sem rede é
         * a fatia 5 da ADR 0022, e ainda não existe. */
        const guardada = await balcao.configuracaoGuardada(chaveLocal);
        if (!vivo) return;
        setConfig(guardada);
        setTravado(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [chaveLocal]);

  /* A fila do aparelho, relida sempre que ela muda — inclusive quando esvazia sozinha em
   * segundo plano, com a pessoa parada nesta tela. */
  const reverFila = useCallback(() => {
    void balcao.vendasNaFila(chaveLocal).then(setNaFila);
    void balcao.avisos(chaveLocal).then(setAvisos);
  }, [chaveLocal]);

  useEffect(() => {
    reverFila();
    window.addEventListener(EVENTO_FILA, reverFila);
    return () => window.removeEventListener(EVENTO_FILA, reverFila);
  }, [reverFila]);

  const [identificando, setIdentificando] = useState(false);
  const [buscaCliente, setBuscaCliente] = useState("");
  const [achadosCliente, setAchadosCliente] = useState<Cliente[] | null>(null);

  const campoCodigo = useRef<HTMLInputElement>(null);

  const focarCodigo = useCallback(() => {
    // Depois do render, senão o foco corre antes de o campo voltar a existir.
    requestAnimationFrame(() => campoCodigo.current?.focus());
  }, []);

  /* Retoma a venda aberta em vez de começar outra: recarregar a página não pode perder o
   * que já foi bipado. */
  /* Renova o catálogo guardado ao abrir o PDV.
   *
   * É aqui, e não num relógio de fundo: quem abre o caixa está começando o expediente,
   * que é exatamente quando vale gastar rede para ficar preparado para a falta dela.
   * Falha é silenciosa — não ter rede agora é o próprio caso que isto serve. */
  useEffect(() => {
    void catalogo.atualizar(chaveLocal).catch(() => undefined);
  }, [chaveLocal]);

  useEffect(() => {
    // Enquanto a trava não for resolvida, nenhuma venda é aberta — ver `travado`.
    if (travado !== false) return;

    /* O módulo `financeiro` pode não estar ativo nesta empresa: aí a escolha de conta
     * simplesmente não aparece, e o caixa vende como antes. */
    financeiro
      .listarContas()
      .then(setContas)
      .catch(() => setContas([]));
    let vivo = true;
    (async () => {
      try {
        const abertas = await pdv.listVendas("aberta");
        if (!vivo) return;
        const atual = abertas[0]
          ? await pdv.ver(abertas[0].id)
          : await pdv.abrir();
        if (!vivo) return;
        setVenda(atual);
      } catch (cause) {
        if (!vivo) return;
        /* Sem rede o caixa **abre no aparelho**. Era aqui que a operação morria: o PDV
         * mostrava "não foi possível abrir o caixa" e não havia como vender nada, com
         * cliente na frente e mercadoria na mão. */
        if (cause instanceof SemRedeError) {
          setVenda(balcao.vendaNova());
          setLocal(true);
        } else {
          setErro(motivo(cause, "Não foi possível abrir o caixa."));
        }
      } finally {
        if (vivo) {
          setCarregando(false);
          focarCodigo();
        }
      }
    })();
    return () => {
      vivo = false;
    };
  }, [focarCodigo, travado]);

  /* As teclas de função abrem o recebimento.
   *
   * No caixa a mão não sai do teclado: o código é bipado, a quantidade é digitada, e ter
   * de pegar no mouse no fim de cada venda quebra o ritmo no ponto que mais se repete.
   * As teclas são as que `FORMAS` já declarava e que até aqui não faziam nada.
   *
   * **Enquanto o PDV está na tela, estas teclas são dele**, mesmo quando não há o que
   * receber. Antes o efeito só se ligava com venda e item, e nos outros momentos — que
   * é a maior parte do expediente — F1 abria a ajuda do navegador e F3 a busca, por
   * cima do caixa. Tecla que às vezes faz outra coisa é pior do que tecla que não faz
   * nada: o operador para de confiar nela e volta ao mouse.
   *
   * Agir é outra história, e aí as guardas valem. Dentro do recebimento, F2 trocaria a
   * forma por baixo de quem já está digitando o valor — e o título do diálogo passaria a
   * mentir sobre o que vai ser registrado.
   *
   * As guardas repetem as do botão de propósito: atalho que faz o que o botão desabilitado
   * recusa é um caminho por fora da regra, não uma conveniência. */
  useEffect(() => {
    const aoTeclar = (evento: KeyboardEvent) => {
      // Com modificador, a combinação é do navegador ou do sistema: Ctrl+F4 fecha aba, e
      // tomar isso do usuário seria pior do que não ter atalho.
      if (evento.ctrlKey || evento.altKey || evento.metaKey) return;
      const forma = FORMAS.find((item) => item.atalho === evento.key);
      if (!forma) return;

      // Engolida sempre, antes de qualquer guarda: é isto que impede o navegador de
      // abrir ajuda, busca ou barra de endereço por cima do atendimento.
      evento.preventDefault();

      if (!venda || venda.itens.length === 0 || busy) return;
      if (cobrando !== null || achados !== null || identificando || descontando)
        return;

      setCobrando(forma.valor);
      // Mesmo padrão do botão: o caso comum é receber exatamente o que falta.
      setValorRecebido(venda.falta);
    };

    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, [venda, busy, cobrando, achados, identificando, descontando]);

  /** Aplica a operação no aparelho. Devolve se deu certo. */
  function aplicarLocal(acao: (venda: Venda) => Venda, padrao: string): boolean {
    if (!venda) return false;
    try {
      setVenda(acao(venda));
      setErro(null);
      return true;
    } catch (cause) {
      setErro(motivo(cause, padrao));
      return false;
    } finally {
      focarCodigo();
    }
  }

  /* Toda operação da venda passa por aqui, e é isto que faz a operação não parar.
   *
   * Com rede, quem decide é o servidor — regra de negócio não desce para a tela. Quando a
   * rede cai **no meio da operação**, a mesma operação é refeita no aparelho e a venda
   * passa a ser composta aqui. A bipada não se perde, a venda não recomeça, e o operador
   * não precisa fazer nada diferente: ele continua bipando.
   *
   * A queda é reconhecida por `SemRedeError`, e só por ela: 422 do servidor é regra de
   * negócio recusando, e refazer a operação no aparelho passaria por cima da regra. */
  async function mexer(
    online: (venda: Venda) => Promise<Venda>,
    noAparelho: (venda: Venda) => Venda,
    padrao: string,
  ): Promise<boolean> {
    if (!venda) return false;
    if (local) return aplicarLocal(noAparelho, padrao);

    setBusy(true);
    setErro(null);
    try {
      setVenda(await online(venda));
      return true;
    } catch (cause) {
      if (!(cause instanceof SemRedeError)) {
        setErro(motivo(cause, padrao));
        return false;
      }
      setLocal(true);
      return aplicarLocal(noAparelho, padrao);
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  async function lancar(produto: Produto) {
    const entrou = await mexer(
      (atual) =>
        pdv.adicionarItem(atual.id, {
          produto_id: produto.id,
          quantidade: quantidade.replace(",", ".") || "1",
        }),
      (atual) => balcao.lancar(atual, produto, quantidade),
      "Não foi possível lançar o item.",
    );
    if (!entrou) return;
    setCodigo("");
    setQuantidade("1");
    setAchados(null);
  }

  async function procurar() {
    const termo = codigo.trim();
    if (termo === "" || !venda) return;

    setBusy(true);
    setErro(null);
    try {
      const achado = await catalogo.procurar(chaveLocal, termo);
      const produtos = achado.produtos.filter((item) => item.ativo);
      setSemRede(achado.doAparelho);
      if (produtos.length === 0) {
        setErro(`Nenhum produto para “${termo}”.`);
        setAchados(null);
      } else if (produtos.length === 1) {
        // Caso do leitor de código de barras: achou um, lança e segue.
        await lancar(produtos[0]);
      } else {
        setAchados(produtos);
      }
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível procurar o produto."));
    } finally {
      setBusy(false);
    }
  }

  async function procurarCliente() {
    setErro(null);
    try {
      /* Pela carteira, e não direto pelo servidor: ela cai no cadastro guardado neste
       * aparelho quando não há rede. Identificar a venda é o que permite vender no crediário
       * de quem o dono conhece, e isso não pode depender de sinal. */
      const visao = await listarCarteira(chaveLocal, buscaCliente);
      setAchadosCliente(visao.clientes);
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível procurar o cliente."));
    }
  }

  async function escolherCliente(cliente: Cliente) {
    setIdentificando(false);
    setBuscaCliente("");
    setAchadosCliente(null);
    await mexer(
      (atual) => pdv.identificar(atual.id, cliente.id),
      (atual) => balcao.identificar(atual, cliente),
      "Não foi possível identificar a venda.",
    );
  }

  /* Ação que a loja pode exigir supervisor para fazer.
   *
   * A tela **tenta primeiro**. Se o servidor responder que falta liberação, o diálogo
   * abre e a mesma ação é repetida com a credencial. Nenhum botão é destravado antes:
   * quem decide é o servidor, na requisição que executa. */
  async function operarComLiberacao(
    acao: (credencial?: Credencial) => Promise<Venda>,
    padrao: string,
  ) {
    setBusy(true);
    setErro(null);
    try {
      await autorizacao.executar(async (credencial) =>
        setVenda(await acao(credencial)),
      );
    } catch (cause) {
      if (cause instanceof SemRedeError) {
        // A venda passa a ser deste aparelho, e a ação é repetida do jeito local.
        setLocal(true);
        setErro("A conexão caiu. Esta venda agora é deste aparelho — tente de novo.");
      } else {
        setErro(motivo(cause, padrao));
      }
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  /** O recado de quando a loja exige supervisor e não há a quem pedir. */
  function semLiberacao(oque: string): string {
    return (
      `Esta loja exige liberação de supervisor para ${oque}, e sem conexão não há a quem ` +
      "pedir. A liberação é conferida no servidor, nunca neste aparelho."
    );
  }

  async function retirarItem(item: ItemVenda) {
    if (local) {
      if (!balcao.podeSemLiberacao(config, "cancelar_item")) {
        setErro(semLiberacao("retirar item da venda"));
        return;
      }
      aplicarLocal(
        (atual) => balcao.retirar(atual, item.id),
        "Não foi possível retirar o item.",
      );
      return;
    }
    if (!venda) return;
    await operarComLiberacao(
      (credencial) => pdv.removerItem(venda.id, item.id, credencial),
      "Não foi possível retirar o item.",
    );
  }

  async function cobrar() {
    if (!venda || cobrando === null) return;
    const forma = cobrando;
    const valor = valorRecebido.replace(",", ".");
    const destino = conta || null;
    setCobrando(null);
    setValorRecebido("");
    await mexer(
      (atual) => pdv.pagar(atual.id, { forma, valor, conta_id: destino }),
      (atual) =>
        balcao.pagar(atual, {
          forma,
          valor,
          conta_id: destino,
          // O nome da conta é só para a tela; o servidor resolve pelo id na sincronização.
          conta_nome: contas.find((item) => item.id === destino)?.nome ?? null,
        }),
      "Não foi possível registrar o pagamento.",
    );
  }

  async function aplicarDesconto() {
    if (!venda) return;
    // Vírgula para ponto, como no resto da tela: quem está no caixa escreve "1,50".
    const valor = valorDesconto.replace(",", ".") || "0";
    setDescontando(false);
    setValorDesconto("");

    if (local) {
      if (!balcao.podeSemLiberacao(config, "desconto", valor)) {
        setErro(semLiberacao("dar este desconto"));
        return;
      }
      aplicarLocal(
        (atual) => balcao.definirDesconto(atual, valor),
        "Não foi possível dar o desconto.",
      );
      return;
    }

    await operarComLiberacao(
      (credencial) => pdv.definirDesconto(venda.id, valor, credencial),
      "Não foi possível dar o desconto.",
    );
  }

  async function cancelarVenda() {
    if (!venda) return;

    if (local) {
      if (!balcao.podeSemLiberacao(config, "cancelar_venda")) {
        setErro(semLiberacao("cancelar a venda"));
        return;
      }
      /* A venda local nunca foi gravada em lugar nenhum: cancelar é esquecê-la. Nada é
       * enfileirado, e por isso nada precisa ser desfeito no servidor depois. */
      setVenda(null);
      setErro(null);
      focarCodigo();
      return;
    }

    setBusy(true);
    setErro(null);
    try {
      // A venda só sai da tela depois que o servidor cancelou de verdade. Limpar antes
      // faria o diálogo de liberação abrir sobre uma tela que já esqueceu a venda.
      await autorizacao.executar(async (credencial) => {
        await pdv.cancelar(venda.id, credencial);
        setVenda(null);
      });
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível cancelar."));
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  /** Fecha a venda no aparelho e põe o pacote na fila. */
  async function concluirNoAparelho(aberta: Venda) {
    const fechada = balcao.fechar(aberta);
    await balcao.enfileirarVenda(chaveLocal, fechada);
    setConcluida(fechada);
    setVenda(null);
    // A venda seguinte tenta o servidor de novo: a rede pode já ter voltado.
    setLocal(false);
    // E esta mesma tenta subir agora, pelo mesmo motivo. Falhar aqui não é problema: ela
    // está na fila, e a fila sobe sozinha quando a rede voltar.
    void enviarPendentes(chaveLocal).catch(() => undefined);
  }

  async function finalizar() {
    if (!venda) return;
    setBusy(true);
    setErro(null);
    try {
      if (local) {
        await concluirNoAparelho(venda);
        return;
      }
      try {
        const fechada = await pdv.finalizar(venda.id);
        setConcluida(fechada);
        setVenda(null);
      } catch (cause) {
        if (!(cause instanceof SemRedeError)) throw cause;
        /* A rede caiu **no fechamento**, o pior momento possível: o dinheiro já está na
         * gaveta. O pedido pode ter chegado e só a resposta ter se perdido — e aí a venda
         * sobe de novo sem duplicar, porque o id é o desta venda e o servidor reconhece a
         * segunda chegada do mesmo pacote (ADR 0022, fatia 1). O que não dá é perdê-la. */
        await concluirNoAparelho(venda);
      }
    } catch (cause) {
      setErro(motivo(cause, "Não foi possível fechar a venda."));
    } finally {
      setBusy(false);
    }
  }

  async function novaVenda() {
    setConcluida(null);
    setBusy(true);
    setErro(null);
    try {
      setVenda(await pdv.abrir());
      setLocal(false);
    } catch (cause) {
      if (cause instanceof SemRedeError) {
        setVenda(balcao.vendaNova());
        setLocal(true);
      } else {
        setErro(motivo(cause, "Não foi possível abrir outra venda."));
      }
    } finally {
      setBusy(false);
      focarCodigo();
    }
  }

  /* A trava de abertura.
   *
   * Vem antes de tudo, inclusive do "abrindo o caixa": enquanto não se sabe quem está
   * operando, não há venda, não há tela e não há o que fazer aqui além de dizer quem é —
   * ou sair. A saída está escrita no diálogo, porque trava sem saída dita é armadilha. */
  if (travado === true) {
    return (
      <Page wide>
        <PageHeader title="Ponto de venda" onBack={onBack} />
        <TrocarOperador
          open
          travado
          onClose={() => undefined}
          onSair={onBack}
          onDefinirPin={() => setDefinindoPin(true)}
          onTrocado={(nova) => {
            onOperadorTrocado(nova);
            setTravado(false);
          }}
        />
        <MeuPin
          open={definindoPin}
          onClose={() => setDefinindoPin(false)}
          jaTem={jaTemPin}
          nested
        />
      </Page>
    );
  }

  if (carregando || travado === null) {
    return (
      <Page wide>
        <p className="animate-fade text-base text-ink-muted">
          Abrindo o caixa…
        </p>
      </Page>
    );
  }

  if (concluida) {
    return (
      <Page>
        <PageHeader title="Venda concluída" onBack={onBack} />
        <Card>
          <CardBody className="text-center">
            <p className="text-sm uppercase tracking-wide text-ink-faint">
              Venda
            </p>
            {/* Sem rede a venda ainda não tem número: ele nasce no servidor, porque dois
                caixas sem rede não têm como combinar um contador. Mostrar um número
                inventado aqui seria pior do que não mostrar nenhum — o cliente levaria um
                cupom com um número que não existe. */}
            <p className="mt-1 text-5xl font-bold tabular-nums tracking-tight text-ink">
              {concluida.numero ?? "—"}
            </p>
            {concluida.numero === null && (
              <p className="mt-3 text-base text-ink-muted">
                A venda está guardada neste aparelho e sobe sozinha quando a rede voltar.
                O número do cupom sai lá.
              </p>
            )}

            <dl className="mt-8 flex flex-col gap-3 text-left">
              <Linha rotulo="Total" valor={brl(concluida.total)} />
              <Linha rotulo="Recebido" valor={brl(concluida.pago)} />
              {Number(concluida.troco) > 0 && (
                <Linha rotulo="Troco" valor={brl(concluida.troco)} destaque />
              )}
            </dl>

            <div className="mt-8 flex flex-col gap-3">
              <Button onClick={() => void novaVenda()} loading={busy}>
                Nova venda
              </Button>
              {/* O recibo é opcional: muito balcão não imprime nada, e obrigar a passar
                  por um diálogo de impressão a cada venda atrasaria a fila. */}
              <Button variant="secondary" onClick={() => window.print()}>
                Imprimir recibo
              </Button>
              <div className="flex justify-center">
                <LarguraDoPapel onChange={() => undefined} />
              </div>
            </div>
          </CardBody>
        </Card>

        <Recibo venda={concluida} empresa={empresa} />
      </Page>
    );
  }

  const operacoes = (
    <>
      <div className="mb-6 flex flex-wrap gap-2">
        {podeAbrirCaixa && (
          <Button
            variant="secondary"
            inline
            onClick={() => setOperacao("meu-caixa")}
          >
            Meu caixa
          </Button>
        )}
        {podeDevolver && (
          <Button
            variant="secondary"
            inline
            onClick={() => setOperacao("devolucao")}
          >
            Devolução
          </Button>
        )}
        {podeConferir && (
          <Button
            variant="secondary"
            inline
            onClick={() => setOperacao("conferencia")}
          >
            Conferência do dia
          </Button>
        )}
        {podeAjustar && (
          <Button
            variant="secondary"
            inline
            onClick={() => setOperacao("ajustes")}
          >
            Ajustes do caixa
          </Button>
        )}
        {/* Sem permissão: passar o turno e ter um PIN é de quem opera, seja quem for. */}
        <Button
          variant="secondary"
          inline
          onClick={() => setTrocandoOperador(true)}
        >
          Trocar de operador
        </Button>
        <Button
          variant="secondary"
          inline
          onClick={() => setDefinindoPin(true)}
        >
          Meu PIN
        </Button>
      </div>

      <TrocarOperador
        open={trocandoOperador}
        onClose={() => setTrocandoOperador(false)}
        onTrocado={onOperadorTrocado}
      />

      <MeuPin
        open={definindoPin}
        onClose={() => setDefinindoPin(false)}
        jaTem={jaTemPin}
      />

      <Modal
        open={operacao === "meu-caixa"}
        largura="ampla"
        title="Meu caixa"
        description="Abra, lance retiradas e entradas, e feche contando a gaveta."
        onClose={() => setOperacao(null)}
      >
        <Suspense
          fallback={<p className="text-base text-ink-muted">Carregando…</p>}
        >
          <MeuCaixaPage embutido />
        </Suspense>
      </Modal>

      <Modal
        open={operacao === "devolucao"}
        largura="ampla"
        title="Devolução de venda"
        description="Ache a venda pelo número do cupom e diga o que está voltando."
        onClose={() => setOperacao(null)}
      >
        <Suspense
          fallback={<p className="text-base text-ink-muted">Carregando…</p>}
        >
          <DevolucaoPage embutido />
        </Suspense>
      </Modal>

      <Modal
        open={operacao === "conferencia"}
        largura="ampla"
        title="Conferência do dia"
        description="Conte o dinheiro da gaveta antes de ver o que o sistema esperava."
        onClose={() => setOperacao(null)}
      >
        <Suspense
          fallback={<p className="text-base text-ink-muted">Carregando…</p>}
        >
          <CaixaPage embutido />
        </Suspense>
      </Modal>

      <Modal
        open={operacao === "ajustes"}
        largura="ampla"
        title="Ajustes do caixa"
        description="O que esta loja exige supervisor para fazer, e a partir de quanto."
        onClose={() => setOperacao(null)}
      >
        <Suspense
          fallback={<p className="text-base text-ink-muted">Carregando…</p>}
        >
          <AjustesCaixaPage podeEditar={podeAjustar} />
        </Suspense>
      </Modal>
    </>
  );

  if (!venda) {
    return (
      <Page>
        <PageHeader title="Ponto de venda" onBack={onBack} />
        {erro && <Alert tone="danger">{erro}</Alert>}
        <Pendencias
          naFila={naFila}
          avisos={avisos}
          onEsquecer={(id) => void balcao.esquecerAviso(chaveLocal, id).then(reverFila)}
        />
        {/* As operações vêm antes de abrir venda de propósito: o operador abre o caixa
            dele no começo do expediente, quando ainda não há venda nenhuma. */}
        <div className="mt-6">{operacoes}</div>
        <Button onClick={() => void novaVenda()} loading={busy}>
          Abrir venda
        </Button>
      </Page>
    );
  }

  const falta = Number(venda.falta);
  const temItem = venda.itens.length > 0;

  return (
    <Page wide>
      <PageHeader
        title="Ponto de venda"
        description="Bipe o código de barras ou digite o código do produto e dê Enter."
        onBack={onBack}
      />

      {(local || semRede) && (
        <div className="mb-6">
          <Alert tone="warn">
            {local
              ? "Sem conexão: esta venda está sendo feita neste aparelho. Ela sobe sozinha " +
                "quando a rede voltar, e é lá que o número do cupom nasce. Os preços são os " +
                "da última sincronização."
              : "Sem conexão: a busca está usando o catálogo guardado neste aparelho. Os " +
                "preços são os da última sincronização, e produto cadastrado hoje pode não " +
                "aparecer."}
          </Alert>
        </div>
      )}

      <Pendencias
        naFila={naFila}
        avisos={avisos}
        onEsquecer={(id) => void balcao.esquecerAviso(chaveLocal, id).then(reverFila)}
      />

      {erro && (
        <div className="mb-6">
          <Alert tone="danger">{erro}</Alert>
        </div>
      )}

      {operacoes}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardBody>
              <form
                className="flex flex-col gap-4 sm:flex-row sm:items-end"
                onSubmit={(event) => {
                  event.preventDefault();
                  void procurar();
                }}
              >
                <div className="flex-1">
                  <TextField
                    ref={campoCodigo}
                    label="Código, código de barras ou nome"
                    leading="⌕"
                    autoFocus
                    autoComplete="off"
                    value={codigo}
                    onChange={(event) => setCodigo(event.target.value)}
                    /* O Enter é tratado aqui, e não só pelo submit do formulário: o
                     * leitor de código de barras termina a leitura com Enter, e deixar
                     * isso por conta do envio implícito do formulário é frágil demais
                     * para o que mais se repete no caixa. */
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void procurar();
                      }
                    }}
                    placeholder="Bipe ou digite"
                  />
                </div>
                <div className="w-full sm:w-28">
                  <TextField
                    label="Qtd."
                    inputMode="decimal"
                    value={quantidade}
                    onChange={(event) => setQuantidade(event.target.value)}
                  />
                </div>
                <Button type="submit" inline loading={busy}>
                  Lançar
                </Button>
              </form>
            </CardBody>
          </Card>

          {podeIdentificar && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-base">
              {venda.cliente_nome ? (
                <>
                  <span className="text-ink-muted">Cliente:</span>
                  <span className="font-medium text-ink">
                    {venda.cliente_nome}
                  </span>
                  <Button
                    variant="ghost"
                    inline
                    disabled={busy}
                    onClick={() => setIdentificando(true)}
                  >
                    Trocar
                  </Button>
                  <Button
                    variant="ghost"
                    inline
                    disabled={busy}
                    onClick={() =>
                      void mexer(
                        (atual) => pdv.desidentificar(atual.id),
                        (atual) => balcao.desidentificar(atual),
                        "Não foi possível tirar o cliente da venda.",
                      )
                    }
                  >
                    Tirar
                  </Button>
                </>
              ) : (
                <>
                  {/* Venda anônima é o caso normal, e a frase diz isso em vez de parecer
                      um campo por preencher. */}
                  <span className="text-ink-muted">Venda anônima.</span>
                  <Button
                    variant="ghost"
                    inline
                    disabled={busy}
                    onClick={() => setIdentificando(true)}
                  >
                    Identificar cliente
                  </Button>
                </>
              )}
            </div>
          )}

          <Card>
            <CardHeader
              title="Itens"
              description={
                temItem ? undefined : "Nada lançado ainda nesta venda."
              }
            />
            {temItem && (
              <ul className="mt-2">
                {venda.itens.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center gap-4 border-b border-line-subtle px-5 py-3 last:border-0 sm:px-6"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-base font-medium text-ink">
                        {item.descricao}
                      </p>
                      <p className="text-sm tabular-nums text-ink-muted">
                        {num(item.quantidade, 3)} × {brl(item.preco_unitario)}
                      </p>
                    </div>
                    <p className="shrink-0 text-base font-semibold tabular-nums text-ink">
                      {brl(item.total)}
                    </p>
                    <button
                      type="button"
                      aria-label={`Retirar ${item.descricao}`}
                      disabled={busy}
                      onClick={() => void retirarItem(item)}
                      className="shrink-0 rounded-dk px-2 py-1 text-lg leading-none text-ink-faint
                                 transition-colors duration-150 ease-dk hover:bg-danger-soft hover:text-danger
                                 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardBody>
              <dl className="flex flex-col gap-2.5">
                <Linha rotulo="Subtotal" valor={brl(venda.soma_dos_itens)} />
                {Number(venda.desconto) > 0 && (
                  <Linha rotulo="Desconto" valor={`− ${brl(venda.desconto)}`} />
                )}
              </dl>

              {/* O servidor aceita desconto desde o início e nenhuma tela chamava. A regra
                  é dele: não negativo, não maior que a soma dos itens, e só em venda
                  aberta — aqui não se repete nada disso, só se oferece o caminho. */}
              <div className="mt-3">
                <Button
                  variant="ghost"
                  inline
                  disabled={!temItem || busy}
                  onClick={() => {
                    setValorDesconto(
                      Number(venda.desconto) > 0 ? venda.desconto : "",
                    );
                    setDescontando(true);
                  }}
                >
                  {Number(venda.desconto) > 0
                    ? "Alterar desconto"
                    : "Dar desconto"}
                </Button>
              </div>

              <div className="mt-5 border-t border-line-subtle pt-5">
                <p className="text-sm uppercase tracking-wide text-ink-faint">
                  A pagar
                </p>
                <p className="mt-1 text-4xl font-bold tabular-nums tracking-tight text-ink">
                  {brl(venda.total)}
                </p>
              </div>

              {venda.pagamentos.length > 0 && (
                <ul className="mt-5 flex flex-col gap-2 border-t border-line-subtle pt-5">
                  {venda.pagamentos.map((pagamento) => (
                    <li
                      key={pagamento.id}
                      className="flex items-center justify-between gap-3 text-sm"
                    >
                      <span className="capitalize text-ink-muted">
                        {pagamento.forma}
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="tabular-nums text-ink">
                          {brl(pagamento.valor)}
                        </span>
                        <button
                          type="button"
                          aria-label="Retirar pagamento"
                          disabled={busy}
                          onClick={() =>
                            void mexer(
                              (atual) =>
                                pdv.removerPagamento(atual.id, pagamento.id),
                              (atual) =>
                                balcao.retirarPagamento(atual, pagamento.id),
                              "Não foi possível retirar o pagamento.",
                            )
                          }
                          className="rounded-dk px-1.5 leading-none text-ink-faint
                                     transition-colors duration-150 ease-dk hover:text-danger
                                     disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          ×
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              <div className="mt-5 border-t border-line-subtle pt-5">
                {falta > 0 ? (
                  <Linha rotulo="Falta" valor={brl(venda.falta)} destaque />
                ) : (
                  <Linha rotulo="Troco" valor={brl(venda.troco)} destaque />
                )}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Receber" />
            <CardBody className="pt-4">
              <div className="grid grid-cols-2 gap-3">
                {FORMAS.map((forma) => (
                  <Button
                    key={forma.valor}
                    variant="secondary"
                    disabled={!temItem || busy}
                    onClick={() => {
                      setCobrando(forma.valor);
                      // O caso comum é receber exatamente o que falta.
                      setValorRecebido(venda.falta);
                    }}
                    aria-keyshortcuts={forma.atalho}
                  >
                    {forma.label}
                    {/* Escondido de leitor de tela porque `aria-keyshortcuts` já informa
                        o atalho, e some no celular, onde não há tecla de função. */}
                    <span
                      aria-hidden="true"
                      className="hidden text-sm font-normal text-ink-faint sm:inline"
                    >
                      {forma.atalho}
                    </span>
                  </Button>
                ))}
              </div>

              <div className="mt-5 flex flex-col gap-3">
                <Button
                  disabled={!temItem || falta > 0}
                  loading={busy}
                  onClick={() => void finalizar()}
                >
                  Fechar venda
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void cancelarVenda()}
                >
                  Cancelar venda
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>

      <Modal
        open={identificando}
        title="Identificar a venda"
        description="Procure por nome, apelido ou documento."
        onClose={() => {
          setIdentificando(false);
          setBuscaCliente("");
          setAchadosCliente(null);
          focarCodigo();
        }}
      >
        <form
          className="flex gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void procurarCliente();
          }}
        >
          <div className="flex-1">
            <TextField
              label="Cliente"
              leading="⌕"
              autoFocus
              autoComplete="off"
              value={buscaCliente}
              onChange={(event) => setBuscaCliente(event.target.value)}
              placeholder="Nome, apelido ou CPF"
            />
          </div>
          <div className="self-end">
            <Button type="submit" inline>
              Procurar
            </Button>
          </div>
        </form>

        {achadosCliente !== null && achadosCliente.length === 0 && (
          <p className="mt-4 text-base text-ink-muted">
            Nenhum cliente encontrado. Cadastre em Clientes e volte aqui.
          </p>
        )}

        {achadosCliente !== null && achadosCliente.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2">
            {achadosCliente.map((cliente) => (
              <li key={cliente.id}>
                <button
                  type="button"
                  onClick={() => void escolherCliente(cliente)}
                  className="flex min-h-touch w-full items-center justify-between gap-3
                             rounded-dk px-4 py-3 text-left ring-1 ring-line
                             transition-colors duration-150 ease-dk hover:bg-sunken"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-base font-medium text-ink">
                      {cliente.nome}
                    </span>
                    {(cliente.apelido || cliente.cpf_cnpj) && (
                      <span className="block truncate text-sm text-ink-faint">
                        {[cliente.apelido, cliente.cpf_cnpj]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    )}
                  </span>
                  <span aria-hidden="true" className="text-ink-faint">
                    →
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Modal>

      <Modal
        open={achados !== null}
        title="Qual produto?"
        description="Mais de um produto bate com o que foi digitado."
        onClose={() => {
          setAchados(null);
          focarCodigo();
        }}
      >
        <ul className="flex flex-col gap-2">
          {(achados ?? []).map((produto) => (
            <li key={produto.id}>
              <button
                type="button"
                onClick={() => void lancar(produto)}
                className="flex w-full items-center justify-between gap-4 rounded-dk px-4 py-3 text-left
                           ring-1 ring-line-subtle transition-colors duration-150 ease-dk hover:bg-sunken"
              >
                <span className="min-w-0">
                  <span className="block truncate text-base text-ink">
                    {produto.nome}
                  </span>
                  <span className="block text-sm tabular-nums text-ink-faint">
                    {produto.codigo}
                  </span>
                </span>
                <span className="shrink-0 text-base font-semibold tabular-nums text-ink">
                  {produto.preco_venda ? brl(produto.preco_venda) : "sem preço"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Modal>

      <Modal
        open={descontando}
        title="Desconto na venda"
        description="Sobre o total, além do que cada item já tenha."
        onClose={() => {
          setDescontando(false);
          focarCodigo();
        }}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button
              variant="secondary"
              inline
              onClick={() => setDescontando(false)}
            >
              Cancelar
            </Button>
            <Button inline onClick={() => void aplicarDesconto()}>
              Aplicar
            </Button>
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void aplicarDesconto();
          }}
        >
          <TextField
            label="Desconto"
            leading="R$"
            inputMode="decimal"
            value={valorDesconto}
            onChange={(event) => setValorDesconto(event.target.value)}
            hint={`A venda soma ${brl(venda.soma_dos_itens)}. Zero tira o desconto.`}
          />
        </form>
      </Modal>

      <Modal
        open={cobrando !== null}
        title={`Receber em ${FORMAS.find((f) => f.valor === cobrando)?.label ?? ""}`}
        onClose={() => setCobrando(null)}
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button
              variant="secondary"
              inline
              onClick={() => setCobrando(null)}
            >
              Cancelar
            </Button>
            <Button inline onClick={() => void cobrar()}>
              Receber
            </Button>
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void cobrar();
          }}
        >
          <TextField
            label="Valor recebido"
            leading="R$"
            inputMode="decimal"
            value={valorRecebido}
            onChange={(event) => setValorRecebido(event.target.value)}
          />
          {contas.length > 0 && (
            <div className="mt-4">
              <Select
                label="Caiu em"
                value={conta}
                onChange={setConta}
                options={contas.map((item) => ({
                  value: item.id,
                  label: item.nome,
                }))}
                placeholder="Não informar"
                hint="Opcional. É o que permite fechar o caixa sabendo o que entrou em cada lugar."
              />
            </div>
          )}

          <p className="mt-3 text-sm text-ink-muted">
            Falta {brl(venda.falta)}. Troco só sai de pagamento em dinheiro.
          </p>
        </form>
      </Modal>

      <p className="mt-8 flex items-center gap-2 text-sm text-ink-faint">
        <Badge>Sem emissão fiscal</Badge>
        Esta venda registra a saída no estoque. A emissão de cupom fiscal entra
        com o módulo fiscal.
      </p>

      {autorizacao.dialogo}
    </Page>
  );
}

/* O que este aparelho vendeu e o servidor ainda não sabe, e o que ele soube e não bateu.
 *
 * Fica na tela do caixa porque é lá que está quem precisa disso. A trilha de auditoria
 * registra a divergência para o dono da loja; esta lista é para o operador, no mesmo dia:
 * ele vendeu o que o estoque dizia não ter, e isso tem de ter endereço — qual produto,
 * quanto saiu, com quanto ficou.
 *
 * A fila some sozinha quando sobe. O que **não** some sozinho é a recusa: venda que o
 * servidor não aceitou fica com o motivo à mostra, porque repetir não resolveria e apagar
 * esconderia de quem vendeu que a venda não entrou. */
function Pendencias({
  naFila,
  avisos,
  onEsquecer,
}: {
  naFila: Pendente[];
  avisos: balcao.Aviso[];
  onEsquecer: (id: string) => void;
}) {
  const esperando = naFila.filter((item) => !item.erro);
  const recusadas = naFila.filter((item) => item.erro);
  if (esperando.length === 0 && recusadas.length === 0 && avisos.length === 0) return null;

  return (
    <div className="mb-6 flex flex-col gap-3">
      {esperando.length > 0 && (
        <Alert tone="info">
          {esperando.length === 1
            ? "1 venda feita neste aparelho está esperando a rede."
            : `${esperando.length} vendas feitas neste aparelho estão esperando a rede.`}{" "}
          Elas sobem sozinhas, sem ninguém pedir.
        </Alert>
      )}

      {recusadas.map((item) => (
        <Alert tone="danger" key={item.id}>
          Uma venda deste aparelho não foi aceita pelo servidor: {item.erro} Ela continua
          guardada aqui; chame quem cuida do caixa.
        </Alert>
      ))}

      {avisos.map((aviso) => (
        <Alert tone="warn" key={aviso.id}>
          <span className="font-medium">
            A venda {aviso.numero ?? "sem número"} entrou com o estoque negativo.
          </span>{" "}
          {aviso.divergencias
            .map(
              (divergencia) =>
                `${divergencia.descricao}: saíram ${num(divergencia.vendido, 3)} e o saldo ` +
                `ficou em ${num(divergencia.saldo_depois, 3)}`,
            )
            .join("; ")}
          .{" "}
          <button
            type="button"
            onClick={() => onEsquecer(aviso.id)}
            className="underline underline-offset-2"
          >
            Entendi
          </button>
        </Alert>
      ))}
    </div>
  );
}

function Linha({
  rotulo,
  valor,
  destaque = false,
}: {
  rotulo: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt
        className={destaque ? "text-base text-ink" : "text-sm text-ink-muted"}
      >
        {rotulo}
      </dt>
      <dd
        className={
          "tabular-nums " +
          (destaque ? "text-xl font-semibold text-ink" : "text-base text-ink")
        }
      >
        {valor}
      </dd>
    </div>
  );
}
