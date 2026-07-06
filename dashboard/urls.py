from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='dashboard'),
    path('preparo/', views.preparo_page, name='preparo'),
    path('preparo/google/conectar/', views.preparo_google_connect, name='preparo_google_connect'),
    path('preparo/google/callback/', views.preparo_google_callback, name='preparo_google_callback'),
    path('preparo/google/desconectar/', views.preparo_google_disconnect, name='preparo_google_disconnect'),
    path('membros/', views.member_list, name='membros'),
    path('membros/novo/', views.member_create, name='membro_create'),
    path('membros/<int:pk>/editar/', views.member_update, name='membro_update'),
    path('membros/<int:pk>/excluir/', views.member_delete, name='membro_delete'),
    path('<slug:team_slug>/tarefas/nova/', views.task_create, name='task_create'),
    path('tarefas/<int:pk>/editar/', views.task_update, name='task_update'),
    path('tarefas/<int:pk>/excluir/', views.task_delete, name='task_delete'),
    path('eventos/', views.team_page, {'team_slug': 'eventos'}, name='eventos'),
    path('logistica/', views.team_page, {'team_slug': 'logistica'}, name='logistica'),
    path('aconselhamento/', views.team_page, {'team_slug': 'aconselhamento'}, name='aconselhamento'),
    path('programa/', views.team_page, {'team_slug': 'programa'}, name='programa'),
    path('lojinha-e-cantina/', views.team_page, {'team_slug': 'lojinha_cantina'}, name='lojinha_cantina'),
    path('oracao/', views.team_page, {'team_slug': 'oracao'}, name='oracao'),
    path('comunicacao/', views.team_page, {'team_slug': 'comunicacao'}, name='comunicacao'),
    path('administracao/', views.team_page, {'team_slug': 'administracao'}, name='administracao'),
    path('financeiro/', views.team_page, {'team_slug': 'financeiro'}, name='financeiro'),
    path('materiais/', views.team_page, {'team_slug': 'materiais'}, name='materiais'),
    path('pessoal/', views.team_page, {'team_slug': 'pessoal'}, name='pessoal'),
    path('<slug:team_slug>/membros/novo/', views.team_member_create, name='team_member_create'),
]
