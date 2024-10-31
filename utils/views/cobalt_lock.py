import datetime
import os

from django.db import transaction
from django.utils import timezone

from utils.models import Lock


class CobaltLock:
    """handle running one thing at a time in a multi-node environment"""

    def __init__(self, topic: str, expiry: int = 15):
        """
        Args:
            topic: name of this lock
            expiry: time in minutes to keep the lock closed for. After this even if
                    open it will be considered expired (assume process died)
        """

        self.topic = topic
        self.expiry = expiry
        self._locked = False

    @transaction.atomic
    def get_lock(self):
        """Try to get a lock, returns True or False"""

        lock = Lock.objects.select_for_update().filter(topic=self.topic).first()

        if lock:  # Lock found

            if lock.lock_open_time and lock.lock_open_time > timezone.now():
                return False

            lock.lock_created_time = timezone.now()
            open_time = timezone.now() + datetime.timedelta(minutes=self.expiry)
            hostname = os.popen("hostname 2>/dev/null").read().strip()
            lock.lock_open_time = open_time
            lock.owner = hostname
            lock.save()

        else:  # Create lock

            open_time = timezone.now() + datetime.timedelta(minutes=self.expiry)
            hostname = os.popen("hostname 2>/dev/null").read().strip()
            Lock(lock_open_time=open_time, topic=self.topic, owner=hostname).save()

        self._locked = True
        return True

    @transaction.atomic
    def free_lock(self):
        """Release lock"""

        if not self._locked:
            return

        lock = Lock.objects.select_for_update().filter(topic=self.topic).first()
        if not lock:
            return
        lock.lock_open_time = None
        lock.save()
        self._locked = False

    @transaction.atomic
    def delete_lock(self):
        """Delete the lock record, returning success. Will only delete an expired or freed lock. COB_965"""

        lock = Lock.objects.select_for_update().filter(topic=self.topic).first()
        if not lock:
            return True

        if lock.lock_open_time and lock.lock_open_time > timezone.now():
            return False

        lock.delete()
        self._locked = False
        return True
