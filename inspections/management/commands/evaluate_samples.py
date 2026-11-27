import csv
import posixpath
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inspections.inference import run_inference
from inspections.validation import ImageValidationError, validate_image

CLASS_ORDER = ("Normal", "Defective")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
VALIDATION_FIXTURES = ("not_an_image.jpg", "corrupt_image.png", "too_small.png")


def _class_name(value):
    normalized = str(value).strip().casefold()
    return {
        "normal": "Normal",
        "defective": "Defective",
    }.get(normalized)


def _relative_key(value):
    key = posixpath.normpath(str(value).replace("\\", "/"))
    while key.startswith("./"):
        key = key[2:]
    return key


class Command(BaseCommand):
    help = "Evaluate the frozen classifier on labeled Samples/ images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--samples-dir",
            type=Path,
            default=Path(settings.BASE_DIR) / "Samples",
        )
        parser.add_argument(
            "--validation-dir",
            type=Path,
            default=Path(settings.BASE_DIR) / "Validation",
        )
        parser.add_argument(
            "--report-path",
            type=Path,
            default=Path(settings.BASE_DIR) / "evaluation_report.md",
        )

    def handle(self, *args, **options):
        samples_dir = options["samples_dir"].resolve()
        images_dir = samples_dir / "images"
        labels_path = samples_dir / "labels.csv"
        if not images_dir.is_dir():
            raise CommandError(f"Samples image directory not found: {images_dir}")
        if not labels_path.is_file():
            raise CommandError(f"Sample labels file not found: {labels_path}")

        image_paths = sorted(
            path
            for path in images_dir.rglob("*")
            if path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES
        )
        if not image_paths:
            raise CommandError(f"No JPEG or PNG samples found in {images_dir}")

        predictions = {}
        failures = {}
        for image_path in image_paths:
            key = image_path.relative_to(samples_dir).as_posix()
            try:
                predicted_class, _, _, _ = run_inference(image_path)
                normalized_prediction = _class_name(predicted_class)
                if normalized_prediction is None:
                    raise ValueError(
                        f"Model returned unsupported class: {predicted_class!r}"
                    )
                predictions[key] = normalized_prediction
            except Exception as error:
                reason = str(error).strip() or error.__class__.__name__
                failures[key] = reason

        labels = self._read_labels(labels_path)
        image_keys = set(predictions) | set(failures)
        matrix = {
            actual: {predicted: 0 for predicted in CLASS_ORDER}
            for actual in CLASS_ORDER
        }
        failed_or_missing = list(failures.items())
        failed_keys = set(failures)
        invalid_labels = []
        unlabeled_images = []
        evaluated = 0
        true_positive = false_negative = false_positive = true_negative = 0
        labeled_keys = set()

        for row in labels:
            key = _relative_key(row["relative_path"])
            key = self._match_sample_key(key, samples_dir, image_keys)
            actual = _class_name(row["label"])
            if actual is None:
                invalid_labels.append(
                    (key, f"Unsupported actual label: {row['label']!r}")
                )
                continue
            labeled_keys.add(key)
            predicted = predictions.get(key)
            if predicted is None:
                if key not in failed_keys:
                    failed_or_missing.append(
                        (key, "Sample file is missing or has no prediction")
                    )
                    failed_keys.add(key)
                continue
            matrix[actual][predicted] += 1
            evaluated += 1
            if actual == "Defective" and predicted == "Defective":
                true_positive += 1
            elif actual == "Defective" and predicted == "Normal":
                false_negative += 1
            elif actual == "Normal" and predicted == "Defective":
                false_positive += 1
            else:
                true_negative += 1

        for key in predictions.keys() | failures.keys():
            if key not in labeled_keys:
                unlabeled_images.append(key)

        accuracy = (true_positive + true_negative) / evaluated if evaluated else None
        recall_denominator = true_positive + false_negative
        defect_recall = (
            true_positive / recall_denominator if recall_denominator else None
        )
        validation_results = self._check_validation_fixtures(
            options["validation_dir"]
        )
        report = self._build_report(
            matrix=matrix,
            true_positive=true_positive,
            false_negative=false_negative,
            false_positive=false_positive,
            true_negative=true_negative,
            accuracy=accuracy,
            defect_recall=defect_recall,
            failed_or_missing=failed_or_missing,
            invalid_labels=invalid_labels,
            unlabeled_images=unlabeled_images,
            validation_results=validation_results,
        )

        report_path = options["report_path"]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        self.stdout.write(report)
        self.stdout.write(f"\nReport saved to {report_path}")

    def _read_labels(self, labels_path):
        required_columns = {"image_id", "relative_path", "product_id", "label"}
        with labels_path.open(encoding="utf-8-sig", newline="") as labels_file:
            reader = csv.DictReader(labels_file)
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                raise CommandError(
                    "labels.csv must contain image_id, relative_path, "
                    "product_id, and label columns."
                )
            rows = []
            for line_number, row in enumerate(reader, start=2):
                relative_path = (row.get("relative_path") or "").strip()
                label = (row.get("label") or "").strip()
                if not relative_path or not label:
                    raise CommandError(
                        f"labels.csv is missing relative_path or label on "
                        f"line {line_number}."
                    )
                rows.append({"relative_path": relative_path, "label": label})
            if not rows:
                raise CommandError("labels.csv contains no labeled samples.")
            return rows

    def _match_sample_key(self, key, samples_dir, image_keys):
        candidates = [key]
        if key.startswith(f"{samples_dir.name}/"):
            candidates.append(key[len(samples_dir.name) + 1 :])
        if not key.startswith("images/"):
            candidates.append(f"images/{key}")
        if key.startswith("Samples/"):
            candidates.append(key[len("Samples/") :])
        for candidate in candidates:
            if candidate in image_keys:
                return candidate
        return key

    def _check_validation_fixtures(self, validation_dir):
        results = []
        for filename in VALIDATION_FIXTURES:
            fixture = validation_dir / filename
            if not fixture.is_file():
                results.append((filename, "Missing validation fixture"))
                continue
            try:
                with fixture.open("rb") as image_file:
                    validate_image(image_file)
            except ImageValidationError as error:
                results.append((filename, f"Rejected: {error}"))
            else:
                results.append((filename, "Accepted"))
        return results

    def _build_report(
        self,
        *,
        matrix,
        true_positive,
        false_negative,
        false_positive,
        true_negative,
        accuracy,
        defect_recall,
        failed_or_missing,
        invalid_labels,
        unlabeled_images,
        validation_results,
    ):
        accuracy_text = "N/A" if accuracy is None else f"{accuracy:.4f}"
        recall_text = "N/A" if defect_recall is None else f"{defect_recall:.4f}"
        lines = [
            "# Sample Evaluation Report",
            "",
            "Confusion matrix (rows = actual, columns = predicted):",
            "",
            "| Actual / Predicted | Normal | Defective |",
            "|---|---:|---:|",
            f"| Normal | {matrix['Normal']['Normal']} | {matrix['Normal']['Defective']} |",
            f"| Defective | {matrix['Defective']['Normal']} | {matrix['Defective']['Defective']} |",
            "",
            f"- TP: {true_positive}",
            f"- FN: {false_negative}",
            f"- FP: {false_positive}",
            f"- TN: {true_negative}",
            f"- Accuracy (correct / successful labeled predictions): {accuracy_text}",
            f"- Defect recall (TP / (TP + FN)): {recall_text}",
            f"- Failed or missing predictions: {len(failed_or_missing)}",
        ]
        if failed_or_missing:
            lines.extend(("", "Failed or missing prediction details:"))
            lines.extend(f"- `{key}`: {reason}" for key, reason in failed_or_missing)
        if invalid_labels:
            lines.extend(("", "Invalid label details:"))
            lines.extend(f"- `{key}`: {reason}" for key, reason in invalid_labels)
        lines.extend(
            (
                f"- Images without a label row: {len(unlabeled_images)}",
                "",
                "Validation fixture outcomes:",
            )
        )
        lines.extend(
            f"- `{filename}`: {result}" for filename, result in validation_results
        )
        if false_negative == 0:
            lines.extend(
                (
                    "",
                    "No false negatives were observed, but 60 synthetic samples "
                    "cannot establish real-world reliability.",
                )
            )
        return "\n".join(lines)
