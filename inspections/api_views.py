from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Batch, Inspection, Product, Review
from .product_serializers import ProductSerializer
from .permissions import (
    ADMINISTRATOR,
    ENGINEER,
    SUPERVISOR,
    CanViewInspections,
    IsEngineerOrSupervisor,
    IsAdministrator,
    IsSupervisor,
)
from .serializers import (
    BatchStatusSerializer,
    InspectionDetailSerializer,
    InspectionHistorySerializer,
    InspectionStatusSerializer,
    ReviewWriteSerializer,
)
from .tasks import process_inspection
from .validation import (
    ImageValidationError,
    validate_batch_size,
    validate_image,
)
from rest_framework.pagination import PageNumberPagination


class InspectionHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class InspectionUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def get_permissions(self):
        role_permission = (
            CanViewInspections()
            if self.request.method == "GET"
            else IsEngineerOrSupervisor()
        )
        return [IsAuthenticated(), role_permission]

    def get(self, request):
        return _list_inspections(request)

    def post(self, request):
        files = request.FILES.getlist("files")
        try:
            validate_batch_size(len(files))
        except ImageValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        product_id = request.data.get("product_id")
        if not product_id:
            return Response(
                {"detail": "product_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = Product.objects.filter(product_id=product_id).first()
        if product is None:
            return Response(
                {"detail": "Product not found."}, status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            batch = Batch.objects.create(created_by=request.user, product=product)
            inspections = []
            for uploaded_file in files:
                try:
                    validate_image(uploaded_file)
                except ImageValidationError as error:
                    inspection = Inspection(
                        product=product,
                        submitted_by=request.user,
                        batch=batch,
                        original_filename=uploaded_file.name[:255],
                        status=Inspection.Status.FAILED,
                        error_message=str(error),
                    )
                else:
                    uploaded_file.seek(0)
                    inspection = Inspection(
                        product=product,
                        submitted_by=request.user,
                        batch=batch,
                        image=uploaded_file,
                        original_filename=uploaded_file.name[:255],
                    )
                inspection.save()
                inspections.append(inspection)
                if inspection.status == Inspection.Status.QUEUED:
                    transaction.on_commit(
                        lambda inspection_id=inspection.pk: process_inspection.delay(
                            inspection_id
                        )
                    )

        return Response(
            {
                "id": batch.pk,
                "inspections": InspectionStatusSerializer(
                    inspections, many=True, context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class InspectionStatusView(APIView):
    permission_classes = (IsAuthenticated, CanViewInspections)

    def get(self, request, inspection_id):
        inspections = _role_scoped_inspections(request.user)
        inspection = get_object_or_404(inspections, pk=inspection_id)
        return Response(
            InspectionDetailSerializer(
                inspection, context={"request": request}
            ).data
        )


class InspectionHistoryView(APIView):
    permission_classes = (IsAuthenticated, CanViewInspections)

    def get(self, request):
        return _list_inspections(request)


class InspectionReviewView(APIView):
    permission_classes = (IsAuthenticated, IsSupervisor)

    def post(self, request, inspection_id):
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            inspection = get_object_or_404(
                Inspection.objects.select_for_update(), pk=inspection_id
            )
            if inspection.status != Inspection.Status.COMPLETED:
                return Response(
                    {"detail": "Only completed inspections can be reviewed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            review, created = Review.objects.update_or_create(
                inspection=inspection,
                defaults={
                    "reviewed_class": serializer.validated_data["reviewed_class"],
                    "reviewer": request.user,
                    "comment": serializer.validated_data.get("comment", ""),
                    "reviewed_at": timezone.now(),
                },
            )
        response_serializer = InspectionDetailSerializer(
            inspection, context={"request": request}
        )
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BatchStatusView(APIView):
    permission_classes = (IsAuthenticated, CanViewInspections)

    def get(self, request, batch_id):
        batches = Batch.objects.prefetch_related("inspections")
        if _is_engineer_only(request.user):
            batches = batches.filter(created_by=request.user)
        batch = get_object_or_404(batches, pk=batch_id)
        return Response(BatchStatusSerializer(batch).data)


class ProductListView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get_permissions(self):
        role_permission = IsAdministrator() if self.request.method == "POST" else None
        permissions = [IsAuthenticated()]
        if role_permission is not None:
            permissions.append(role_permission)
        return permissions

    def get(self, request):
        products = Product.objects.order_by("name", "product_id")
        return Response(ProductSerializer(products, many=True).data)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(
            ProductSerializer(product).data, status=status.HTTP_201_CREATED
        )


class ProductDetailView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method != "GET":
            permissions.append(IsAdministrator())
        return permissions

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        return Response(ProductSerializer(product).data)

    def put(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        serializer = ProductSerializer(product, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        try:
            product.delete()
        except ProtectedError:
            return Response(
                {"detail": "Product has inspections and cannot be deleted."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


def _is_engineer_only(user):
    return (
        user.groups.filter(name=ENGINEER).exists()
        and not user.groups.filter(name__in=(ADMINISTRATOR, SUPERVISOR)).exists()
    )


def _role_scoped_inspections(user):
    inspections = Inspection.objects.select_related(
        "product", "submitted_by", "review__reviewer"
    )
    if _is_engineer_only(user):
        return inspections.filter(submitted_by=user)
    return inspections


def _list_inspections(request):
    inspections = _role_scoped_inspections(request.user)
    filters = {
        "prediction": ("predicted_class", {"Normal", "Defective"}),
        "status": ("status", set(Inspection.Status.values)),
        "review_status": ("review_status", {"pending", "reviewed"}),
    }
    for parameter, (field, allowed_values) in filters.items():
        value = request.query_params.get(parameter)
        if value is None or value == "":
            continue
        if value not in allowed_values:
            return Response(
                {"detail": f"Invalid {parameter} filter."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if field == "review_status":
            inspections = inspections.filter(review__isnull=(value == "pending"))
        else:
            inspections = inspections.filter(**{field: value})

    batch_id = request.query_params.get("batch")
    if batch_id:
        try:
            batch_id = int(batch_id)
        except ValueError:
            return Response(
                {"detail": "batch must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if batch_id < 1:
            return Response(
                {"detail": "batch must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inspections = inspections.filter(batch_id=batch_id)

    paginator = InspectionHistoryPagination()
    page = paginator.paginate_queryset(
        inspections.order_by("-created_at", "-pk"), request
    )
    serializer = InspectionHistorySerializer(
        page, many=True, context={"request": request}
    )
    return paginator.get_paginated_response(serializer.data)
