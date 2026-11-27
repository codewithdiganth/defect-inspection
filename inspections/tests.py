import csv
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from inspections.admin import ProductAdmin
from inspections.inference import run_inference
from inspections.models import Batch, Inspection, Product, Review
from inspections.permissions import (
    ADMINISTRATOR,
    ENGINEER,
    SUPERVISOR,
    has_role,
)
from django.urls import reverse
from inspections.validation import (
    ImageValidationError,
    validate_batch_size,
    validate_image,
)
from inspections.tasks import process_inspection


def image_bytes(image_format="PNG", size=(128, 128), exif=None, color="red"):
    image = Image.new("RGB", size, color=color)
    output = BytesIO()
    if exif is None:
        image.save(output, format=image_format)
    else:
        image.save(output, format=image_format, exif=exif)
    return output.getvalue()


class SeedDemoTests(TestCase):
    def test_seed_demo_creates_roles_users_and_product(self):
        call_command("seed_demo", stdout=StringIO())

        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)),
            {ADMINISTRATOR, ENGINEER, SUPERVISOR},
        )
        user_model = get_user_model()
        admin_user = user_model.objects.get(username="admin1")
        engineer = user_model.objects.get(username="eng1")
        supervisor = user_model.objects.get(username="sup1")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.check_password("Demo@12345"))
        self.assertTrue(has_role(admin_user, ADMINISTRATOR))
        self.assertTrue(has_role(engineer, ENGINEER))
        self.assertTrue(has_role(supervisor, SUPERVISOR))
        self.assertEqual(
            Product.objects.get(product_id="P-PLATE01").name,
            "Demonstration metal plate",
        )

    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())

        self.assertEqual(get_user_model().objects.filter(username="eng1").count(), 1)
        self.assertEqual(Product.objects.filter(product_id="P-PLATE01").count(), 1)

    def test_only_administrator_role_can_manage_products_in_admin(self):
        call_command("seed_demo", stdout=StringIO())
        model_admin = ProductAdmin(Product, admin.site)
        request = RequestFactory().get("/admin/inspections/product/")

        request.user = get_user_model().objects.get(username="admin1")
        self.assertTrue(model_admin.has_module_permission(request))
        self.assertTrue(model_admin.has_add_permission(request))
        self.assertTrue(model_admin.has_change_permission(request))
        self.assertTrue(model_admin.has_delete_permission(request))

        request.user = get_user_model().objects.get(username="eng1")
        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_product_model_permissions_are_assigned_only_to_administrator(self):
        call_command("seed_demo", stdout=StringIO())
        administrator = Group.objects.get(name=ADMINISTRATOR)
        product_permissions = administrator.permissions.filter(
            content_type__app_label="inspections",
            content_type__model="product",
        )
        self.assertEqual(
            set(product_permissions.values_list("codename", flat=True)),
            {"add_product", "change_product", "delete_product", "view_product"},
        )
        for role in (ENGINEER, SUPERVISOR):
            self.assertFalse(
                Group.objects.get(name=role)
                .permissions.filter(
                    content_type__app_label="inspections",
                    content_type__model="product",
                )
                .exists()
            )


class ImageValidationTests(TestCase):
    def test_accepts_png_content_even_when_filename_and_content_type_disagree(self):
        uploaded_file = SimpleUploadedFile(
            "misleading.jpg", image_bytes(), content_type="text/plain"
        )

        result = validate_image(uploaded_file)

        self.assertEqual(
            (result.image_format, result.width, result.height), ("PNG", 128, 128)
        )
        self.assertEqual(uploaded_file.tell(), 0)

    def test_accepts_jpeg_content(self):
        result = validate_image(BytesIO(image_bytes("JPEG")))

        self.assertEqual(result.image_format, "JPEG")

    def test_rejects_non_image_content(self):
        with self.assertRaisesMessage(
            ImageValidationError, "File is not a valid JPEG or PNG image"
        ):
            validate_image(BytesIO(b"not an image"))

    def test_rejects_truncated_png(self):
        truncated_png = image_bytes()[:-16]

        with self.assertRaisesMessage(
            ImageValidationError, "Image is truncated or corrupt"
        ):
            validate_image(BytesIO(truncated_png))

    def test_rejects_unsupported_decoded_format(self):
        with self.assertRaisesMessage(
            ImageValidationError, "File is not a valid JPEG or PNG image"
        ):
            validate_image(BytesIO(image_bytes("GIF")))

    def test_rejects_empty_file(self):
        with self.assertRaisesMessage(ImageValidationError, "File is empty"):
            validate_image(BytesIO(b""))

    def test_rejects_oversized_file_before_decoding(self):
        oversized_file = BytesIO(b"x" * (5 * 1024 * 1024 + 1))

        with self.assertRaisesMessage(
            ImageValidationError, "File exceeds 5 MiB; maximum is 5 MiB"
        ):
            validate_image(oversized_file)

    def test_rejects_dimensions_below_minimum(self):
        with self.assertRaisesMessage(
            ImageValidationError,
            "Image is 32x32; each dimension must be between 64 and 4096 pixels",
        ):
            validate_image(BytesIO(image_bytes(size=(32, 32))))

    def test_rejects_dimensions_above_maximum(self):
        with self.assertRaisesMessage(
            ImageValidationError,
            "Image is 4097x64; each dimension must be between 64 and 4096 pixels",
        ):
            validate_image(BytesIO(image_bytes(size=(4097, 64))))

    def test_checks_dimensions_after_exif_orientation(self):
        exif = Image.Exif()
        exif[274] = 6

        result = validate_image(BytesIO(image_bytes("JPEG", (100, 80), exif)))

        self.assertEqual((result.width, result.height), (80, 100))

    def test_rejects_batch_sizes_outside_one_to_ten(self):
        for count in (0, 11):
            with self.subTest(count=count), self.assertRaisesMessage(
                ImageValidationError, "Batch must contain between 1 and 10 files."
            ):
                validate_batch_size(count)

    def test_accepts_batch_sizes_one_through_ten(self):
        for count in range(1, 11):
            with self.subTest(count=count):
                validate_batch_size(count)


class SharedInferenceTests(TestCase):
    def test_normalizes_supplied_model_dictionary_after_validating_image(self):
        image_path = Path("validated-sample.png")
        prediction = {
            "predicted_class": "Defective",
            "confidence": 0.81,
            "defect_probability": 0.81,
            "model_version": "BIT-PLATE-CV-1.0",
        }
        with patch("builtins.open", return_value=BytesIO(image_bytes())) as open_file:
            with patch(
                "inspections.inference._load_predict", return_value=lambda path: prediction
            ) as load_predict:
                result = run_inference(image_path)

        self.assertEqual(
            result,
            ("Defective", 0.81, 0.81, "BIT-PLATE-CV-1.0"),
        )
        open_file.assert_called_once_with(image_path, "rb")
        load_predict.assert_called_once()

    def test_rejects_bad_image_before_loading_or_calling_model(self):
        with patch("builtins.open", return_value=BytesIO(b"not an image")):
            with patch("inspections.inference._load_predict") as load_predict:
                with self.assertRaises(ImageValidationError):
                    run_inference(Path("untrusted.jpg"))

        load_predict.assert_not_called()


class InspectionUploadTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.product = Product.objects.create(
            product_id="P-PLATE01", name="Demonstration metal plate"
        )
        self.engineer_group = Group.objects.create(name=ENGINEER)
        self.user = get_user_model().objects.create_user(
            username="upload-engineer", password="test-password"
        )
        self.user.groups.add(self.engineer_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def upload_file(self, name, content):
        return SimpleUploadedFile(name, content, content_type="application/octet-stream")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("inspections.inference._load_predict")
    def test_mixed_upload_fails_bad_item_and_completes_valid_item(self, load_predict):
        def predict_from_content(path):
            with Image.open(path) as image:
                self.assertEqual(image.convert("RGB").getpixel((0, 0)), (255, 0, 0))
            return "Normal", 0.91, 0.09, "test-model"

        load_predict.return_value = predict_from_content
        files = [
            self.upload_file("valid.png", image_bytes()),
            self.upload_file("fake.jpg", b"not an image"),
        ]

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/inspections/",
                {"product_id": self.product.product_id, "files": files},
                format="multipart",
            )

        self.assertEqual(response.status_code, 201, response.data)
        inspections = list(
            Inspection.objects.filter(batch_id=response.data["id"]).order_by("id")
        )
        self.assertEqual(len(inspections), 2)
        self.assertEqual(
            inspections[0].status,
            Inspection.Status.COMPLETED,
            inspections[0].error_message,
        )
        self.assertEqual(inspections[0].predicted_class, "Normal")
        self.assertEqual(inspections[0].confidence, 0.91)
        self.assertEqual(inspections[0].defect_probability, 0.09)
        self.assertEqual(inspections[0].model_version, "test-model")
        self.assertEqual(inspections[1].status, Inspection.Status.FAILED)
        self.assertIn("not a valid JPEG or PNG", inspections[1].error_message)
        self.assertIsNone(inspections[1].confidence)
        load_predict.assert_called_once()
        persisted = Inspection.objects.get(pk=inspections[0].pk)
        self.assertEqual(persisted.product, self.product)
        self.assertEqual(persisted.submitted_by, self.user)
        self.assertEqual(persisted.original_filename, "valid.png")
        self.assertTrue(persisted.image.name)
        self.assertEqual(persisted.predicted_class, "Normal")
        self.assertEqual(persisted.confidence, 0.91)
        self.assertEqual(persisted.defect_probability, 0.09)
        self.assertEqual(persisted.model_version, "test-model")
        self.assertIsNotNone(persisted.created_at)

    def test_rejects_empty_and_oversized_batches(self):
        empty_response = self.client.post(
            "/api/inspections/",
            {"product_id": self.product.product_id},
            format="multipart",
        )
        oversized_response = self.client.post(
            "/api/inspections/",
            {
                "product_id": self.product.product_id,
                "files": [
                    self.upload_file(f"{index}.png", image_bytes())
                    for index in range(11)
                ],
            },
            format="multipart",
        )

        self.assertEqual(empty_response.status_code, 400)
        self.assertIn("between 1 and 10", empty_response.data["detail"])
        self.assertEqual(oversized_response.status_code, 400)
        self.assertEqual(Batch.objects.count(), 0)

    def test_engineer_can_poll_only_their_own_inspection(self):
        another_user = get_user_model().objects.create_user(username="other-engineer")
        batch = Batch.objects.create(created_by=another_user, product=self.product)
        other_inspection = Inspection.objects.create(
            product=self.product,
            submitted_by=another_user,
            batch=batch,
            original_filename="private.png",
            status=Inspection.Status.FAILED,
            error_message="invalid",
        )

        response = self.client.get(f"/api/inspections/{other_inspection.pk}/")

        self.assertEqual(response.status_code, 404)

    @patch("inspections.tasks.run_inference")
    def test_duplicate_task_delivery_does_not_change_completed_prediction(
        self, run_inference_mock
    ):
        batch = Batch.objects.create(created_by=self.user, product=self.product)
        inspection = Inspection.objects.create(
            product=self.product,
            submitted_by=self.user,
            batch=batch,
            original_filename="already-completed.png",
            status=Inspection.Status.COMPLETED,
            predicted_class="Normal",
            confidence=0.93,
            defect_probability=0.07,
            model_version="test-model",
        )

        result = process_inspection.run(inspection.pk)

        self.assertIn("Skipped inspection", result)
        run_inference_mock.assert_not_called()
        inspection.refresh_from_db()
        self.assertEqual(inspection.status, Inspection.Status.COMPLETED)
        self.assertEqual(inspection.predicted_class, "Normal")
        self.assertEqual(inspection.confidence, 0.93)
        self.assertEqual(inspection.defect_probability, 0.07)
        self.assertEqual(inspection.model_version, "test-model")

    @patch("inspections.tasks.run_inference", side_effect=RuntimeError("predictor error"))
    def test_task_exception_fails_queued_item_without_prediction(self, run_inference_mock):
        batch = Batch.objects.create(created_by=self.user, product=self.product)
        inspection = Inspection.objects.create(
            product=self.product,
            submitted_by=self.user,
            batch=batch,
            original_filename="queued.png",
        )
        inspection.image.save(
            "queued.png", self.upload_file("queued.png", image_bytes()), save=True
        )

        process_inspection.run(inspection.pk)

        inspection.refresh_from_db()
        self.assertEqual(inspection.status, Inspection.Status.FAILED)
        self.assertEqual(inspection.error_message, "Inference failed: predictor error")
        self.assertIsNone(inspection.predicted_class)
        self.assertIsNone(inspection.confidence)
        self.assertIsNone(inspection.defect_probability)
        self.assertEqual(inspection.model_version, "")
        run_inference_mock.assert_called_once()


class InspectionReviewAndHistoryTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            product_id="P-PLATE01", name="Demonstration metal plate"
        )
        self.engineer_group = Group.objects.create(name=ENGINEER)
        self.supervisor_group = Group.objects.create(name=SUPERVISOR)
        self.engineer = get_user_model().objects.create_user(username="history-engineer")
        self.engineer.groups.add(self.engineer_group)
        self.other_engineer = get_user_model().objects.create_user(
            username="another-history-engineer"
        )
        self.other_engineer.groups.add(self.engineer_group)
        self.supervisor = get_user_model().objects.create_user(
            username="history-supervisor"
        )
        self.supervisor.groups.add(self.supervisor_group)
        self.client = APIClient()
        self.batch = Batch.objects.create(created_by=self.engineer, product=self.product)
        self.completed_inspection = self.create_inspection(
            self.engineer,
            self.batch,
            status=Inspection.Status.COMPLETED,
            predicted_class="Normal",
            confidence=0.91,
            defect_probability=0.09,
            model_version="test-model",
        )

    def create_inspection(self, user, batch, **overrides):
        values = {
            "product": self.product,
            "submitted_by": user,
            "batch": batch,
            "image": "",
            "original_filename": "inspection.png",
            "status": Inspection.Status.FAILED,
        }
        values.update(overrides)
        return Inspection.objects.create(**values)

    def test_engineer_review_request_is_forbidden_without_changes(self):
        self.client.force_authenticate(self.engineer)
        original_values = (
            self.completed_inspection.predicted_class,
            self.completed_inspection.confidence,
            self.completed_inspection.defect_probability,
            self.completed_inspection.model_version,
        )

        response = self.client.post(
            f"/api/inspections/{self.completed_inspection.pk}/review/",
            {"reviewed_class": "Defective", "comment": "manual check"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Review.objects.filter(inspection=self.completed_inspection).exists())
        self.completed_inspection.refresh_from_db()
        self.assertEqual(
            (
                self.completed_inspection.predicted_class,
                self.completed_inspection.confidence,
                self.completed_inspection.defect_probability,
                self.completed_inspection.model_version,
            ),
            original_values,
        )

    def test_supervisor_can_create_and_update_review_without_changing_prediction(self):
        self.client.force_authenticate(self.supervisor)
        original_values = (
            self.completed_inspection.predicted_class,
            self.completed_inspection.confidence,
            self.completed_inspection.defect_probability,
            self.completed_inspection.model_version,
        )

        response = self.client.post(
            f"/api/inspections/{self.completed_inspection.pk}/review/",
            {"reviewed_class": "Defective", "comment": "Confirmed defect"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["predicted_class"], "Normal")
        self.assertEqual(response.data["review"]["reviewed_class"], "Defective")
        self.assertEqual(response.data["review"]["reviewer"], self.supervisor.username)
        review = Review.objects.get(inspection=self.completed_inspection)
        self.assertEqual(review.comment, "Confirmed defect")
        self.assertEqual(review.reviewer, self.supervisor)

        response = self.client.post(
            f"/api/inspections/{self.completed_inspection.pk}/review/",
            {"reviewed_class": "Normal", "comment": "Corrected review"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Review.objects.filter(inspection=self.completed_inspection).count(), 1)
        self.assertEqual(
            Review.objects.get(inspection=self.completed_inspection).comment,
            "Corrected review",
        )
        self.completed_inspection.refresh_from_db()
        self.assertEqual(
            (
                self.completed_inspection.predicted_class,
                self.completed_inspection.confidence,
                self.completed_inspection.defect_probability,
                self.completed_inspection.model_version,
            ),
            original_values,
        )

    def test_unauthenticated_review_is_rejected(self):
        response = self.client.post(
            f"/api/inspections/{self.completed_inspection.pk}/review/",
            {"reviewed_class": "Normal"},
            format="json",
        )

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(Review.objects.filter(inspection=self.completed_inspection).exists())

    def test_only_completed_inspections_can_be_reviewed(self):
        queued_inspection = self.create_inspection(
            self.engineer,
            self.batch,
            status=Inspection.Status.QUEUED,
            predicted_class="",
        )
        self.client.force_authenticate(self.supervisor)

        response = self.client.post(
            f"/api/inspections/{queued_inspection.pk}/review/",
            {"reviewed_class": "Normal"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Review.objects.filter(inspection=queued_inspection).exists())

    def test_history_filters_and_engineer_scope(self):
        self.create_inspection(
            self.engineer,
            self.batch,
            status=Inspection.Status.COMPLETED,
            predicted_class="Defective",
            confidence=0.8,
            defect_probability=0.8,
        )
        other_batch = Batch.objects.create(
            created_by=self.other_engineer, product=self.product
        )
        self.create_inspection(
            self.other_engineer,
            other_batch,
            status=Inspection.Status.COMPLETED,
            predicted_class="Normal",
            confidence=0.95,
            defect_probability=0.05,
        )
        Review.objects.create(
            inspection=self.completed_inspection,
            reviewed_class="Normal",
            reviewer=self.supervisor,
        )
        self.client.force_authenticate(self.engineer)

        response = self.client.get(
            "/api/inspections/",
            {
                "prediction": "Normal",
                "review_status": "reviewed",
                "status": "completed",
                "batch": str(self.batch.pk),
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.completed_inspection.pk)
        self.assertEqual(response.data["results"][0]["reviewer"], self.supervisor.username)
        self.assertEqual(
            response.data["results"][0]["review"]["reviewed_class"], "Normal"
        )

    def test_supervisor_sees_all_inspections_and_bad_filter_is_rejected(self):
        other_batch = Batch.objects.create(
            created_by=self.other_engineer, product=self.product
        )
        other_inspection = self.create_inspection(
            self.other_engineer,
            other_batch,
            status=Inspection.Status.COMPLETED,
            predicted_class="Normal",
            confidence=0.95,
            defect_probability=0.05,
        )
        self.client.force_authenticate(self.supervisor)

        response = self.client.get("/api/inspections/")
        invalid_filter_response = self.client.get(
            "/api/inspections/", {"prediction": "unknown"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertIn(
            other_inspection.pk,
            {item["id"] for item in response.data["results"]},
        )
        self.assertEqual(invalid_filter_response.status_code, 400)

    def test_completed_original_prediction_fields_are_immutable(self):
        self.completed_inspection.predicted_class = "Defective"

        with self.assertRaisesMessage(
            ValidationError, "Original model prediction fields cannot be changed."
        ):
            self.completed_inspection.save()

        self.completed_inspection.refresh_from_db()
        self.assertEqual(self.completed_inspection.predicted_class, "Normal")


class FrontendPageTests(TestCase):
    def setUp(self):
        self.administrator_group = Group.objects.create(name=ADMINISTRATOR)
        self.engineer_group = Group.objects.create(name=ENGINEER)
        self.supervisor_group = Group.objects.create(name=SUPERVISOR)
        self.administrator = get_user_model().objects.create_user(
            username="page-admin"
        )
        self.administrator.groups.add(self.administrator_group)
        self.engineer = get_user_model().objects.create_user(username="page-engineer")
        self.engineer.groups.add(self.engineer_group)
        self.supervisor = get_user_model().objects.create_user(
            username="page-supervisor"
        )
        self.supervisor.groups.add(self.supervisor_group)
        self.product = Product.objects.create(
            product_id="P-PLATE01", name="Demonstration metal plate"
        )

    def test_login_page_and_authenticated_dashboard(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')

        self.client.force_login(self.engineer)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "page-engineer")
        self.assertContains(response, ENGINEER)

    def test_engineer_upload_and_history_pages_render(self):
        self.client.force_login(self.engineer)

        upload_response = self.client.get(reverse("upload"))
        history_response = self.client.get(reverse("history"))

        self.assertEqual(upload_response.status_code, 200)
        self.assertContains(upload_response, "inspection-files")
        self.assertContains(upload_response, self.product.name)
        self.assertEqual(history_response.status_code, 200)
        self.assertContains(history_response, "history-filters")
        self.assertNotContains(history_response, "review-modal")

    def test_supervisor_history_page_includes_review_modal(self):
        self.client.force_login(self.supervisor)

        response = self.client.get(reverse("history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "review-modal")
        self.assertContains(response, "Save review")

    def test_only_administrator_can_access_product_management_page(self):
        self.client.force_login(self.engineer)
        denied_response = self.client.get(reverse("products"))
        self.assertEqual(denied_response.status_code, 403)

        self.client.force_login(self.administrator)
        response = self.client.get(reverse("products"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.product_id)

        response = self.client.post(
            reverse("products"),
            {
                "product_id": "P-TEST02",
                "name": "Test part",
                "description": "Product page test",
            },
        )
        self.assertRedirects(response, reverse("products"))
        self.assertTrue(Product.objects.filter(product_id="P-TEST02").exists())

    def test_administrator_cannot_access_upload_page_or_see_upload_actions(self):
        self.client.force_login(self.administrator)

        upload_response = self.client.get(reverse("upload"))
        dashboard_response = self.client.get(reverse("dashboard"))

        self.assertEqual(upload_response.status_code, 403)
        self.assertNotContains(dashboard_response, 'href="/upload/"')

    def test_metrics_page_is_only_visible_to_supervisors_and_administrators(self):
        with TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "evaluation_report.md"
            report_path.write_text("Defect recall: 1.0000", encoding="utf-8")
            with override_settings(BASE_DIR=Path(temporary_directory)):
                self.client.force_login(self.engineer)
                self.assertEqual(self.client.get(reverse("metrics")).status_code, 403)

                self.client.force_login(self.supervisor)
                supervisor_response = self.client.get(reverse("metrics"))
                self.assertEqual(supervisor_response.status_code, 200)
                self.assertContains(supervisor_response, "Defect recall: 1.0000")

                self.client.force_login(self.administrator)
                admin_response = self.client.get(reverse("metrics"))
                self.assertEqual(admin_response.status_code, 200)
                self.assertContains(admin_response, "Sample metrics")


class ProductAPITests(TestCase):
    def setUp(self):
        self.admin_group = Group.objects.create(name=ADMINISTRATOR)
        self.engineer_group = Group.objects.create(name=ENGINEER)
        self.admin_user = get_user_model().objects.create_user(username="api-admin")
        self.admin_user.groups.add(self.admin_group)
        self.engineer = get_user_model().objects.create_user(username="api-engineer")
        self.engineer.groups.add(self.engineer_group)
        self.product = Product.objects.create(
            product_id="P-PLATE01", name="Demonstration metal plate"
        )
        self.client = APIClient()

    def test_authenticated_role_can_read_and_only_administrator_can_write(self):
        self.client.force_authenticate(self.engineer)
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["product_id"], "P-PLATE01")

        forbidden_create = self.client.post(
            "/api/products/",
            {"product_id": "P-OTHER", "name": "Other", "description": ""},
            format="json",
        )
        forbidden_update = self.client.put(
            f"/api/products/{self.product.pk}/",
            {"product_id": "P-CHANGED", "name": "Changed", "description": ""},
            format="json",
        )
        forbidden_delete = self.client.delete(f"/api/products/{self.product.pk}/")
        self.assertEqual(forbidden_create.status_code, 403)
        self.assertEqual(forbidden_update.status_code, 403)
        self.assertEqual(forbidden_delete.status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_id, "P-PLATE01")

    def test_authenticated_user_without_inspection_role_can_read_products(self):
        authenticated_user = get_user_model().objects.create_user(
            username="authenticated-reader"
        )
        self.client.force_authenticate(authenticated_user)

        list_response = self.client.get("/api/products/")
        detail_response = self.client.get(f"/api/products/{self.product.pk}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)

    def test_administrator_can_create_update_and_delete_product(self):
        self.client.force_authenticate(self.admin_user)
        create_response = self.client.post(
            "/api/products/",
            {
                "product_id": "P-OTHER",
                "name": "Other demonstration part",
                "description": "API-managed product",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        product_pk = create_response.data["id"]
        update_response = self.client.put(
            f"/api/products/{product_pk}/",
            {
                "product_id": "P-OTHER",
                "name": "Updated part",
                "description": "Updated description",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, 200, update_response.data)
        self.assertEqual(update_response.data["name"], "Updated part")
        delete_response = self.client.delete(f"/api/products/{product_pk}/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Product.objects.filter(pk=product_pk).exists())

    def test_api_product_delete_reports_inspection_reference(self):
        user = self.admin_user
        batch = Batch.objects.create(created_by=user, product=self.product)
        Inspection.objects.create(
            product=self.product,
            submitted_by=user,
            batch=batch,
            original_filename="referenced.png",
            status=Inspection.Status.FAILED,
        )
        self.client.force_authenticate(user)

        response = self.client.delete(f"/api/products/{self.product.pk}/")

        self.assertEqual(response.status_code, 409)
        self.assertIn("cannot be deleted", response.data["detail"])
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())


class EvaluateSamplesCommandTests(TestCase):
    def test_metrics_use_validated_image_predictions_and_write_report(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            samples_dir = root / "Samples"
            images_dir = samples_dir / "images"
            images_dir.mkdir(parents=True)
            validation_dir = root / "Validation"
            validation_dir.mkdir()
            report_path = root / "evaluation_report.md"

            samples = [
                ("normal-correct.png", "Normal", "green"),
                ("normal-false-positive.png", "Normal", "red"),
                ("defect-true-positive.png", "Defective", "red"),
                ("defect-false-negative.png", "Defective", "green"),
            ]
            for filename, _, color in samples:
                (images_dir / filename).write_bytes(image_bytes(color=color))

            corrupt_content = image_bytes()[:-16]
            (images_dir / "corrupt.png").write_bytes(corrupt_content)
            label_rows = [
                {
                    "image_id": str(index),
                    "relative_path": f"images/{filename}",
                    "product_id": "P-PLATE01",
                    "label": actual,
                }
                for index, (filename, actual, _) in enumerate(samples)
            ]
            label_rows.extend(
                [
                    {
                        "image_id": "bad",
                        "relative_path": "images/corrupt.png",
                        "product_id": "P-PLATE01",
                        "label": "Normal",
                    },
                    {
                        "image_id": "missing",
                        "relative_path": "images/missing.png",
                        "product_id": "P-PLATE01",
                        "label": "Defective",
                    },
                ]
            )
            with (samples_dir / "labels.csv").open(
                "w", encoding="utf-8", newline=""
            ) as label_file:
                writer = csv.DictWriter(
                    label_file,
                    fieldnames=("image_id", "relative_path", "product_id", "label"),
                )
                writer.writeheader()
                writer.writerows(label_rows)

            (validation_dir / "not_an_image.jpg").write_text(
                "not an image", encoding="utf-8"
            )
            (validation_dir / "corrupt_image.png").write_bytes(corrupt_content)
            (validation_dir / "too_small.png").write_bytes(
                image_bytes(size=(32, 32))
            )

            def predict_from_pixels(image_path):
                with Image.open(image_path) as image:
                    is_red = image.convert("RGB").getpixel((0, 0))[0] > 200
                predicted_class = "Defective" if is_red else "Normal"
                return predicted_class, 0.9, float(is_red), "test-model"

            output = StringIO()
            with patch(
                "inspections.inference._load_predict",
                return_value=predict_from_pixels,
            ) as load_predict:
                call_command(
                    "evaluate_samples",
                    samples_dir=samples_dir,
                    validation_dir=validation_dir,
                    report_path=report_path,
                    stdout=output,
                )

            result = output.getvalue()
            report = report_path.read_text(encoding="utf-8")
            self.assertEqual(load_predict.call_count, 4)
            self.assertIn("| Normal | 1 | 1 |", result)
            self.assertIn("| Defective | 1 | 1 |", result)
            self.assertIn("- TP: 1", result)
            self.assertIn("- FN: 1", result)
            self.assertIn("- FP: 1", result)
            self.assertIn("- TN: 1", result)
            self.assertIn("- Accuracy (correct / successful labeled predictions): 0.5000", result)
            self.assertIn("- Defect recall (TP / (TP + FN)): 0.5000", result)
            self.assertIn("- Failed or missing predictions: 2", result)
            self.assertIn("not_an_image.jpg`: Rejected:", result)
            self.assertIn("corrupt_image.png`: Rejected:", result)
            self.assertIn("too_small.png`: Rejected:", result)
            self.assertNotIn("cannot establish real-world reliability", report)
            self.assertIn("evaluation_report.md", result)

    def test_zero_false_negatives_produces_reliability_limitation_note(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            samples_dir = root / "Samples"
            images_dir = samples_dir / "images"
            images_dir.mkdir(parents=True)
            image_path = images_dir / "defect.png"
            image_path.write_bytes(image_bytes(color="red"))
            with (samples_dir / "labels.csv").open(
                "w", encoding="utf-8", newline=""
            ) as label_file:
                writer = csv.DictWriter(
                    label_file,
                    fieldnames=("image_id", "relative_path", "product_id", "label"),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "image_id": "defect",
                        "relative_path": "images/defect.png",
                        "product_id": "P-PLATE01",
                        "label": "Defective",
                    }
                )
            output = StringIO()
            with patch(
                "inspections.inference._load_predict",
                return_value=lambda path: ("Defective", 0.9, 0.9, "test-model"),
            ):
                call_command(
                    "evaluate_samples",
                    samples_dir=samples_dir,
                    validation_dir=root / "Validation",
                    report_path=root / "evaluation_report.md",
                    stdout=output,
                )

            self.assertIn("Defect recall (TP / (TP + FN)): 1.0000", output.getvalue())
            self.assertIn(
                "cannot establish real-world reliability", output.getvalue()
            )

    def test_missing_samples_directory_fails_explicitly(self):
        with TemporaryDirectory() as temporary_directory:
            missing_samples = Path(temporary_directory) / "Samples"
            with self.assertRaisesMessage(
                CommandError, "Samples image directory not found"
            ):
                call_command("evaluate_samples", samples_dir=missing_samples)
