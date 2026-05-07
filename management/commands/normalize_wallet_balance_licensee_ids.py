"""
Rewrite wallet_balances.licensee_id to canonical NA/... (or LA/SB).

  python manage.py normalize_wallet_balance_licensee_ids

Step 1 (PostgreSQL): UPDATE rows where licensee_id equals applicant username on licenses.
Step 2: ORM save() per row for any remaining cases.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from models.transactional.wallet.models import WalletBalance


class Command(BaseCommand):
    help = "Normalize wallet_balances.licensee_id to issued license ids (e.g. NA/...)."

    def handle(self, *args, **options):
        sql_updated = 0
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                # wallet row keyed by username (TH...) → licenses.license_id (NA/...) via applicant
                cursor.execute(
                    """
                    UPDATE wallet_balances wb
                    SET licensee_id = l.license_id
                    FROM licenses l
                    INNER JOIN custom_user u ON u.id = l.applicant_id
                    WHERE wb.licensee_id = u.username
                      AND l.source_type = %s
                      AND l.is_active = TRUE
                      AND wb.licensee_id NOT LIKE 'NA/%%'
                      AND wb.licensee_id NOT LIKE 'LA/%%'
                      AND wb.licensee_id NOT LIKE 'SB/%%'
                    """,
                    ["new_license_application"],
                )
                sql_updated = cursor.rowcount
            if sql_updated:
                self.stdout.write(
                    self.style.WARNING(
                        f"PostgreSQL bulk UPDATE: {sql_updated} row(s) matched username → NA/..."
                    )
                )

        updated = 0
        skipped = 0
        for wb in WalletBalance.objects.all().iterator():
            before = str(wb.licensee_id or "").strip()
            wb.save()
            after = str(wb.licensee_id or "").strip()
            if before != after:
                updated += 1
                self.stdout.write(f"{before!r} -> {after!r} (wallet_balance_id={wb.wallet_balance_id})")
            else:
                skipped += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. sql_bulk={sql_updated}, orm_updated={updated}, unchanged={skipped}."
            )
        )
