import apps from "../assets/icons/apps.png";
import boxes from "../assets/icons/boxes.png";
import drone from "../assets/icons/drone.png";
import home from "../assets/icons/home.png";
import register from "../assets/icons/register.png";
import settings from "../assets/icons/settings.png";
import store from "../assets/icons/store.png";
import truck from "../assets/icons/truck.png";

/* Os ícones do Decko, desenhados para o projeto. A folha de origem e o recorte estão em
 * docs/brand/ — ver docs/BRAND.md, seção 2.2.
 *
 * O mapa é escrito à mão de propósito. Varrer a pasta com import.meta.glob traria os 35
 * ícones para dentro do pacote, e o alvo inclui PC antigo de caixa: entra no pacote o que
 * está em uso. Módulo novo que declare um ícone acrescenta uma linha aqui. */
const ARTE: Record<string, string> = {
  apps,
  boxes,
  drone,
  home,
  register,
  settings,
  store,
  truck,
};

/** O ícone genérico, para módulo que declara um nome que esta versão ainda não tem. */
const PADRAO = apps;

interface Props {
  /** Nome declarado no module.toml do módulo, ou escolhido pela tela. */
  name: string;
  /** Lado em pixels. 32 dentro da placa de 48, 22 no menu lateral. */
  size?: number;
  className?: string;
}

export function ModuleIcon({ name, size = 32, className = "" }: Props) {
  return (
    <img
      src={ARTE[name] ?? PADRAO}
      // Decorativo: quem nomeia o módulo é o título ao lado. Alt vazio evita o leitor de
      // tela dizer o nome duas vezes.
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      draggable={false}
      className={`select-none object-contain ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
