from django_ses.signals import send_received
from django.dispatch import receiver
from django_ses.signals import delivery_received
from django_ses.signals import open_received
from django_ses.signals import click_received
from django_ses.signals import bounce_received
from django_ses.signals import complaint_received


@receiver(bounce_received)
def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
    # message_id = mail_obj["messageId"]
    # recipient_list = mail_obj["destination"]
    print("This is bounce email object")
    print(mail_obj)
    with open("/tmp/email.txt", "a") as fhandle:
        fhandle.write("bounce\n")


@receiver(complaint_received)
def complaint_handler(sender, mail_obj, complaint_obj, raw_message, *args, **kwargs):

    with open("/tmp/email.txt", "a") as fhandle:
        fhandle.write("complaint\n")

        print("Aardvark complaint_received", flush=True)
        print(sender, flush=True)
        print(mail_obj, flush=True)


@receiver(send_received)
def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):
    with open("/tmp/email.txt", "a") as fhandle:
        fhandle.write("send\n")

    print("Aardvark send_received4", flush=True)
    print(sender, flush=True)
    print(mail_obj, flush=True)


@receiver(delivery_received)
def delivery_handler(sender, mail_obj, delivery_obj, raw_message, *args, **kwargs):
    with open("/tmp/email.txt", "a") as fhandle:
        fhandle.write("deliver\n")

    print("Aardvark delivery_received", flush=True)
    print(sender, flush=True)
    print(mail_obj, flush=True)


@receiver(open_received)
def open_handler(sender, mail_obj, open_obj, raw_message, *args, **kwargs):
    with open("/tmp/email.txt", "a") as fhandle:
        fhandle.write("open\n")
    print("Aardvark open_received", flush=True)
    print(sender, flush=True)
    print(mail_obj, flush=True)


@receiver(click_received)
def click_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
    with open("/tmp/email.txt", "a") as fhandle:
        fhandle.write("click\n")
    print("Aardvark click_received", flush=True)
    print(sender, flush=True)
    print(mail_obj, flush=True)
