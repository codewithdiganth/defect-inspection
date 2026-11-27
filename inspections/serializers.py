from rest_framework import serializers

from .models import Batch, Inspection, Review


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.CharField(source="reviewer.username", read_only=True)

    class Meta:
        model = Review
        fields = ("reviewed_class", "reviewer", "comment", "reviewed_at")
        read_only_fields = fields


class ReviewWriteSerializer(serializers.Serializer):
    reviewed_class = serializers.ChoiceField(choices=Review.ReviewedClass.choices)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class InspectionHistorySerializer(serializers.ModelSerializer):
    product_id = serializers.CharField(source="product.product_id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    submitted_by = serializers.CharField(source="submitted_by.username", read_only=True)
    image_url = serializers.SerializerMethodField()
    review_status = serializers.SerializerMethodField()
    reviewer = serializers.SerializerMethodField()
    review = ReviewSerializer(read_only=True)

    class Meta:
        model = Inspection
        fields = (
            "id",
            "product_id",
            "product_name",
            "submitted_by",
            "original_filename",
            "image_url",
            "status",
            "error_message",
            "predicted_class",
            "confidence",
            "defect_probability",
            "model_version",
            "review_status",
            "reviewer",
            "review",
            "created_at",
        )
        read_only_fields = fields

    def get_image_url(self, inspection):
        if not inspection.image:
            return None
        request = self.context.get("request")
        url = inspection.image.url
        return request.build_absolute_uri(url) if request else url

    def get_review_status(self, inspection):
        return "reviewed" if hasattr(inspection, "review") else "pending"

    def get_reviewer(self, inspection):
        if not hasattr(inspection, "review"):
            return None
        return inspection.review.reviewer.username


class InspectionDetailSerializer(InspectionHistorySerializer):
    review = ReviewSerializer(read_only=True)

    class Meta(InspectionHistorySerializer.Meta):
        fields = InspectionHistorySerializer.Meta.fields


class InspectionStatusSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Inspection
        fields = (
            "id",
            "original_filename",
            "image_url",
            "status",
            "error_message",
            "predicted_class",
            "confidence",
            "defect_probability",
            "model_version",
            "created_at",
        )
        read_only_fields = fields

    def get_image_url(self, inspection):
        if not inspection.image:
            return None
        request = self.context.get("request")
        url = inspection.image.url
        return request.build_absolute_uri(url) if request else url


class BatchStatusSerializer(serializers.ModelSerializer):
    inspections = InspectionStatusSerializer(many=True, read_only=True)
    product_id = serializers.CharField(source="product.product_id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Batch
        fields = ("id", "product_id", "product_name", "created_at", "inspections")
        read_only_fields = fields
