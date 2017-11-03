from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
from django.contrib.postgres.fields import ArrayField, HStoreField
from django.db import connection
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from email.mime.text import MIMEText
from urllib import urlretrieve

import json
import os
import smtplib
import zipfile

from django.conf import settings 

#class Item(models.Model):
class BoundedItem(models.Model):
    Abstract = models.TextField()
    Access = models.TextField()
    Area = models.FloatField()
    Availability = models.TextField(default="online")
    CenterX = models.FloatField()
    CenterY = models.FloatField()
    ContentDate = models.TextField()
    DataType = models.TextField()
    FgdcText = models.TextField()
    GeoReferenced = models.BooleanField()
    HalfHeight = models.FloatField()
    HalfWidth = models.FloatField()
    Institution = models.TextField()
    LayerDisplayName = models.TextField()
    LayerId = models.TextField()
    Location = models.TextField(blank=True)
    MaxX = models.FloatField()
    MinX = models.FloatField()
    MaxY = models.FloatField()
    MinY = models.FloatField()
    Name = models.TextField(unique=True)
    Originator = models.TextField()
    PlaceKeywords = models.TextField(blank=True)
    Publisher = models.TextField()
    ThemeKeywords = models.TextField(blank=True)
    WorkspaceName = models.TextField(blank=True)
    timestamp = models.TextField()

    collection = models.ForeignKey("ItemCollection", blank=True, null=True)
    directory_path = models.TextField()

    bounds = models.PolygonField(blank=True, null=True)
    srs = models.IntegerField(default=4326)
    objects = models.GeoManager()

    def __unicode__(self):
        return self.Name

    def date_object(self):
        ogp_time_format = '%Y-%m-%dT%H:%M:%SZ'

    @property
    def fedora_url(self):
        return "%s/place/%s/%s" % (settings.FCREPO_BASE_URL, self.collection.fedora_name, self.LayerId)

    class Meta:
        app_label = "ogp"

    def as_dictionary(self, fields, include_collection = False):
        if type(fields) != list and type(fields) != tuple:
            if type(fields) == str or type(fields) == unicode:
                fields = fields.split(",")
            else:
                return None

        d = {}

        for field in fields:
            if hasattr(self, field):
                d[field] = self.__getattribute__(field)

        if (include_collection): 
            d["collection"] = self.collection.name

        return d

    @classmethod
    def from_json(object_type, dictionary):
        b = None

        if BoundedItem.objects.filter(LayerId=dictionary["LayerId"]).exists():
            b = BoundedItem.objects.get(LayerId=dictionary["LayerId"])
        else:
            b = BoundedItem()

        for k in dictionary.keys():
            if hasattr(b, k):
                b.__setattr__(k, dictionary[k])
    
        return b

@receiver(pre_save, sender=BoundedItem)
def add_bounds_to_item(sender, **kwargs):
    i = kwargs['instance']
    minX = i.MinX
    maxX = i.MaxX
    minY = i.MinY
    maxY = i.MaxY

    i.bounds = Polygon(((minX, minY), (minX, maxY), (maxX, maxY), (maxX, minY), (minX, minY)))

class ItemCollection(models.Model):
    full_name = models.TextField()
    short_name = models.TextField()
    abbreviated_name = models.TextField(blank=True, null=True)
    metadata_available = models.BooleanField(default=False)
    external = models.BooleanField(blank=True, default=False)
    enabled = models.BooleanField(blank=True, default=False)

    class Meta:
        app_label = "ogp"

    @property
    def name(self):
        return self.short_name or self.full_name
    @property
    def fedora_name(self):
        return self.short_name.replace(" ", "_").lower()
    @property
    def fedora_url(self):
        return "%s/place/%s" % (settings.FCREPO_BASE_URL, self.fedora_name)
        
    def __unicode__(self):
        return self.name

@receiver(pre_save, sender=ItemCollection)
def add_short_name(sender, **kwargs):
    i = kwargs['instance']
    if i.short_name == '':
        i.short_name = i.full_name

class DownloadRequest(models.Model):
    email_address = models.EmailField()
    items = models.ManyToManyField(BoundedItem, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=False)
    image_width = models.IntegerField(default=2000)
    wfs_format = models.TextField(null=True, blank=True)

    class Meta:
        app_label = "ogp"

    def create_zip_file_and_notify(self, **kwargs):
        i = self
    
        if not i.active:
            return
    
        zip_file_path = "/media/zip/place_data_for_%s_%d.zip" % (i.email_address, i.id)
        zip_file = zipfile.ZipFile("%s/%s" % (settings.BASE_DIR, zip_file_path), "w")
        
        for item in i.items.all():
            location = "{%s}" if not item.Location[0] == '{' else item.Location
            location = json.loads(location)
    
            if item.DataType == "Book":
                pdf_file_path = "%s/media/pdf/%s.pdf" % (settings.BASE_DIR, item.Name)
                zip_file.write(pdf_file_path, "place_data/%s.pdf" % (item.LayerId))
                zip_file.writestr("place_data/%s.xml" % (item.LayerId), item.FgdcText.encode('utf-8'))
            elif "wfs" in location:
                wfs_path = location["wfs"][0]
                data_file_path = "%s/temp/%s_%d.json" % (settings.BASE_DIR, item.LayerId, i.id)
                data_url = "http://%s/external_wfs/%s?request=GetFeature&typeName=%s:%s&outputFormat=%s&srsName=EPSG:4326" % (settings.ALLOWED_HOSTS[0], wfs_path.replace("http://",""),item.WorkspaceName,item.Name, i.wfs_format)
                urlretrieve(data_url, data_file_path)
                
                extension = None
                if i.wfs_format == "shape-zip":
                    extension = "zip"
                elif i.wfs_format == "GML2" or i.wfs_format == "GML3":
                    extension = "gml"
                elif i.wfs_format == "KML":
                    extension = "kml"
                else:
                    extension = "json"
    
                zip_file.write(data_file_path, "place_data/%s.%s" % (item.LayerId, extension))
                os.remove(data_file_path)
                zip_file.writestr("place_data/%s.xml" % (item.LayerId), item.FgdcText.encode('utf-8'))
            elif "wms" in location:
                wms_path = location["wms"][0]
                image_file_path = "%s/temp/%s_%d.tiff" % (settings.BASE_DIR, item.Name, i.id)
                image_url = "%s/reflect?format=image/geotiff&transparent=true&width=%d&layers=%s" % (wms_path, i.image_width, item.Name)
                urlretrieve(image_url, image_file_path)
                zip_file.write(image_file_path, "place_data/%s.tif" % (item.LayerId))
                os.remove(image_file_path)
                zip_file.writestr("place_data/%s.xml" % (item.LayerId), item.FgdcText.encode('utf-8'))
    
        zip_file.close()
    
    #   send mail with zip link
        mail_server = smtplib.SMTP('cisunix.unh.edu')
        message = MIMEText("Your download request is located at http://%s%s. It will be deleted after 24 hours." % (settings.ALLOWED_HOSTS[0], zip_file_path))
        message["Subject"] = "PLACE Data ready for download"
        message["To"] = i.email_address
        message["From"] = "no-reply@place.sr.unh.edu"
        mail_server.sendmail(message["From"], [i.email_address], message.as_string())
    
        i.active = False
        i.save()

class Category(models.Model):
    name = models.TextField()
    keyword = models.TextField()

    class Meta:
        app_label = "ogp"

    def __unicode__(self):
        return "%s (%s)" % (self.name, self.keyword)

    @property
    def items(self):
        return BoundedItem.objects.filter(ThemeKeywords__icontains=self.keyword)
