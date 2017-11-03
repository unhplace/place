from django.core.management.base import BaseCommand, CommandError
import crontab

#from place.settings import BASE_DIR
from django.conf import settings
BASE_DIR = settings.BASE_DIR

class Command(BaseCommand):
    help = 'Start or stop the cron jobs associated with processing download requests and updating the database from external Solr repositories.'

    def add_arguments(self, parser):
        parser.add_argument("command", type=str)
        parser.add_argument("task", type=str)

    def handle(self, *args, **options):
        command = options["command"]
        task = options["task"]

        if not command in ("start", "stop"):
            raise CommandError("command must be either 'start' or 'stop'")

        if not task in ("downloads", "update", "all"):
            raise CommandError("task must be either 'downloads', 'update', or 'all' for both.")

        if task == "downloads":
            self.toggle_downloads(command)
            self.toggle_delete(command)
        elif task == "update":
            self.toggle_update(command)
        elif task == "all":
            self.toggle_downloads(command)
            self.toggle_delete(command)
            self.toggle_update(command)

    def toggle_downloads(self, command):
        cron = crontab.CronTab(user=False, tabfile="/etc/crontab")

        jobs = list(cron.find_command("%s/cron/process_download_requests.py" % (BASE_DIR)))
        job = None

        if len(jobs) == 0:
            job = cron.new("%s/cron/process_download_requests.py" % (BASE_DIR), user="apache")
            job.minute.every(5)
        else:
            job = jobs[0]

        job.enable(command == "start")

        cron.write()

        self.stdout.write("%s background download request processing" % ("Enabled" if command == "start" else "Disabled"))

    def toggle_delete(self, command):
        cron = crontab.CronTab(user=False, tabfile="/etc/crontab")

        jobs = list(cron.find_command("%s/cron/delete_old_downloads.py" % (BASE_DIR)))
        job = None

        if len(jobs) == 0:
            job = cron.new("%s/cron/delete_old_downloads.py" % (BASE_DIR), user="apache")
            job.minute.on(0)
            job.hour.on(0)
        else:
            job = jobs[0]

        job.enable(command == "start")

        cron.write()

        self.stdout.write("%s background download deletion" % ("Enabled" if command == "start" else "Disabled"))

    def toggle_update(self, command):
        cron = crontab.CronTab(user=False, tabfile="/etc/crontab")

        jobs = list(cron.find_command("%s/cron/update_db_from_solr.py" % (BASE_DIR)))
        job = None

        if len(jobs) == 0:
            job = cron.new("%s/cron/update_db_from_solr.py" % (BASE_DIR), user="apache")
            job.minute.on(0)
            job.hour.on(0)
            job.dow.on(0)
        else:
            job = jobs[0]

        job.enable(command == "start")

        cron.write()

        self.stdout.write("%s background database update" % ("Enabled" if command == "start" else "Disabled"))
