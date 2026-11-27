from django.db import models
from django.conf import settings


class Product(models.Model):
    product_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Batch(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspection_batches",
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="batches"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Batch {self.pk}"


class Inspection(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="inspections"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspections",
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="inspections",
        null=True,
        blank=True,
    )
    image = models.ImageField(
        upload_to="inspections/%Y/%m/%d/", blank=True, null=True
    )
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED
    )
    error_message = models.TextField(blank=True)
    predicted_class = models.CharField(
        max_length=20,
        choices=(("Normal", "Normal"), ("Defective", "Defective")),
        blank=True,
        null=True,
    )
    confidence = models.FloatField(null=True, blank=True)
    defect_probability = models.FloatField(null=True, blank=True)
    model_version = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Inspection {self.pk} ({self.status})"

    def save(self, *args, **kwargs):
        prediction_fields = (
            "predicted_class",
            "confidence",
            "defect_probability",
            "model_version",
        )
        if self.pk:
            previous = (
                type(self).objects.filter(pk=self.pk)
                .values("status", *prediction_fields)
                .first()
            )
            has_prediction = previous and (
                previous["status"] == self.Status.COMPLETED
                or any(previous[field] not in (None, "") for field in prediction_fields)
            )
            if has_prediction and any(
                previous[field] != getattr(self, field)
                for field in prediction_fields
            ):
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    "Original model prediction fields cannot be changed."
                )
        super().save(*args, **kwargs)


class Review(models.Model):
    class ReviewedClass(models.TextChoices):
        NORMAL = "Normal", "Normal"
        DEFECTIVE = "Defective", "Defective"

    inspection = models.OneToOneField(
        Inspection, on_delete=models.CASCADE, related_name="review"
    )
    reviewed_class = models.CharField(max_length=20, choices=ReviewedClass.choices)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspection_reviews",
    )
    comment = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for inspection {self.inspection_id}"
