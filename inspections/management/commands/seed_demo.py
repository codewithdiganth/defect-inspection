import csv
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inspections.models import Product
from inspections.permissions import ADMINISTRATOR, ENGINEER, SUPERVISOR

DEMO_PASSWORD = "Demo@12345"


class Command(BaseCommand):
    help = "Create the demo role groups, users, and products from product_details.csv."

    @transaction.atomic
    def handle(self, *args, **options):
        product_rows = self._read_products()
        groups = {
            role: Group.objects.get_or_create(name=role)[0]
            for role in (ADMINISTRATOR, ENGINEER, SUPERVISOR)
        }
        self._assign_product_permissions(groups[ADMINISTRATOR])
        self._seed_users(groups)
        for row in product_rows:
            Product.objects.update_or_create(
                product_id=row["product_id"],
                defaults={
                    "name": row["product_name"],
                    "description": row["description"],
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Created or updated Administrator, Engineer, and Supervisor "
                "groups; demo users; and products."
            )
        )

    def _read_products(self):
        csv_path = Path(settings.BASE_DIR) / "product_details.csv"
        if not csv_path.is_file():
            raise CommandError(f"Product data file not found: {csv_path}")

        with csv_path.open(encoding="utf-8-sig", newline="") as product_file:
            reader = csv.DictReader(product_file)
            if not reader.fieldnames or not {
                "product_id",
                "description",
            }.issubset(reader.fieldnames) or not (
                "product_name" in reader.fieldnames or "name" in reader.fieldnames
            ):
                raise CommandError(
                    "product_details.csv must contain product_id, "
                    "product_name (or name), and description columns."
                )
            name_column = (
                "product_name" if "product_name" in reader.fieldnames else "name"
            )
            rows = []
            for line_number, row in enumerate(reader, start=2):
                product_id = (row.get("product_id") or "").strip()
                name = (row.get(name_column) or "").strip()
                if not product_id or not name:
                    raise CommandError(
                        f"Product data is missing product_id or name on line "
                        f"{line_number}."
                    )
                rows.append(
                    {
                        "product_id": product_id,
                        "product_name": name,
                        "description": (row.get("description") or "").strip(),
                    }
                )
            if not rows:
                raise CommandError("product_details.csv contains no products.")
            return rows

    def _assign_product_permissions(self, administrator_group):
        content_type = ContentType.objects.get_for_model(Product)
        permissions = Permission.objects.filter(
            content_type=content_type,
            codename__in=(
                "add_product",
                "change_product",
                "delete_product",
                "view_product",
            ),
        )
        administrator_group.permissions.set(permissions)

    def _seed_users(self, groups):
        user_model = get_user_model()
        for username, role in (
            ("admin1", ADMINISTRATOR),
            ("eng1", ENGINEER),
            ("sup1", SUPERVISOR),
        ):
            user, _ = user_model.objects.get_or_create(username=username)
            user.set_password(DEMO_PASSWORD)
            user.is_staff = role == ADMINISTRATOR
            user.is_superuser = role == ADMINISTRATOR
            user.save()
            user.groups.set([groups[role]])
