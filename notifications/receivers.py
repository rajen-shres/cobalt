from django_ses.signals import send_received
from django.dispatch import receiver


@receiver(send_received)
def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):
    print("Aardvark")
    print(sender)
    print(mail_obj)
