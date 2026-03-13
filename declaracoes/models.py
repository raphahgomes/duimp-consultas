"""
Models da app declaracoes.

ConfiguracaoAPI   — armazena as chaves de acesso ao Portal Único criptografadas com Fernet.
ConsultaDeclaracao — representa uma consulta de DI ou DUIMP.
ItemDeclaracao     — representa um item (adição/seq) de uma consulta.
"""

import logging

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


def _fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY.encode() if isinstance(settings.FERNET_KEY, str) else settings.FERNET_KEY)


class ConfiguracaoAPI(models.Model):
    """
    Configuração de acesso ao Portal Único Siscomex.

    Armazena o par de chaves (id_chave + chave_secreta) criptografado com
    Fernet AES-256, garantindo que nunca fique legível no banco de dados.
    """

    cpf_cnpj = models.CharField('CPF/CNPJ do importador', max_length=18)
    id_chave_encrypted = models.TextField('ID da chave (criptografado)')
    chave_secreta_encrypted = models.TextField('Chave secreta (criptografada)')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de API'
        verbose_name_plural = 'Configurações de API'
        ordering = ['-atualizado_em']

    def __str__(self):
        return f'Config API — {self.cpf_cnpj}'

    # ── Criptografia ───────────────────────────────────────────────────────

    def set_id_chave(self, valor: str) -> None:
        self.id_chave_encrypted = _fernet().encrypt(valor.encode()).decode()

    def get_id_chave(self) -> str:
        return _fernet().decrypt(self.id_chave_encrypted.encode()).decode()

    def set_chave_secreta(self, valor: str) -> None:
        self.chave_secreta_encrypted = _fernet().encrypt(valor.encode()).decode()

    def get_chave_secreta(self) -> str:
        return _fernet().decrypt(self.chave_secreta_encrypted.encode()).decode()


class ConsultaDeclaracao(models.Model):
    """
    Registro de uma consulta de DI ou DUIMP.

    O campo `excel_file` é preenchido após o processamento bem-sucedido.
    O campo `task_id` armazena o ID Celery para acompanhar progresso assíncrono.
    """

    class Tipo(models.TextChoices):
        DI = 'DI', 'DI (Declaração de Importação)'
        DUIMP = 'DUIMP', 'DUIMP'

    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PROCESSANDO = 'PROCESSANDO', 'Processando'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        ERRO = 'ERRO', 'Erro'

    tipo = models.CharField('Tipo', max_length=10, choices=Tipo.choices)
    numero = models.CharField('Número', max_length=50)
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultas',
        verbose_name='Usuário',
    )
    status = models.CharField(
        'Status', max_length=20, choices=Status.choices, default=Status.PENDENTE
    )
    mensagem_erro = models.TextField('Mensagem de erro', blank=True)
    excel_file = models.FileField(
        'Arquivo Excel', upload_to='excels/', blank=True, null=True
    )
    task_id = models.CharField('ID da tarefa Celery', max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Consulta'
        verbose_name_plural = 'Consultas'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.tipo} {self.numero} — {self.get_status_display()}'


class ApplicationLog(models.Model):
    class Nivel(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'

    criado_em = models.DateTimeField(auto_now_add=True)
    nivel = models.CharField('Nível', max_length=10, choices=Nivel.choices)
    acao = models.CharField('Ação', max_length=100)
    mensagem = models.TextField('Mensagem')
    referencia = models.CharField('Referência', max_length=120, blank=True)
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='app_logs',
        verbose_name='Usuário',
    )

    class Meta:
        verbose_name = 'Log'
        verbose_name_plural = 'Logs'
        ordering = ['-criado_em']

    def __str__(self):
        return f'[{self.nivel}] {self.acao}'


class ItemDeclaracao(models.Model):
    """
    Item (adição/sequencial) extraído de uma DI ou DUIMP.
    Armazena os valores já formatados no padrão pt-BR.
    """

    consulta = models.ForeignKey(
        ConsultaDeclaracao,
        on_delete=models.CASCADE,
        related_name='itens',
    )
    num_adicao = models.PositiveIntegerField('Nº Adição')
    sequencial = models.PositiveIntegerField('Seq.')
    quantidade = models.CharField('Quantidade', max_length=50)
    unidade_medida = models.CharField('Unidade Medida', max_length=50)
    descricao = models.TextField('Descrição Mercadoria')
    c_class_trib = models.CharField('cClassTrib', max_length=50, blank=True)
    valor_unitario = models.CharField('Valor Unitário', max_length=50)
    ii = models.CharField('II', max_length=20)
    ipi = models.CharField('IPI', max_length=20)
    pis_pasep = models.CharField('PIS/PASEP', max_length=20)
    cofins = models.CharField('COFINS', max_length=20)
    ncm = models.CharField('NCM', max_length=20)

    class Meta:
        verbose_name = 'Item'
        verbose_name_plural = 'Itens'
        ordering = ['num_adicao', 'sequencial']

    def __str__(self):
        return f'Ad.{self.num_adicao} Seq.{self.sequencial} — {self.ncm}'
