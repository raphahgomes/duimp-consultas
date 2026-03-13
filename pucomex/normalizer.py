"""
Normalizador: converte respostas brutas da API DUIMP para o formato de 12 colunas
utilizado pelo sistema (equivalente ao output de BOTDI.py).

As 12 colunas são:
  1.  num_adicao       → Nº Adição
  2.  sequencial       → Seq.
  3.  quantidade       → Quantidade (formatada pt-BR)
  4.  unidade_medida   → Unidade Medida
  5.  descricao        → Descrição Mercadoria
  6.  c_class_trib     → cClassTrib
  7.  valor_unitario   → Valor Unitário (formatado pt-BR, 7 casas)
  8.  ii               → II (percentual formatado pt-BR)
  9.  ipi              → IPI (percentual formatado pt-BR)
  10. pis_pasep        → PIS/PASEP (percentual formatado pt-BR)
  11. cofins           → COFINS (percentual formatado pt-BR)
  12. ncm              → NCM

Estrutura real da API (endpoint /itens):
  item['identificacao']['numeroItem']                     → nº do item
  item['mercadoria']['quantidadeComercial']               → quantidade
  item['mercadoria']['unidadeComercial']                  → unidade
  item['mercadoria']['descricao']                         → descrição
  item['mercadoria']['valorUnitarioMoedaNegociada']       → valor unitário
  item['produto']['ncm']                                  → NCM
  item['tributos']['tributosCalculados']                  → lista com:
      { tipo: "II"/"IPI"/"PIS"/"COFINS",
        memoriaCalculo: { valorAliquota: float } }
"""

import logging
import re
from typing import Any

from core.formatters import (
    formatar_valor_monetario_api,
    formatar_percentual_api,
)

logger = logging.getLogger(__name__)


def _safe_get(obj: Any, *keys, default=None):
    """Navega por dicts aninhados de forma segura."""
    current = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current


def _extrair_c_class_trib(descricao: str) -> str:
    """Extrai o cClassTrib embutido na descrição (mesmo padrão de BOTDI.py)."""
    match = re.search(r'cClassTrib\s*[:\{]\s*([^\}\s,;]+)', descricao or '')
    if match:
        return match.group(1).strip()
    return ''


def _limpar_descricao(descricao: str) -> str:
    """Remove o bloco cClassTrib da descrição, se presente."""
    return re.sub(r'\s*cClassTrib\s*[:\{][^\}]*\}?', '', descricao or '').strip()


def _fmt_qtd(raw_val: str) -> str:
    """Formata quantidade (vem como '200.00000' da API) para pt-BR."""
    try:
        val = float(raw_val)
        formatted = f"{val:,.5f}"
        return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return str(raw_val) if raw_val else '0,00000'


def _extrair_tributos_item(item: dict) -> dict[str, float]:
    """
    Extrai alíquotas de tributos do campo item['tributos']['tributosCalculados'].

    Retorna dict com chaves 'II', 'IPI', 'PIS', 'COFINS' → valorAliquota.
    """
    result: dict[str, float] = {}
    tributos_calc = _safe_get(item, 'tributos', 'tributosCalculados', default=[])
    if not isinstance(tributos_calc, list):
        return result
    for t in tributos_calc:
        tipo = _safe_get(t, 'tipo', default='')
        aliquota = _safe_get(t, 'memoriaCalculo', 'valorAliquota', default=0)
        if tipo and aliquota is not None:
            result[tipo.upper()] = aliquota
    return result


def _normalizar_item(item: dict, idx: int) -> dict:
    """Normaliza um item da API DUIMP para o formato de 12 colunas."""
    # Identificação
    num_item = _safe_get(item, 'identificacao', 'numeroItem', default=idx)

    # Mercadoria (dados aninhados)
    merc = item.get('mercadoria') or {}
    qtd_raw = merc.get('quantidadeComercial') or merc.get('quantidadeMedidaEstatistica') or '0'
    unidade = (merc.get('unidadeComercial') or merc.get('unidadeMedidaEstatistica') or '').upper()
    descricao_raw = merc.get('descricao') or merc.get('descricaoMercadoria') or ''
    val_unitario_raw = merc.get('valorUnitarioMoedaNegociada') or merc.get('valorUnitario') or '0'

    # NCM (em produto.ncm)
    ncm = _safe_get(item, 'produto', 'ncm', default='') or ''

    # Formatação
    qtd_fmt = _fmt_qtd(qtd_raw)
    c_class_trib = _extrair_c_class_trib(descricao_raw)
    descricao = _limpar_descricao(descricao_raw)

    try:
        val_unitario_fmt = formatar_valor_monetario_api(val_unitario_raw)
    except (ValueError, TypeError):
        val_unitario_fmt = str(val_unitario_raw)

    # Tributos (inline no item)
    trib = _extrair_tributos_item(item)

    def fmt_pct(v):
        try:
            return formatar_percentual_api(v)
        except (ValueError, TypeError):
            return '0,00%'

    ii = fmt_pct(trib.get('II', 0))
    ipi = fmt_pct(trib.get('IPI', 0))
    pis = fmt_pct(trib.get('PIS', 0))
    cofins = fmt_pct(trib.get('COFINS', 0))

    return {
        'num_adicao': 1,          # DUIMP não tem conceito de adição como DI
        'sequencial': int(num_item),
        'quantidade': qtd_fmt,
        'unidade_medida': unidade,
        'descricao': descricao,
        'c_class_trib': c_class_trib,
        'valor_unitario': val_unitario_fmt,
        'ii': ii,
        'ipi': ipi,
        'pis_pasep': pis,
        'cofins': cofins,
        'ncm': ncm,
    }


# ── Ponto de entrada principal ─────────────────────────────────────────────

def normalizar_duimp(dados_api: dict) -> list[dict]:
    """
    Converte o retorno bruto de `api_duimp.consultar_duimp()` para lista de
    dicts com as 12 colunas, ordenada por (num_adicao, sequencial).
    """
    itens_raw = dados_api.get('itens', [])

    resultado = []
    for idx, item in enumerate(itens_raw, start=1):
        try:
            row = _normalizar_item(item, idx)
            resultado.append(row)
        except Exception as exc:
            logger.warning('Erro ao normalizar item %d: %s', idx, exc)

    resultado.sort(key=lambda r: (r['num_adicao'], r['sequencial']))
    return resultado
