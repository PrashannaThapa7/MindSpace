from django.apps import AppConfig

class MentalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mental'

    def ready(self):
        import mental.signals  # noqa