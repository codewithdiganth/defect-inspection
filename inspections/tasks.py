from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .inference import run_inference
from .models import Inspection


@shared_task
def process_inspection(inspection_id):
    try:
        with transaction.atomic():
            inspection = Inspection.objects.select_for_update().get(pk=inspection_id)
            if inspection.status != Inspection.Status.QUEUED:
                return (
                    f"Skipped inspection {inspection_id} with status "
                    f"{inspection.status}."
                )
            inspection.status = Inspection.Status.PROCESSING
            inspection.error_message = ""
            inspection.save(
                update_fields=("status", "error_message", "updated_at")
            )

        predicted_class, confidence, defect_probability, model_version = run_inference(
            inspection.image.path
        )
        inspection.predicted_class = predicted_class
        inspection.confidence = confidence
        inspection.defect_probability = defect_probability
        inspection.model_version = model_version
        inspection.status = Inspection.Status.COMPLETED
        inspection.error_message = ""
        inspection.save(
            update_fields=(
                "predicted_class",
                "confidence",
                "defect_probability",
                "model_version",
                "status",
                "error_message",
                "updated_at",
            )
        )
    except Exception as error:
        message = str(error).strip() or error.__class__.__name__
        Inspection.objects.filter(pk=inspection_id).update(
            status=Inspection.Status.FAILED,
            error_message=f"Inference failed: {message}",
            updated_at=timezone.now(),
        )
