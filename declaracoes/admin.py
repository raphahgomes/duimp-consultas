from django.contrib import admin

from .models import ConfiguracaoAPI, ConsultaDeclaracao, ItemDeclaracao, ApplicationLog


@admin.register(ConfiguracaoAPI)
class ConfiguracaoAPIAdmin(admin.ModelAdmin):
    list_display = ('cpf_cnpj', 'criado_em', 'atualizado_em')
    readonly_fields = ('criado_em', 'atualizado_em', 'id_chave_encrypted', 'chave_secreta_encrypted')


@admin.register(ConsultaDeclaracao)
class ConsultaDeclaracaoAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'numero', 'usuario', 'status', 'criado_em')
    list_filter = ('tipo', 'status')
    readonly_fields = ('criado_em', 'task_id')


@admin.register(ItemDeclaracao)
class ItemDeclaracaoAdmin(admin.ModelAdmin):
    list_display = ('consulta', 'num_adicao', 'sequencial', 'ncm', 'descricao')
    list_filter = ('consulta__tipo',)
    search_fields = ('ncm', 'descricao')


@admin.register(ApplicationLog)
class ApplicationLogAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'nivel', 'acao', 'referencia', 'usuario')
    list_filter = ('nivel',)
    search_fields = ('acao', 'mensagem', 'referencia')
    readonly_fields = ('criado_em',)
