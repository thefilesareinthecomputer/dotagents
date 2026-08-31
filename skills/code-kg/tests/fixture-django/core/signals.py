"""Signal receivers wired in CoreConfig.ready()."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Payment
from core.services.notifications import notify_payment_received


@receiver(post_save, sender=Payment)
def announce_payment(sender, instance, created, **kwargs):
    if created:
        notify_payment_received(instance)
