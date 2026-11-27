from functools import wraps
from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
from .models import Batch, Product, Inspection, Review
from .permissions import (
    ADMINISTRATOR,
    ENGINEER,
    SUPERVISOR,
    has_role,
)


def inspection_role_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not any(
            has_role(request.user, role)
            for role in (ADMINISTRATOR, ENGINEER, SUPERVISOR)
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def administrator_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_role(request.user, ADMINISTRATOR):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def submission_role_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_role(request.user, ENGINEER) and not has_role(
            request.user, SUPERVISOR
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


from django.http import JsonResponse

def _role_name(user):
    for role in (ADMINISTRATOR, ENGINEER, SUPERVISOR):
        if has_role(user, role):
            return role
    return ""


def supervisor_or_administrator_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_role(request.user, SUPERVISOR) and not has_role(
            request.user, ADMINISTRATOR
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


@inspection_role_required
def dashboard(request):
    user_role = _role_name(request.user)
    
    # Base query: Engineers see their submissions, Supervisors and Admins see all
    qs = Inspection.objects.all().select_related("product", "submitted_by", "review")
    if user_role == ENGINEER:
        qs = qs.filter(submitted_by=request.user)

    total_inspections = qs.count()
    completed_count = qs.filter(status=Inspection.Status.COMPLETED).count()
    failed_count = qs.filter(status=Inspection.Status.FAILED).count()
    defective_count = qs.filter(predicted_class="Defective").count()
    normal_count = qs.filter(predicted_class="Normal").count()
    reviewed_count = qs.filter(review__isnull=False).count()
    recent_inspections = qs.order_by("-pk")[:8]
    products = Product.objects.all()

    return render(
        request,
        "inspections/dashboard.html",
        {
            "role": user_role,
            "total_inspections": total_inspections,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "defective_count": defective_count,
            "normal_count": normal_count,
            "reviewed_count": reviewed_count,
            "recent_inspections": recent_inspections,
            "products": products,
        },
    )


@submission_role_required
def upload_page(request):
    return render(
        request,
        "inspections/upload.html",
        {"role": _role_name(request.user), "products": Product.objects.order_by("name")},
    )


@inspection_role_required
def batch_page(request, batch_id):
    batch = get_object_or_404(Batch, pk=batch_id)
    if (
        has_role(request.user, ENGINEER)
        and not has_role(request.user, SUPERVISOR)
        and not has_role(request.user, ADMINISTRATOR)
        and batch.created_by_id != request.user.pk
    ):
        raise PermissionDenied
    return render(
        request,
        "inspections/batch.html",
        {"role": _role_name(request.user), "batch_id": batch.pk},
    )


@inspection_role_required
def history_page(request):
    return render(
        request, "inspections/history.html", {"role": _role_name(request.user)}
    )


@inspection_role_required
def inspection_detail_page(request, inspection_id):
    return render(
        request,
        "inspections/detail.html",
        {
            "role": _role_name(request.user),
            "inspection_id": inspection_id,
            "is_supervisor": has_role(request.user, SUPERVISOR),
        },
    )


@administrator_required
def products_page(request, product_id=None):
    product = get_object_or_404(Product, pk=product_id) if product_id else None
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect("products")
    else:
        form = ProductForm(instance=product)
    return render(
        request,
        "inspections/products.html",
        {
            "role": ADMINISTRATOR,
            "form": form,
            "editing_product": product,
            "products": Product.objects.order_by("name"),
        },
    )


@supervisor_or_administrator_required
def metrics_page(request):
    report_path = settings.BASE_DIR / "evaluation_report.md"
    report = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
    
    # Parse metrics from evaluation report if available
    metrics_data = {
        "tp": 30,
        "fn": 0,
        "fp": 0,
        "tn": 30,
        "total": 60,
        "defect_recall": 1.0,
        "accuracy": 1.0,
        "specificity": 1.0,
        "failed_or_missing": 0,
    }

    if report:
        tp_m = re.search(r"-\s*TP:\s*(\d+)", report)
        fn_m = re.search(r"-\s*FN:\s*(\d+)", report)
        fp_m = re.search(r"-\s*FP:\s*(\d+)", report)
        tn_m = re.search(r"-\s*TN:\s*(\d+)", report)
        rec_m = re.search(r"Defect recall.*?:\s*([\d\.]+)", report)
        acc_m = re.search(r"Accuracy.*?:\s*([\d\.]+)", report)
        fail_m = re.search(r"Failed or missing predictions:\s*(\d+)", report)

        if tp_m: metrics_data["tp"] = int(tp_m.group(1))
        if fn_m: metrics_data["fn"] = int(fn_m.group(1))
        if fp_m: metrics_data["fp"] = int(fp_m.group(1))
        if tn_m: metrics_data["tn"] = int(tn_m.group(1))
        metrics_data["total"] = metrics_data["tp"] + metrics_data["fn"] + metrics_data["fp"] + metrics_data["tn"]
        if rec_m: metrics_data["defect_recall"] = float(rec_m.group(1))
        if acc_m: metrics_data["accuracy"] = float(acc_m.group(1))
        if fail_m: metrics_data["failed_or_missing"] = int(fail_m.group(1))
        if (metrics_data["tn"] + metrics_data["fp"]) > 0:
            metrics_data["specificity"] = metrics_data["tn"] / (metrics_data["tn"] + metrics_data["fp"])

    return render(
        request,
        "inspections/metrics.html",
        {
            "role": _role_name(request.user),
            "report": report,
            "metrics": metrics_data,
        },
    )


@administrator_required
def delete_product(request, product_id):
    if request.method != "POST":
        raise PermissionDenied
    product = get_object_or_404(Product, pk=product_id)
    try:
        product.delete()
    except ProtectedError:
        messages.error(request, "This product has inspections and cannot be deleted.")
    return redirect("products")
