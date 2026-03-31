from pathlib import Path

import sqlparse
from django.core.management.base import BaseCommand
from django.db import connection, transaction


def _strip_sql_comments(statement: str) -> str:
    kept_lines: list[str] = []
    for line in (statement or "").splitlines():
        if line.lstrip().startswith("--"):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


class Command(BaseCommand):
    help = "Apply MASTER_LIQUOR_TYPE_MIGRATION.sql and print master_liquor_type rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sql",
            default=str(Path("docs") / "MASTER_LIQUOR_TYPE_MIGRATION.sql"),
            help="Path to SQL migration file (default: docs/MASTER_LIQUOR_TYPE_MIGRATION.sql).",
        )
        parser.add_argument(
            "--finalize",
            action="store_true",
            help="Also apply docs/MASTER_LIQUOR_TYPE_FINALIZE.sql (drops legacy brand_warehouse.brand_type).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Max rows to print from master_liquor_type (default: 200).",
        )

    def handle(self, *args, **options):
        sql_path = Path(options["sql"])
        limit = int(options["limit"])

        if not sql_path.exists():
            self.stderr.write(self.style.ERROR(f"SQL file not found: {sql_path}"))
            return

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'brand_warehouse'
                  AND column_name = 'brand_type'
                LIMIT 1;
                """
            )
            has_legacy_brand_type = cursor.fetchone() is not None

        sql_text = sql_path.read_text(encoding="utf-8")
        raw_statements = [s.strip() for s in sqlparse.split(sql_text) if s.strip()]

        statements: list[str] = []
        for raw in raw_statements:
            cleaned = _strip_sql_comments(raw)
            if cleaned:
                if (not has_legacy_brand_type) and ("brand_type" in cleaned):
                    # After finalization we drop brand_warehouse.brand_type.
                    # Skip legacy seed/backfill statements that reference it.
                    continue
                statements.append(cleaned)

        if not statements:
            self.stderr.write(self.style.ERROR("No executable SQL statements found."))
            return

        self.stdout.write(self.style.NOTICE(f"Applying SQL migration: {sql_path}"))
        if not has_legacy_brand_type:
            self.stdout.write(self.style.WARNING("Legacy column public.brand_warehouse.brand_type not found; skipping legacy seed/backfill steps."))
        self.stdout.write(self.style.NOTICE(f"Statements: {len(statements)}"))

        with transaction.atomic():
            with connection.cursor() as cursor:
                for idx, stmt in enumerate(statements, start=1):
                    cursor.execute(stmt)

        self.stdout.write(self.style.SUCCESS("Migration applied."))

        if options.get("finalize"):
            finalize_path = Path("docs") / "MASTER_LIQUOR_TYPE_FINALIZE.sql"
            if not finalize_path.exists():
                self.stderr.write(self.style.ERROR(f"Finalize SQL file not found: {finalize_path}"))
                return

            finalize_text = finalize_path.read_text(encoding="utf-8")
            finalize_raw = [s.strip() for s in sqlparse.split(finalize_text) if s.strip()]
            finalize_statements: list[str] = []
            for raw in finalize_raw:
                cleaned = _strip_sql_comments(raw)
                if cleaned:
                    finalize_statements.append(cleaned)

            self.stdout.write(self.style.NOTICE(f"Applying finalize SQL: {finalize_path}"))
            with transaction.atomic():
                with connection.cursor() as cursor:
                    for stmt in finalize_statements:
                        cursor.execute(stmt)

            self.stdout.write(self.style.SUCCESS("Finalize applied (legacy brand_type dropped if present)."))

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM public.master_liquor_type;")
            total = int(cursor.fetchone()[0] or 0)
            self.stdout.write(self.style.NOTICE(f"master_liquor_type total rows: {total}"))

            cursor.execute(
                """
                SELECT id, liquor_type
                FROM public.master_liquor_type
                ORDER BY id
                LIMIT %s;
                """,
                [limit],
            )
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write("No rows found in master_liquor_type.")
            return

        self.stdout.write("")
        self.stdout.write("id\tliquor_type")
        for row_id, liquor_type in rows:
            self.stdout.write(f"{row_id}\t{liquor_type}")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'brand_warehouse'
                  AND column_name IN ('brand_type', 'liquor_type')
                ORDER BY column_name;
                """
            )
            cols = cursor.fetchall()

        if cols:
            self.stdout.write("")
            self.stdout.write("brand_warehouse columns:")
            for col_name, col_type in cols:
                self.stdout.write(f"- {col_name}: {col_type}")
