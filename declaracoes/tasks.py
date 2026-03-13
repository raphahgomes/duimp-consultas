"""
Tarefas Celery para processamento assíncrono de DI e DUIMP.
"""

import base64
import logging
import tempfile
import uuid
from pathlib import Path

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def processar_duimp(
    self,
    consulta_id: int,
    cert_pfx_b64: str | None = None,
    cert_password: str | None = None,
    auth_mode: str = 'arquivo',
    cert_thumbprint: str | None = None,
) -> str:
    """
        Processa uma consulta DUIMP:
            1. Autentica no Portal Único (certificado A1 ou chaves salvas)
      2. Consulta a API DUIMP
      3. Normaliza os dados
      4. Salva os itens no banco
      5. Gera o arquivo Excel
    """
    from declaracoes.excel_export import gerar_excel
    from declaracoes.models import ApplicationLog, ConfiguracaoAPI, ConsultaDeclaracao, ItemDeclaracao
    from pucomex.api_duimp import consultar_duimp
    from pucomex.auth import PucomexSession
    from pucomex.normalizer import normalizar_duimp

    try:
        consulta = ConsultaDeclaracao.objects.get(pk=consulta_id)
        consulta.status = ConsultaDeclaracao.Status.PROCESSANDO
        consulta.task_id = self.request.id or ''
        consulta.save(update_fields=['status', 'task_id'])
        ApplicationLog.objects.create(
            nivel='INFO',
            acao='PROCESSAMENTO_DUIMP_INICIADO',
            mensagem=f'Iniciado processamento da DUIMP {consulta.numero}.',
            referencia=consulta.numero,
            usuario=consulta.usuario,
        )

        if auth_mode == 'windows_store':
            # SChannel: mTLS via Windows sem exportar chave privada
            from pucomex.schannel_session import SChannelSession

            if not cert_thumbprint:
                raise RuntimeError('Thumbprint do certificado do Windows não informado.')
            session = SChannelSession(thumbprint=cert_thumbprint, role_type='IMPEXP')
            session.authenticate()
        elif auth_mode == 'arquivo' and cert_pfx_b64 and cert_password:
            session = PucomexSession(role_type='IMPEXP')
            cert_bytes = base64.b64decode(cert_pfx_b64)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pfx') as tmp_cert:
                tmp_cert.write(cert_bytes)
                cert_path = tmp_cert.name
            try:
                session.authenticate_mtls(cert_path, cert_password)
            finally:
                Path(cert_path).unlink(missing_ok=True)
        else:
            config = ConfiguracaoAPI.objects.order_by('-atualizado_em').first()
            if not config:
                raise RuntimeError(
                    'Nenhuma configuração de API encontrada. Configure as chaves de acesso primeiro '
                    'ou use certificado A1 na tela de consulta.'
                )
            session.authenticate_chave_acesso(config.get_id_chave(), config.get_chave_secreta())

        # Consulta API
        dados_api = consultar_duimp(session, consulta.numero)

        # Normaliza
        itens_data = normalizar_duimp(dados_api)
        if not itens_data:
            logger.warning('Nenhum item encontrado para DUIMP %s – prosseguindo com 0 itens.', consulta.numero)

        # Salva itens no banco
        consulta.itens.all().delete()
        ItemDeclaracao.objects.bulk_create([
            ItemDeclaracao(consulta=consulta, **row)
            for row in itens_data
        ])

        # Gera Excel
        nome_arquivo = f'DUIMP_{consulta.numero}_{uuid.uuid4().hex[:8]}.xlsx'
        caminho = Path(settings.MEDIA_ROOT) / 'excels' / nome_arquivo
        gerar_excel(consulta, caminho)

        consulta.excel_file = f'excels/{nome_arquivo}'
        consulta.status = ConsultaDeclaracao.Status.CONCLUIDO
        consulta.mensagem_erro = ''
        consulta.save(update_fields=['excel_file', 'status', 'mensagem_erro'])
        ApplicationLog.objects.create(
            nivel='INFO',
            acao='PROCESSAMENTO_DUIMP_CONCLUIDO',
            mensagem=f'DUIMP {consulta.numero} concluída com {len(itens_data)} itens.',
            referencia=consulta.numero,
            usuario=consulta.usuario,
        )

        logger.info('DUIMP %s processada com sucesso: %d itens', consulta.numero, len(itens_data))
        return f'OK: {len(itens_data)} itens'

    except ConsultaDeclaracao.DoesNotExist:
        logger.error('ConsultaDeclaracao %d não encontrada', consulta_id)
        raise

    except Exception as exc:
        logger.exception('Erro ao processar DUIMP %d: %s', consulta_id, exc)
        try:
            consulta = ConsultaDeclaracao.objects.get(pk=consulta_id)
            consulta.status = ConsultaDeclaracao.Status.ERRO
            consulta.mensagem_erro = str(exc)
            consulta.save(update_fields=['status', 'mensagem_erro'])
            ApplicationLog.objects.create(
                nivel='ERROR',
                acao='PROCESSAMENTO_DUIMP_ERRO',
                mensagem=str(exc),
                referencia=consulta.numero,
                usuario=consulta.usuario,
            )
        except Exception:
            pass
        raise


@shared_task(bind=True)
def processar_di_xml(self, consulta_id: int, xml_b64: str) -> str:
    """
    Processa uma consulta DI a partir do conteúdo bruto do arquivo XML (base64):
      1. Faz parse do XML
      2. Salva os itens no banco
      3. Gera o arquivo Excel
    """
    from declaracoes.excel_export import gerar_excel
    from declaracoes.models import ApplicationLog, ConsultaDeclaracao, ItemDeclaracao
    from declaracoes.services_di import extrair_dados_do_xml

    try:
        consulta = ConsultaDeclaracao.objects.get(pk=consulta_id)
        consulta.status = ConsultaDeclaracao.Status.PROCESSANDO
        consulta.task_id = self.request.id or ''
        consulta.save(update_fields=['status', 'task_id'])
        ApplicationLog.objects.create(
            nivel='INFO',
            acao='PROCESSAMENTO_DI_INICIADO',
            mensagem=f'Iniciado processamento da DI {consulta.numero}.',
            referencia=consulta.numero,
            usuario=consulta.usuario,
        )

        xml_bytes = base64.b64decode(xml_b64)
        itens_data = extrair_dados_do_xml(xml_bytes)
        if not itens_data:
            raise ValueError(f'Nenhum item encontrado no XML para DI {consulta.numero}')

        # Salva itens
        consulta.itens.all().delete()
        ItemDeclaracao.objects.bulk_create([
            ItemDeclaracao(consulta=consulta, **row)
            for row in itens_data
        ])

        # Gera Excel
        nome_arquivo = f'DI_{consulta.numero}_{uuid.uuid4().hex[:8]}.xlsx'
        caminho = Path(settings.MEDIA_ROOT) / 'excels' / nome_arquivo
        gerar_excel(consulta, caminho)

        consulta.excel_file = f'excels/{nome_arquivo}'
        consulta.status = ConsultaDeclaracao.Status.CONCLUIDO
        consulta.mensagem_erro = ''
        consulta.save(update_fields=['excel_file', 'status', 'mensagem_erro'])
        ApplicationLog.objects.create(
            nivel='INFO',
            acao='PROCESSAMENTO_DI_CONCLUIDO',
            mensagem=f'DI {consulta.numero} concluída com {len(itens_data)} itens.',
            referencia=consulta.numero,
            usuario=consulta.usuario,
        )

        logger.info('DI %s processada: %d itens', consulta.numero, len(itens_data))
        return f'OK: {len(itens_data)} itens'

    except ConsultaDeclaracao.DoesNotExist:
        logger.error('ConsultaDeclaracao %d não encontrada', consulta_id)
        raise

    except Exception as exc:
        logger.exception('Erro ao processar DI %d: %s', consulta_id, exc)
        try:
            consulta = ConsultaDeclaracao.objects.get(pk=consulta_id)
            consulta.status = ConsultaDeclaracao.Status.ERRO
            consulta.mensagem_erro = str(exc)
            consulta.save(update_fields=['status', 'mensagem_erro'])
            ApplicationLog.objects.create(
                nivel='ERROR',
                acao='PROCESSAMENTO_DI_ERRO',
                mensagem=str(exc),
                referencia=consulta.numero,
                usuario=consulta.usuario,
            )
        except Exception:
            pass
        raise
