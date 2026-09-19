"""
Management command: auto_reject_expired_payment_timers

Scans all NewLicenseApplication records in Stage 23 (Awaiting Payment)
whose payment deadline has passed and automatically moves them to:
"Rejected – No Action Taken by User at Payment Stage".

Usage:
    python manage.py auto_reject_expired_payment_timers
    python manage.py auto_reject_expired_payment_timers --dry-run
    python manage.py auto_reject_expired_payment_timers --verbosity 2
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Auto-reject New License applications whose payment deadline at Stage 23 "
        "has passed without completing License Fee and Security Amount payments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview which applications would be rejected without saving changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verbosity = options.get("verbosity", 1)
        now = timezone.now()

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"[{now:%Y-%m-%d %H:%M:%S UTC}] Running auto_reject_expired_payment_timers "
                f"{'(DRY RUN)' if dry_run else ''}"
            )
        )

        from auth.workflow.services import WorkflowService

        if dry_run:
            from models.transactional.new_license_application.models import NewLicenseApplication
            from auth.workflow.models import WorkflowStage as WS
            from django.db.models import Q

            payment_stages = WS.objects.filter(
                name__in=["awaiting_payment", "Awaiting Payment", "Awaiting License Fee Payment"],
                is_final=False,
            ).values_list("id", flat=True)

            qs = NewLicenseApplication.objects.select_related("current_stage", "workflow").filter(
                Q(current_stage_id__in=payment_stages) | Q(current_stage__name__icontains="payment"),
                current_stage__is_final=False,
            ).exclude(
                current_stage__name__icontains="reject"
            ).filter(
                Q(is_license_fee_paid=False) | Q(is_security_fee_paid=False)
            )

            expired_count = 0
            for app in qs:
                entered_at = getattr(app, "awaiting_payment_entered_at", None) or getattr(app, "updated_at", now)
                deadline = WorkflowService._compute_new_license_payment_deadline(from_time=entered_at)
                if now > deadline:
                    expired_count += 1
                    self.stdout.write(
                        f"  • App #{app.pk} ({app.establishment_name}) | entered={entered_at:%Y-%m-%d %H:%M} | "
                        f"deadline={deadline:%Y-%m-%d %H:%M}"
                    )

            if expired_count == 0:
                self.stdout.write(self.style.SUCCESS("No expired payment timers found."))
            else:
                self.stdout.write(self.style.WARNING(f"DRY RUN — {expired_count} expired application(s) found."))
            return

        try:
            result = WorkflowService.auto_reject_expired_payment_timers()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Fatal error: {exc}"))
            raise

        checked = result.get("checked", 0)
        rejected = result.get("rejected", 0)
        errors = result.get("errors", 0)

        if verbosity >= 1:
            if rejected == 0 and errors == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Checked {checked} application(s). Nothing to reject."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Checked {checked} application(s). "
                        f"Rejected: {rejected}. Errors: {errors}."
                    )
                )
