"""
backfill_cycles  —  one-shot data backfill.

Creates an active FarmCycle for every Farm that has at least one
Recommendation but no FarmCycle yet. Useful after upgrading from a
version of the system that did not auto-create cycles when
recommendations were generated.

Usage:
    python manage.py backfill_cycles
    python manage.py backfill_cycles --dry-run   (just report, no writes)
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.farms.models import Farm
from apps.progress.models import FarmCycle
from apps.recommendations.models import Recommendation
from apps.recommendations.views import ensure_active_cycle_for_recommendation


class Command(BaseCommand):
    help = "Backfill missing FarmCycles for farms that already have recommendations."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be created without writing to the database.',
        )

    def handle(self, *args, **opts):
        dry = opts['dry_run']

        farms_with_rec = Farm.objects.filter(recommendations__isnull=False).distinct()
        eligible       = farms_with_rec.filter(farm_cycles__isnull=True).distinct()

        self.stdout.write(self.style.NOTICE(
            f"Farms with at least one recommendation: {farms_with_rec.count()}"
        ))
        self.stdout.write(self.style.NOTICE(
            f"Farms missing a cycle:                  {eligible.count()}"
        ))

        if not eligible.exists():
            self.stdout.write(self.style.SUCCESS("Nothing to backfill — every farm already has a cycle."))
            return

        created = 0
        skipped = 0
        errors  = []

        for farm in eligible.iterator():
            latest_rec = (
                Recommendation.objects
                    .filter(farm=farm)
                    .order_by('-created_at')
                    .first()
            )
            if not latest_rec:
                skipped += 1
                continue

            if dry:
                top = latest_rec.results.order_by('rank').first()
                self.stdout.write(
                    f"  would create cycle for farm={farm.name!r} "
                    f"variety={(top.variety.common_name if top and top.variety else 'n/a')}"
                )
                created += 1
                continue

            try:
                with transaction.atomic():
                    _, was_created = ensure_active_cycle_for_recommendation(latest_rec)
                    if was_created:
                        created += 1
                    else:
                        skipped += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"{farm.id}/{farm.name}: {e}")

        self.stdout.write("")
        if dry:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN — would create {created} cycle(s), skip {skipped}."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Backfill complete. Created {created} cycle(s), skipped {skipped}."
            ))
        if errors:
            self.stdout.write(self.style.ERROR("Errors:"))
            for line in errors:
                self.stdout.write(self.style.ERROR("  " + line))
