from django.urls import path
from . import views
urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('admin-dashboard/', views.admin_dashboard),
    path('engineer/', views.engineer_view),
    path('supervisor/', views.supervisor_view),
    path('api/machines/', views.api_add_machine),
    path('api/manuals/upload/', views.api_upload_manual),
    path('api/ask/', views.api_ask),
    path('api/history/', views.api_history),
]
