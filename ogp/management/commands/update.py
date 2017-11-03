from django.core.management.base import BaseCommand, CommandError

from ogp.models import BoundedItem, ItemCollection

import requests

#from place.settings import EXT_SOLR_REPOS
from django.conf import settings
EXT_SOLR_REPOS = settings.EXT_SOLR_REPOS

class Command(BaseCommand):
    help = 'Update the database using the dictionary EXT_SOLR_REPOS from the settings file.'

    def add_arguments(self, parser):
        parser.add_argument("task", type=str)
        parser.add_argument("--repo", type=str)

    def handle(self, *args, **options):
        task = options["task"]
        repo = options["repo"]

        if not task in ("full", "incremental"):
            raise CommandError("task must be either 'full' or 'incremental'")

        if repo:
            repos = {repo: EXT_SOLR_REPOS[repo]}
        else:
            repos = EXT_SOLR_REPOS

        for k in repos:
            url = "http://%s/solr/select" % (repos[k]["url"])
            institutions = repos[k]["institutions"]

            if len(institutions) > 0:
                institutions_string = "Institution:(%s" % (institutions[0])
                fields = "Abstract,Access,Area,CenterX,CenterY,ContentDate,DataType,FgdcText,GeoReferenced,HalfHeight,HalfWidth,Institution,LayerDisplayName,LayerId,Location,MaxX,MinX,MaxY,MinY,Name,Originator,PlaceKeywords,Publisher,ThemeKeywords,WorkspaceName,timestamp"


                for i in range(1,len(institutions)):
                    institution = institutions[i]
                    institutions_string += "+OR+%s" % (institution)

                institutions_string += ")"

                url += "?q=Access:Public"

                if "datatypes" in repos[k]:
                    url += "+AND+DataType:(%s)" % ("+OR+").join(repos[k]["datatypes"])
                else:
                    url += "+AND+DataType:(Raster+OR+Scanned+Map+OR+Paper+Map+OR+Point+OR+Line+OR+Polygon)"

                url += "+AND+%s" % (institutions_string)

                if task == "full":
                    self.stdout.write("PLACE External Solr Full Update")
                elif task == "incremental":
                    self.stdout.write("PLACE External Solr Incremental Update")
                    url += "+AND+timestamp:[NOW/DAY-7DAYS+TO+NOW]"

                num_found = requests.get("%s&rows=0&wt=json" % (url)).json()["response"]["numFound"]

                if num_found > 0:
                    self.stdout.write("Loading %d items" % (num_found))
                    url += "&fl=%s&rows=%d&wt=json" % (fields, num_found)
                    new_items = requests.get(url).json()["response"]["docs"]

                    for new_item in new_items:
                        b = BoundedItem.from_json(new_item)
                        if not b.collection:
                            b.collection = ItemCollection.objects.get(short_name = new_item["Institution"])
                        try:
                            b.save()
                        except:
                            self.stdout.write("Invalid: %s" % (b.LayerDisplayName))

                        if task == "incremental":
                            self.stdout.write(b.LayerDisplayName)
                    if task == "full":
                        self.stdout.write("%d items added" % (num_found))
                else:
                    self.stdout.write("%s: No new items found." % (k))
