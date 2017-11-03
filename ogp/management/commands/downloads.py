from django.core.management.base import BaseCommand, CommandError
from glob import glob
from lockfile import LockFile
from ogp.models import DownloadRequest
import datetime
import os

#from place.settings import BASE_DIR
from django.conf import settings
BASE_DIR = settings.BASE_DIR

class Command(BaseCommand):
    help = 'Process current download requests'

    def add_arguments(self, parser):
        parser.add_argument("task", type=str)

    def handle(self, *args, **options):
        task = options["task"]

        if not task in ("count", "delete", "process"):
            raise CommandError("task must be either 'count', 'delete' or 'process'")

        if task == "count":
            count = DownloadRequest.objects.filter(active=True).count()
            self.stdout.write("%d requests pending" % (count))

        if task == "delete":
            lock_file_path = "/tmp/place.downloads.delete"
            lock = LockFile(lock_file_path)

            if lock.is_locked():
                return

            lock.acquire()

            files = glob("%s/media/zip/*.zip" % BASE_DIR)

            for file_name in files:
                date = datetime.datetime.fromtimestamp(os.path.getctime(file_name))
                days = (datetime.datetime.now() - date).days

                if days > 0:
                    os.remove(file_name)

            lock.release()

        if task == "process":
            lock_file_path = "/tmp/place.downloads.process"
            lock = LockFile(lock_file_path)

            if lock.is_locked():
                return
            
            lock.acquire()

            count = DownloadRequest.objects.filter(active=True).count()

            for dr in DownloadRequest.objects.filter(active=True):
                dr.create_zip_file_and_notify()

            lock.release()
            
            if count > 0:
                self.stdout.write("%d requests processed" % (count))
