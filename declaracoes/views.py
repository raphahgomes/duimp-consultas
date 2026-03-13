"""Views da app declaracoes."""

import base64
import logging
import mimetypes
import re
import platform

from django.contrib import messages
from django.contrib.auth import get_user_model, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .models import ApplicationLog, ConfiguracaoAPI, ConsultaDeclaracao
from pucomex.windows_cert_store import list_installed_certificates, WindowsCertificateStoreError

logger = logging.getLogger(__name__)
User = get_user_model()


def registrar_log(nivel: str, acao: str, mensagem: str, referencia: str = '', usuario=None) -> None:
    ApplicationLog.objects.create(
        nivel=nivel,
        acao=acao,
        mensagem=mensagem,
        referencia=referencia,
        usuario=usuario,
    )


def garantir_grupos_permissoes() -> None:
    perfis = {
        'Admin': [
            'view_consultadeclaracao', 'add_consultadeclaracao', 'change_consultadeclaracao', 'delete_consultadeclaracao',
            'view_itemdeclaracao',
            'view_configuracaoapi', 'add_configuracaoapi', 'change_configuracaoapi', 'delete_configuracaoapi',
            'view_applicationlog',
            'add_user', 'change_user', 'view_user',
            'add_group', 'change_group', 'view_group',
        ],
        'Operador': [
            'view_consultadeclaracao', 'add_consultadeclaracao',
            'view_itemdeclaracao',
            'view_applicationlog',
        ],
        'Consulta': [
            'view_consultadeclaracao',
            'view_itemdeclaracao',
        ],
    }

    for nome_grupo, codenames in perfis.items():
        grupo, _ = Group.objects.get_or_create(name=nome_grupo)
        perms = Permission.objects.filter(codename__in=codenames)
        grupo.permissions.set(perms)


class SetupInicialView(View):
    template_name = 'declaracoes/setup_inicial.html'

    def get(self, request):
        if User.objects.exists():
            return redirect('declaracoes:login')
        return render(request, self.template_name)

    def post(self, request):
        if User.objects.exists():
            return redirect('declaracoes:login')

        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if not nome or not username or not password:
            messages.error(request, 'Preencha nome, usuário e senha.')
            return render(request, self.template_name)
        if password != password2:
            messages.error(request, 'As senhas não conferem.')
            return render(request, self.template_name)
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Este usuário já existe.')
            return render(request, self.template_name)

        garantir_grupos_permissoes()
        admin = User.objects.create_superuser(username=username, email=email, password=password, first_name=nome)
        grupo_admin = Group.objects.get(name='Admin')
        admin.groups.add(grupo_admin)

        registrar_log('INFO', 'SETUP_INICIAL', f'Usuário administrador {username} criado.', usuario=admin)
        messages.success(request, 'Configuração inicial concluída. Faça login para continuar.')
        return redirect('declaracoes:login')


class LoginView(auth_views.LoginView):
    template_name = 'declaracoes/login.html'
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect('declaracoes:setup_inicial')
        return super().dispatch(request, *args, **kwargs)


class LogoutView(auth_views.LogoutView):
    next_page = 'declaracoes:login'


class IndexView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'

    def get(self, request):
        queryset = ConsultaDeclaracao.objects.all()
        if not request.user.is_staff:
            queryset = queryset.filter(usuario=request.user)

        contexto = {
            'total_consultas': queryset.count(),
            'total_concluidas': queryset.filter(status=ConsultaDeclaracao.Status.CONCLUIDO).count(),
            'total_processando': queryset.filter(status=ConsultaDeclaracao.Status.PROCESSANDO).count(),
            'total_erros': queryset.filter(status=ConsultaDeclaracao.Status.ERRO).count(),
            'consultas_recentes': queryset.order_by('-criado_em')[:8],
            'logs_recentes': ApplicationLog.objects.order_by('-criado_em')[:8],
        }
        return render(request, 'declaracoes/dashboard.html', contexto)


class HistoricoView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'

    def get(self, request):
        consultas = ConsultaDeclaracao.objects.all()
        if not request.user.is_staff:
            consultas = consultas.filter(usuario=request.user)

        paginator = Paginator(consultas.order_by('-criado_em'), 25)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        return render(request, 'declaracoes/historico.html', {'page_obj': page_obj})


class LogsView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'

    def get(self, request):
        if not (request.user.is_staff or request.user.has_perm('declaracoes.view_applicationlog')):
            return HttpResponseForbidden('Sem permissão para acessar logs.')

        logs = ApplicationLog.objects.select_related('usuario').order_by('-criado_em')
        paginator = Paginator(logs, 40)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        return render(request, 'declaracoes/logs.html', {'page_obj': page_obj})


class UsuariosView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'
    template_name = 'declaracoes/usuarios.html'

    def get(self, request):
        if not request.user.is_staff:
            return HttpResponseForbidden('Sem permissão para gerenciar usuários.')

        usuarios = User.objects.all().order_by('username')
        return render(request, self.template_name, {
            'usuarios': usuarios,
            'grupos': Group.objects.all().order_by('name'),
        })

    def post(self, request):
        if not request.user.is_staff:
            return HttpResponseForbidden('Sem permissão para gerenciar usuários.')

        username = request.POST.get('username', '').strip()
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        grupo_nome = request.POST.get('grupo', '').strip()

        if not username or not password or not grupo_nome:
            messages.error(request, 'Usuário, senha e perfil são obrigatórios.')
            return redirect('declaracoes:usuarios')
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Usuário já existe.')
            return redirect('declaracoes:usuarios')

        grupo = Group.objects.filter(name=grupo_nome).first()
        if not grupo:
            messages.error(request, 'Perfil inválido.')
            return redirect('declaracoes:usuarios')

        user = User.objects.create_user(username=username, email=email, password=password, first_name=nome)
        user.groups.add(grupo)
        user.is_staff = grupo.name == 'Admin'
        user.save()

        registrar_log('INFO', 'USUARIO_CRIADO', f'Usuário {username} criado no perfil {grupo.name}.', usuario=request.user)
        messages.success(request, f'Usuário {username} criado com sucesso.')
        return redirect('declaracoes:usuarios')


def _consulta_visivel_para_usuario(consulta: ConsultaDeclaracao, user) -> bool:
    return user.is_staff or consulta.usuario_id == user.id


class ConfigurarAPIView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'
    template_name = 'declaracoes/configurar_api.html'

    def get(self, request):
        if not request.user.is_staff:
            return HttpResponseForbidden('Sem permissão para configurar credenciais.')
        config = ConfiguracaoAPI.objects.order_by('-atualizado_em').first()
        contexto = {'config': config}
        return render(request, self.template_name, contexto)

    def post(self, request):
        if not request.user.is_staff:
            return HttpResponseForbidden('Sem permissão para configurar credenciais.')

        cpf_cnpj = request.POST.get('cpf_cnpj', '').strip()
        id_chave = request.POST.get('id_chave', '').strip()
        chave_secreta = request.POST.get('chave_secreta', '').strip()

        if not cpf_cnpj or not id_chave or not chave_secreta:
            messages.error(request, 'Todos os campos são obrigatórios.')
            config = ConfiguracaoAPI.objects.order_by('-atualizado_em').first()
            return render(request, self.template_name, {'config': config})

        config = ConfiguracaoAPI()
        config.cpf_cnpj = cpf_cnpj
        config.set_id_chave(id_chave)
        config.set_chave_secreta(chave_secreta)
        config.save()
        ConfiguracaoAPI.objects.exclude(pk=config.pk).delete()

        registrar_log('INFO', 'CONFIGURACAO_API', 'Credenciais de chave de acesso atualizadas.', usuario=request.user)
        messages.success(request, 'Chaves de acesso salvas com sucesso.')
        return redirect('declaracoes:configurar_api')


class NovaConsultaView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'
    template_name = 'declaracoes/nova_consulta.html'

    def get(self, request):
        is_windows = platform.system().lower() == 'windows'
        certificados_windows = []
        if is_windows:
            try:
                certificados_windows = list_installed_certificates()
            except Exception:
                certificados_windows = []
        return render(request, self.template_name, {
            'certificados_windows': certificados_windows,
            'is_windows': is_windows,
        })

    def post(self, request):
        from .tasks import processar_di_xml, processar_duimp

        tipo = request.POST.get('tipo', '').upper()
        numero = request.POST.get('numero', '').strip()

        if tipo not in ('DI', 'DUIMP'):
            messages.error(request, 'Tipo de declaração inválido.')
            return render(request, self.template_name)

        if not numero:
            messages.error(request, 'Informe o número da declaração.')
            return render(request, self.template_name)

        if tipo == 'DUIMP':
            numero = re.sub(r'[^A-Za-z0-9]', '', numero).upper()

        if tipo == 'DI':
            xml_file = request.FILES.get('xml_file')
            if not xml_file:
                messages.error(request, 'Para DI, o arquivo XML é obrigatório.')
                return render(request, self.template_name)

            xml_b64 = base64.b64encode(xml_file.read()).decode('ascii')
            consulta = ConsultaDeclaracao.objects.create(tipo='DI', numero=numero, usuario=request.user)
            processar_di_xml.delay(consulta.pk, xml_b64)
            registrar_log('INFO', 'CONSULTA_DI_CRIADA', f'Consulta DI {numero} criada.', referencia=numero, usuario=request.user)

        else:
            auth_modo = request.POST.get('auth_modo', 'certificado')
            consulta = ConsultaDeclaracao.objects.create(tipo='DUIMP', numero=numero, usuario=request.user)
            if auth_modo == 'certificado':
                cert_file = request.FILES.get('cert_file')
                cert_password = request.POST.get('cert_password', '').strip()
                if not cert_file or not cert_password:
                    consulta.delete()
                    messages.error(
                        request,
                        'Para autenticação via certificado, envie o arquivo .pfx e a senha do certificado.'
                    )
                    return render(request, self.template_name)

                cert_pfx_b64 = base64.b64encode(cert_file.read()).decode('ascii')
                processar_duimp.delay(consulta.pk, cert_pfx_b64, cert_password, 'arquivo', None)
            elif auth_modo == 'windows_store':
                cert_thumbprint = request.POST.get('cert_thumbprint', '').strip().upper()
                if not cert_thumbprint:
                    consulta.delete()
                    messages.error(
                        request,
                        'Selecione um certificado do repositório do Windows.'
                    )
                    is_windows = platform.system().lower() == 'windows'
                    certificados_windows = []
                    if is_windows:
                        try:
                            certificados_windows = list_installed_certificates()
                        except WindowsCertificateStoreError:
                            certificados_windows = []
                    return render(request, self.template_name, {
                        'certificados_windows': certificados_windows,
                        'is_windows': is_windows,
                    })

                processar_duimp.delay(consulta.pk, None, None, 'windows_store', cert_thumbprint)
            else:
                if not ConfiguracaoAPI.objects.exists():
                    consulta.delete()
                    messages.error(
                        request,
                        'Configure as chaves de acesso ao Portal Único antes de consultar DUIMPs por chave.'
                    )
                    return redirect('declaracoes:configurar_api')
                processar_duimp.delay(consulta.pk, None, None, 'chave', None)

            registrar_log('INFO', 'CONSULTA_DUIMP_CRIADA', f'Consulta DUIMP {numero} criada.', referencia=numero, usuario=request.user)

        messages.success(request, f'{tipo} {numero} adicionada à fila de processamento.')
        return redirect('declaracoes:resultado', pk=consulta.pk)


class ResultadoView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'

    def get(self, request, pk: int):
        consulta = get_object_or_404(ConsultaDeclaracao, pk=pk)
        if not _consulta_visivel_para_usuario(consulta, request.user):
            return HttpResponseForbidden('Sem permissão para visualizar esta consulta.')

        itens = consulta.itens.order_by('num_adicao', 'sequencial')
        return render(request, 'declaracoes/resultado.html', {'consulta': consulta, 'itens': itens})


class StatusConsultaView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'

    def get(self, request, pk: int):
        consulta = get_object_or_404(ConsultaDeclaracao, pk=pk)
        if not _consulta_visivel_para_usuario(consulta, request.user):
            return JsonResponse({'erro': 'sem permissão'}, status=403)

        return JsonResponse({
            'status': consulta.status,
            'status_display': consulta.get_status_display(),
            'total_itens': consulta.itens.count(),
            'mensagem_erro': consulta.mensagem_erro,
            'excel_url': consulta.excel_file.url if consulta.excel_file else None,
        })


class DownloadExcelView(LoginRequiredMixin, View):
    login_url = 'declaracoes:login'

    def get(self, request, pk: int):
        consulta = get_object_or_404(ConsultaDeclaracao, pk=pk)
        if not _consulta_visivel_para_usuario(consulta, request.user):
            return HttpResponseForbidden('Sem permissão para baixar este arquivo.')

        if not consulta.excel_file:
            raise Http404('Arquivo Excel ainda não gerado.')

        file_path = consulta.excel_file.path
        content_type = mimetypes.guess_type(file_path)[0] or 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        nome = f'{consulta.tipo}_{consulta.numero}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{nome}"'
        return response
