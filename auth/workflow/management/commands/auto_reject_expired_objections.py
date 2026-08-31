"""
Management command: auto_reject_expired_objections

Scans all unresolved objections whose deadline_at has passed and automatically
moves the parent applications to the "Rejected - No Action Taken on Objection"
terminal stage.

Usage:
    python manage.py auto_reject_expired_objections
    python manage.py auto_reject_expired_objections --dry-run
    python manage.py auto_reject_expired_objections --verbosity 2

Schedule this command to run periodically (e.g. every hour) via:
    - Windows Task Scheduler
    - Linux/Mac cron:  0 * * * * /path/to/venv/bin/python manage.py auto_reject_expired_objections
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Auto-reject applications whose objection deadline has passed without "
        "the applicant taking any action."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Preview which applications would be rejected without making "
                "any database changes."
            ),
        )

    def handle(self, *args, **options):
        dry_run   = options["dry_run"]
        verbosity = options.get("verbosity", 1)
        now       = timezone.now()

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"[{now:%Y-%m-%d %H:%M:%S UTC}] Running auto_reject_expired_objections "
                f"{'(DRY RUN)' if dry_run else ''}"
            )
        )

        if dry_run:
            from auth.workflow.models import Objection
            expired = Objection.objects.filter(
                is_resolved=False,
                deadline_at__lt=now,
            ).select_related("content_type")

            if not expired.exists():
                self.stdout.write(self.style.SUCCESS("No expired objections found."))
                return

            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN — {expired.count()} overdue objection(s) found:"
                )
            )
            for obj in expired:
                self.stdout.write(
                    f"  • Objection #{obj.pk} | app_id={obj.object_id} | "
                    f"model={obj.content_type} | deadline={obj.deadline_at:%Y-%m-%d %H:%M}"
                )
            return

        from auth.workflow.services import WorkflowService

        try:
            result = WorkflowService.auto_reject_expired_objections()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Fatal error: {exc}"))
            raise

        checked  = result.get("checked", 0)
        rejected = result.get("rejected", 0)
        errors   = result.get("errors", 0)

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
                if errors and verbosity >= 2:
                    self.stdout.write(
                        self.style.WARNING(
                            "Some applications could not be processed. "
                            "Check the 'workflow.auto_reject' logger for details."
                        )
                    )
