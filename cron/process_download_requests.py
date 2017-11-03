#!/usr/bin/python
import os
import settings

os.system("python %s/manage.py downloads process" % (settings.BASE_DIR))
