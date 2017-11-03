#!/usr/bin/python
import os
import settings

os.system("python %s/manage.py update incremental" % (settings.BASE_DIR))
