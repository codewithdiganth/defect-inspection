"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.urls import include, path


from inspections import views as page_views
from inspections.api_views import (
    BatchStatusView,
    InspectionHistoryView,
    InspectionReviewView,
    InspectionStatusView,
    InspectionUploadView,
    ProductDetailView,
    ProductListView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="inspections/login.html",
            redirect_authenticated_user=True,
            next_page=reverse_lazy("dashboard"),
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", page_views.dashboard, name="dashboard"),
    path("upload/", page_views.upload_page, name="upload"),
    path("batches/<int:batch_id>/", page_views.batch_page, name="batch-page"),
    path("history/", page_views.history_page, name="history"),
    path("metrics/", page_views.metrics_page, name="metrics"),
    path(
        "inspections/<int:inspection_id>/",
        page_views.inspection_detail_page,
        name="inspection-detail-page",
    ),
    path("products/", page_views.products_page, name="products"),
    path(
        "products/<int:product_id>/edit/",
        page_views.products_page,
        name="product-edit",
    ),
    path(
        "products/<int:product_id>/delete/",
        page_views.delete_product,
        name="product-delete",
    ),
    path("api/inspections/", InspectionUploadView.as_view(), name="inspection-upload"),
    path(
        "api/inspections/history/",
        InspectionHistoryView.as_view(),
        name="inspection-history",
    ),
    path(
        "api/inspections/<int:inspection_id>/",
        InspectionStatusView.as_view(),
        name="inspection-status",
    ),
    path(
        "api/inspections/<int:inspection_id>/review/",
        InspectionReviewView.as_view(),
        name="inspection-review",
    ),
    path(
        "api/batches/<int:batch_id>/",
        BatchStatusView.as_view(),
        name="batch-status",
    ),
    path("manuals/", include(("manuals.urls", "manuals"), namespace="manuals")),

    path(
        "api/products/<int:product_id>/",
        ProductDetailView.as_view(),
        name="product-detail",
    ),
]
