from django_ses.signals import send_received
from django.dispatch import receiver
from django_ses.signals import delivery_received


@receiver(send_received)
def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):
    print("Aardvark send_received4", flush=True)
    print(sender, flush=True)
    print(mail_obj, flush=True)


@receiver(delivery_received)
def delivery_handler(sender, mail_obj, delivery_obj, raw_message, *args, **kwargs):
    print("Aardvark delivery_received", flush=True)
    print(sender, flush=True)
    print(mail_obj, flush=True)
