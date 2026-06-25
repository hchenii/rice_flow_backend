"""
python manage.py train_yield_models

Trains 3 regression models (Linear, Ridge, Lasso) for yield prediction.
Compares R², MAE, RMSE — saves the best as active.
Safe to re-run anytime.
"""
from django.core.management.base import BaseCommand
from apps.predictions.models import YieldPredictionModel
from apps.predictions.services import train_all_models


class Command(BaseCommand):
    help = 'Train Linear, Ridge, Lasso regression models for yield prediction'

    def handle(self, *args, **options):
        self.stdout.write('Training yield prediction models...')

        results = train_all_models()
        YieldPredictionModel.objects.all().delete()

        for r in results:
            YieldPredictionModel.objects.create(**r)
            active_label = ' << BEST' if r['is_active'] else ''
            self.stdout.write(
                f"  {r['model_type']:8s}  "
                f"R²={r['r2_score']:.4f}  "
                f"MAE={r['mae']:.4f}  "
                f"RMSE={r['rmse']:.4f}"
                f"{active_label}"
            )

        best = max(results, key=lambda x: x['r2_score'])
        self.stdout.write(self.style.SUCCESS(
            f'\nBest model: {best["model_type"]} '
            f'(R²={best["r2_score"]:.4f})'
        ))
