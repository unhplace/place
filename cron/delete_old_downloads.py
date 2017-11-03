#!/usr/bin/python
import os
import settings

os.system("python %s/manage.py downloads delete" % (settings.BASE_DIR))
