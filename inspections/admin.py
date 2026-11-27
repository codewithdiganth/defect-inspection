from django.contrib import admin

from .models import Batch, Inspection, Product, Review
from .permissions import ADMINISTRATOR, has_role


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("product_id", "name", "description")
    search_fields = ("product_id", "name")

    def has_module_permission(self, request):
        return has_role(request.user, ADMINISTRATOR)

    def has_view_permission(self, request, obj=None):
        return has_role(request.user, ADMINISTRATOR)

    def has_add_permission(self, request):
        return has_role(request.user, ADMINISTRATOR)

    def has_change_permission(self, request, obj=None):
        return has_role(request.user, ADMINISTRATOR)

    def has_delete_permission(self, request, obj=None):
        return has_role(request.user, ADMINISTRATOR)


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "submitted_by",
        "status",
        "predicted_class",
        "created_at",
    )
    list_filter = ("status", "predicted_class", "created_at")
    readonly_fields = (
        "predicted_class",
        "confidence",
        "defect_probability",
        "model_version",
    )


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "created_by", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("inspection", "reviewed_class", "reviewer", "reviewed_at")
    readonly_fields = ("reviewed_at",)
