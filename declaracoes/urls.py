from django.urls import path

from . import views

app_name = 'declaracoes'

urlpatterns = [
    path('setup/', views.SetupInicialView.as_view(), name='setup_inicial'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('', views.IndexView.as_view(), name='index'),
    path('historico/', views.HistoricoView.as_view(), name='historico'),
    path('logs/', views.LogsView.as_view(), name='logs'),
    path('usuarios/', views.UsuariosView.as_view(), name='usuarios'),
    path('configurar/', views.ConfigurarAPIView.as_view(), name='configurar_api'),
    path('nova/', views.NovaConsultaView.as_view(), name='nova_consulta'),
    path('resultado/<int:pk>/', views.ResultadoView.as_view(), name='resultado'),
    path('status/<int:pk>/', views.StatusConsultaView.as_view(), name='status'),
    path('download/<int:pk>/', views.DownloadExcelView.as_view(), name='download_excel'),
]
