"""
Cliente REST para a API DUIMP do Portal Único Siscomex.

Base URL: https://portalunico.siscomex.gov.br/duimp-api/api/ext
Documentação: https://docs.portalunico.siscomex.gov.br/api/dimp/intervenientes-privados/

Endpoints disponíveis:
  GET /duimp/{numero-duimp}/versoes             → lista de versões
  GET /duimp/{numero-duimp}/{versao-duimp}      → dados gerais
  GET /duimp/{numero-duimp}/{versao}/itens      → itens (paginado, de/ate)
  GET /duimp/{numero-duimp}/{versao}/itens/{n}  → item específico
  GET /duimp/{numero-duimp}/{versao}/valores-calculados → tributos
"""

import logging
from typing import Any

from .auth import PucomexSession

logger = logging.getLogger(__name__)

API_BASE = 'https://portalunico.siscomex.gov.br/duimp-api/api/ext'
CATP_BASE = 'https://portalunico.siscomex.gov.br/catp/api/ext'


def _url(*parts: str) -> str:
    return '/'.join([API_BASE.rstrip('/')] + [str(p).strip('/') for p in parts])


def _catp_url(*parts: str) -> str:
    return '/'.join([CATP_BASE.rstrip('/')] + [str(p).strip('/') for p in parts])


# ── Versões ────────────────────────────────────────────────────────────────

def get_versoes(session: PucomexSession, numero: str) -> list[dict]:
    """Retorna lista de versões de uma DUIMP."""
    url = _url('duimp', numero, 'versoes')
    response = session.get(url)
    response.raise_for_status()
    data = response.json()
    logger.debug('Resposta bruta versoes: %s', str(data)[:1000])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # API pode retornar lista dentro de uma chave wrapper
        return data.get('versoes') or data.get('resultado') or data.get('lista') or [data]
    return []


def _extract_version_number(v: dict) -> int | None:
    """Extrai o número da versão de um dict retornado pela API, tentando vários nomes de campo."""
    for key in ('versao', 'numero', 'numeroDaVersao', 'versaoDuimp', 'numeroVersao',
                'version', 'id', 'codigoVersao'):
        val = v.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    return None


def get_versao_vigente(session: PucomexSession, numero: str) -> int:
    """
    Retorna o número da versão vigente (ativa) de uma DUIMP.
    Considera a versão com maior número ou a marcada como vigente.
    """
    versoes = get_versoes(session, numero)
    if not versoes:
        raise ValueError(f'Nenhuma versão encontrada para DUIMP {numero}')

    logger.debug('Versões recebidas da API: %s', versoes)

    # Tenta campo 'vigente' ou 'ativa'; senão, usa a versão de maior número
    for v in versoes:
        if v.get('vigente') or v.get('ativa') or v.get('situacao') in ('VIGENTE', 'ATIVA'):
            num = _extract_version_number(v)
            if num is not None:
                return num

    # Fallback: maior número de versão
    nums = [_extract_version_number(v) for v in versoes]
    nums = [n for n in nums if n is not None]
    if nums:
        return max(nums)

    raise ValueError(
        f'Não foi possível extrair número de versão para DUIMP {numero}. '
        f'Campos disponíveis: {[list(v.keys()) for v in versoes]}'
    )


# ── Dados gerais ───────────────────────────────────────────────────────────

def get_dados_gerais(session: PucomexSession, numero: str, versao: int) -> dict:
    """Retorna os dados gerais de uma DUIMP (importador, modal, portos, etc.)."""
    url = _url('duimp', numero, str(versao))
    response = session.get(url)
    response.raise_for_status()
    return response.json()


# ── Itens ──────────────────────────────────────────────────────────────────

def get_itens(
    session: PucomexSession,
    numero: str,
    versao: int,
    de: int = 1,
    ate: int = 999,
) -> list[dict]:
    """
    Retorna a lista de itens de uma DUIMP.

    O endpoint é paginado por `de`/`ate`. O padrão (1-999) retorna até 999 itens
    de uma vez, suficiente para a grande maioria dos casos.
    """
    url = _url('duimp', numero, str(versao), 'itens')
    params = {'de': de, 'ate': ate}
    response = session.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    # A API pode retornar lista direta ou wrapper com chave 'itens'/'resultado'
    if isinstance(data, list):
        return data
    return data.get('itens') or data.get('resultado') or data.get('lista') or []


def get_item(session: PucomexSession, numero: str, versao: int, num_item: int) -> dict:
    """Retorna um item específico de uma DUIMP."""
    url = _url('duimp', numero, str(versao), 'itens', str(num_item))
    response = session.get(url)
    response.raise_for_status()
    return response.json()


# ── Valores calculados (tributos) ──────────────────────────────────────────

def get_valores_calculados(session: PucomexSession, numero: str, versao: int) -> Any:
    """
    Retorna os valores calculados (II, IPI, PIS/PASEP, COFINS, etc.) de uma DUIMP.

    O retorno pode ser uma lista (por item) ou um dict global, dependendo da versão
    do portal. O normalizador lida com ambos os formatos.
    """
    url = _url('duimp', numero, str(versao), 'valores-calculados')
    response = session.get(url)
    response.raise_for_status()
    return response.json()


# ── Catálogo de Produtos ───────────────────────────────────────────────────

def get_descricao_produto(
    session: PucomexSession,
    ni: str,
    codigo_produto: str,
    versao_produto: str,
) -> str:
    """
    Busca a descrição de um produto no Catálogo de Produtos do Portal Único.
    Retorna a descrição ou string vazia se não encontrar.
    """
    url = _catp_url('produto', ni, codigo_produto, versao_produto)
    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()
        return (
            data.get('descricao')
            or data.get('descricaoMercadoria')
            or data.get('nome')
            or ''
        )
    except Exception as exc:
        logger.warning(
            'Não foi possível obter descrição do produto %s/%s/%s: %s',
            ni, codigo_produto, versao_produto, exc,
        )
        return ''


def _enriquecer_descricoes(session: PucomexSession, itens: list[dict]) -> None:
    """
    Para cada item cujo mercadoria.descricao seja nulo, busca a descrição
    no Catálogo de Produtos e preenche in-place.
    """
    for item in itens:
        merc = item.get('mercadoria') or {}
        if merc.get('descricao'):
            continue  # já tem descrição

        prod = item.get('produto') or {}
        ni = prod.get('niResponsavel')
        codigo = prod.get('codigo')
        versao = prod.get('versao')
        if not (ni and codigo and versao):
            continue  # dados insuficientes para buscar no catálogo

        desc = get_descricao_produto(session, ni, codigo, versao)
        if desc:
            merc['descricao'] = desc
            item['mercadoria'] = merc  # garante referência
            logger.debug(
                'Descrição enriquecida via catálogo para item %s: %s',
                item.get('identificacao', {}).get('numeroItem', '?'),
                desc[:80],
            )


# ── Consulta completa ──────────────────────────────────────────────────────

def consultar_duimp(session: PucomexSession, numero: str) -> dict:
    """
    Realiza consulta completa de uma DUIMP:
      1. Obtém versão vigente
      2. Busca dados gerais
      3. Busca todos os itens
      4. Busca valores calculados

    Retorna dict com as 4 respostas brutas da API.
    """
    logger.info('Consultando DUIMP %s', numero)
    versao = get_versao_vigente(session, numero)
    logger.debug('Versão vigente: %d', versao)

    dados_gerais = get_dados_gerais(session, numero, versao)

    try:
        itens = get_itens(session, numero, versao)
    except Exception as exc:
        logger.warning('Itens indisponíveis para DUIMP %s: %s', numero, exc)
        itens = []

    try:
        valores = get_valores_calculados(session, numero, versao)
    except Exception as exc:
        logger.warning('Valores calculados indisponíveis para DUIMP %s: %s', numero, exc)
        valores = []

    # Enriquecer descrições faltantes via Catálogo de Produtos
    _enriquecer_descricoes(session, itens)

    logger.info('DUIMP %s consultada: %d itens', numero, len(itens))
    return {
        'versao': versao,
        'dados_gerais': dados_gerais,
        'itens': itens,
        'valores_calculados': valores,
    }
