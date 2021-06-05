""" Eamil Daemon to watch for emails """


from django.core.management.base import BaseCommand
from accounts.models import User
import socket


class Command(BaseCommand):
    def handle(self, *args, **options):

        HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
        PORT = 65432  # Port to listen on (non-privileged ports are > 1023)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen()
            print("Running...")
            while True:
                conn, addr = s.accept()
                with conn:
                    print("Connected by", addr)
                    while True:
                        data = conn.recv(1024)
                        if not data:
                            break
                        conn.sendall(b"Ok")
                conn.close()
        #
        # import socket
        #
        # HOST = '127.0.0.1'  # The server's hostname or IP address
        # PORT = 65432  # The port used by the server
        #
        # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        #     s.connect((HOST, PORT))
        #     s.sendall(b'Hello, world')
        #     data = s.recv(1024)
        #
        # print('Received', repr(data))
