"""Configuração da suíte inteira.

**A suíte não toca a rede.** A conferência de senha vazada (ADR 0011) roda em todo
cadastro de empresa, e a suíte cadastra uma empresa por teste: ligada, ela transformaria
cada teste numa chamada a serviço de terceiro — lenta, instável e falhando por motivo que
não é o código. Desligada aqui, ela é exercitada onde deve, em
``modules/core/tests/test_breach.py``, com um cliente HTTP que o próprio teste responde.

A variável de ambiente é definida antes de qualquer import do projeto, e o cache das
configurações é limpo para ela valer.
"""

import os

os.environ["DECKO_BREACH_CHECK_ENABLED"] = "false"

from decko.config import get_settings

get_settings.cache_clear()
