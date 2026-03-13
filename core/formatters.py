"""
Formatadores de valores para pt-BR — portados de BOTDI.py.

Os dados podem vir de duas fontes:
  - XML de DI  → valores inteiros escalados (ex.: monetário × 10^7, percentual × 100)
  - API DUIMP  → valores float já em escala real

Use o parâmetro `from_xml=True` nas funções que possuem essa dicotomia.
"""


def formatar_quantidade(valor_str: str, unidade_medida: str) -> str:
    """
    Converte quantidade do XML para string pt-BR.

    O XML armazena o valor com 5 ou 6 casas decimais implícitas:
      - 6 casas: METRO LINEAR, METRO
      - 5 casas: todas as demais unidades
    """
    unidades_6_casas = {'METRO LINEAR', 'METRO'}
    divisor = 1_000_000 if unidade_medida.upper() in unidades_6_casas else 100_000
    casas = 6 if divisor == 1_000_000 else 5

    valor_int = int(valor_str)
    valor_float = valor_int / divisor
    formatted = f"{valor_float:,.{casas}f}"
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


def formatar_valor_monetario(valor_str: str, from_xml: bool = True) -> str:
    """
    Formata valor monetário para pt-BR com 7 casas decimais.

    - from_xml=True  → divide por 10.000.000 (escala do XML de DI)
    - from_xml=False → valor já é float real (API DUIMP)
    """
    if from_xml:
        valor_float = int(valor_str) / 10_000_000.0
    else:
        valor_float = float(valor_str)

    formatted = f"{valor_float:,.7f}"
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


def formatar_percentual(valor_str: str, from_xml: bool = True) -> str:
    """
    Formata alíquota para pt-BR com 2 casas decimais + símbolo %.

    - from_xml=True  → divide por 100 (escala do XML de DI, ex.: 1600 → 16,00%)
    - from_xml=False → valor já é percentual real (ex.: 16.0 → 16,00%)
    """
    if from_xml:
        valor_float = int(valor_str) / 100.0
    else:
        valor_float = float(valor_str)

    formatted = f"{valor_float:.2f}"
    formatted = formatted.replace('.', ',')
    return f"{formatted}%"


def formatar_valor_monetario_api(valor) -> str:
    """Atalho para valores vindos da API DUIMP (já em escala real)."""
    return formatar_valor_monetario(str(valor), from_xml=False)


def formatar_percentual_api(valor) -> str:
    """Atalho para percentuais vindos da API DUIMP (já em escala real)."""
    return formatar_percentual(str(valor), from_xml=False)
