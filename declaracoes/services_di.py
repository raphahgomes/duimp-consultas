"""
Serviço para processar Declarações de Importação (DI) a partir de arquivo XML.

Portado de BOTDI.py. A lógica de parsing permanece idêntica ao script original:
  - Suporte a múltiplos namespaces via {*}
  - Extração de cClassTrib via regex na descrição
  - Formatos pt-BR com as mesmas casas decimais
"""

import logging
import re
from typing import Union
from xml.etree import ElementTree as ET

from core.formatters import formatar_quantidade, formatar_valor_monetario, formatar_percentual

logger = logging.getLogger(__name__)


def extrair_dados_do_xml(xml_source: Union[str, bytes]) -> list[dict]:
    """
    Extrai os dados de itens/adições de um XML de DI exportado do Siscomex.

    Parâmetros
    ----------
    xml_source : caminho (str) para o arquivo XML, ou conteúdo bruto (bytes)

    Retorna
    -------
    Lista de dicts com as 12 colunas, ordenada por (num_adicao, sequencial).
    """
    if isinstance(xml_source, bytes):
        root = ET.fromstring(xml_source)
    else:
        tree = ET.parse(xml_source)
        root = tree.getroot()

    dados = []

    # Itera sobre todas as adições (elemento <adicao> independente de namespace)
    for adicao in root.iter('{*}adicao'):
        num_adicao_raw = adicao.findtext('{*}numeroAdicao') or adicao.findtext('{*}numero')
        num_adicao = int(num_adicao_raw) if num_adicao_raw else 0

        # ── NCM ──────────────────────────────────────────────────────────
        ncm_node = adicao.find('{*}ncm')
        if ncm_node is not None:
            ncm = ncm_node.findtext('{*}codigo') or ''
        else:
            ncm = adicao.findtext('{*}codigoNcm') or adicao.findtext('{*}ncm') or ''

        # ── Tributos da adição ────────────────────────────────────────────
        ii_raw = adicao.findtext('{*}aliquotaII') or adicao.findtext('{*}percentualReducaoII') or '0'
        ipi_raw = adicao.findtext('{*}aliquotaIPI') or '0'
        pis_raw = adicao.findtext('{*}aliquotaPIS') or adicao.findtext('{*}aliquotaPISPASEP') or '0'
        cofins_raw = adicao.findtext('{*}aliquotaCOFINS') or '0'

        ii = formatar_percentual(ii_raw, from_xml=True)
        ipi = formatar_percentual(ipi_raw, from_xml=True)
        pis = formatar_percentual(pis_raw, from_xml=True)
        cofins = formatar_percentual(cofins_raw, from_xml=True)

        # ── Mercadorias / sequenciais ─────────────────────────────────────
        mercadorias = list(adicao.iter('{*}mercadoria'))
        if not mercadorias:
            # Alguns XMLs colocam sequenciais diretamente na adição
            mercadorias = list(adicao.iter('{*}item'))

        for mercadoria in mercadorias:
            seq_raw = (
                mercadoria.findtext('{*}numeroSequencialItem')
                or mercadoria.findtext('{*}sequencial')
                or mercadoria.findtext('{*}numero')
                or '0'
            )
            sequencial = int(seq_raw)

            # Quantidade e unidade
            quantidade_raw = (
                mercadoria.findtext('{*}quantidadeEstatistica')
                or mercadoria.findtext('{*}quantidade')
                or '0'
            )
            unidade_medida = (
                mercadoria.findtext('{*}unidadeMedidaEstatistica')
                or mercadoria.findtext('{*}unidadeMedida')
                or ''
            ).upper()
            quantidade = formatar_quantidade(quantidade_raw, unidade_medida)

            # Valor unitário
            valor_unitario_raw = (
                mercadoria.findtext('{*}valorUnitario')
                or mercadoria.findtext('{*}valorUnMedEstatistica')
                or '0'
            )
            valor_unitario = formatar_valor_monetario(valor_unitario_raw, from_xml=True)

            # Descrição e cClassTrib
            descricao_bruta = (
                mercadoria.findtext('{*}descricaoMercadoria')
                or mercadoria.findtext('{*}descricao')
                or ''
            )
            match = re.search(r'cClassTrib\s*[:\{]\s*([^\}\s,;]+)', descricao_bruta)
            c_class_trib = match.group(1).strip() if match else ''
            descricao = re.sub(r'\s*cClassTrib\s*[:\{][^\}]*\}?', '', descricao_bruta).strip()

            dados.append({
                'num_adicao':    num_adicao,
                'sequencial':    sequencial,
                'quantidade':    quantidade,
                'unidade_medida': unidade_medida,
                'descricao':     descricao,
                'c_class_trib':  c_class_trib,
                'valor_unitario': valor_unitario,
                'ii':            ii,
                'ipi':           ipi,
                'pis_pasep':     pis,
                'cofins':        cofins,
                'ncm':           ncm,
            })

    dados.sort(key=lambda r: (r['num_adicao'], r['sequencial']))
    logger.info('XML processado: %d itens extraídos', len(dados))
    return dados
