from django.apps import AppConfig


class PaymentGatewayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "models.transactional.payment_gateway"
    verbose_name = "payment_gateway"

