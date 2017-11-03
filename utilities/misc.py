import datetime
import time
import os

from PIL import Image

def is_string(value):
    return type(value) == str or type(value) == unicode

def name_from_filepath(filepath):
    return os.path.splitext(os.path.split(filepath)[1])[0]

def ogp_timestamp_for_now():
    return datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%dT%H:%M:%SZ')

def ogp_timestamp_for_year(year):
    return "%s-01-01T01:01:01Z" % (year)

