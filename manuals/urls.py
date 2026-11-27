from django.urls import path
from . import views

urlpatterns = [
    path('', views.manual_list, name='manual-list'),
    path('upload/', views.manual_upload, name='manual-upload'),
    path('<int:pk>/', views.manual_detail, name='manual-detail'),
]
