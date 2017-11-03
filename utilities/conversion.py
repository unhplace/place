import codecs, csv, os, StringIO, cStringIO

from BeautifulSoup import BeautifulStoneSoup
from django.contrib.gis.geos import Polygon
from PIL import Image
from pyproj import Proj, transform

from utilities.misc import name_from_filepath, ogp_timestamp_for_now, ogp_timestamp_for_year

def points_to_polygon(minX, maxX, minY, maxY):
    coords = ((minX, minY),(minX, maxY),(maxX, maxY),(maxX, minY),(minX,minY))
    return Polygon(coords)

def latlng_to_srs(lat, lng, srs, units='m'):
    srs = unicode(srs)
    if not srs.startswith("EPSG:"):
        srs = "EPSG:%s" % (srs)

    p = Proj(init=srs)
    (x,y) = p(lng, lat)

    m_to_ft_alpha = 3937.0 / 1200.0

    if units == "ft":
        x = x * m_to_ft_alpha
        y = y * m_to_ft_alpha

    return (x,y)

def srs_to_latlng(x,y,srs,units='m'):
    if not unicode(srs).startswith("EPSG:"):
        srs = "EPSG:%s" % (srs)

    ft_to_m_alpha = 1200.0 / 3937.0 #official survey foot to meter conversion

    if units == 'ft':
        x *= ft_to_m_alpha
        y *= ft_to_m_alpha

    p1 = Proj(init=srs)
    p2 = Proj(init="EPSG:4326") #WGS84 srs aka standard Lat./Long. projection

    (lng, lat) = transform(p1, p2, x, y)

    return (lat, lng)

def meter_to_survey_foot(distance):
    m_to_ft_alpha = 3937.0 / 1200.0
    return distance * m_to_ft_alpha

def survey_foot_to_meter(distance):
    ft_to_m_alpha = 1200.0 / 3937.0
    return distance * ft_to_m_alpha

def fgdc_to_ogp_csv(fgdc_path, return_header=False):
    with open(fgdc_path) as f:
        xml = BeautifulStoneSoup(f)

    csv_fields = {}

    csv_fields['DataType'] = xml.find("direct").text

    csv_fields['MinX'] = float(xml.find("westbc").text)
    csv_fields['MaxX'] = float(xml.find("eastbc").text)
    csv_fields['MinY'] = float(xml.find("southbc").text)
    csv_fields['MaxY'] = float(xml.find("northbc").text)

    csv_fields['CenterX'] = (csv_fields['MinX'] + csv_fields['MaxX'])/2
    csv_fields['CenterY'] = (csv_fields['MinY'] + csv_fields['MaxY'])/2
    csv_fields['HalfWidth'] = csv_fields['MaxX'] - csv_fields['CenterX']
    csv_fields['HalfHeight'] = csv_fields['MaxY'] - csv_fields['CenterY']
    csv_fields['Area'] = 4 * csv_fields['HalfWidth'] * csv_fields['HalfHeight']

    csv_fields['Institution'] = "UNH"
    csv_fields['WorkspaceName'] = "ogp"
    csv_fields['Name'] = name_from_filepath(fgdc_path)
    csv_fields['LayerId'] = "%s.%s" % (csv_fields['Institution'], csv_fields['Name'])

    csv_fields['timestamp'] = ogp_timestamp_for_now()
    csv_fields['Availability'] = "Online"
    csv_fields['GeoReferenced'] = "TRUE"

    themes = xml.findAll("themekey")
    csv_fields['ThemeKeywords'] = '"'
    if len(themes) > 0:
        csv_fields['ThemeKeywords'] += '%s' % (themes.pop().text)
        for t in themes:
            csv_fields['ThemeKeywords'] += ', %s' % (t.text)
    csv_fields['ThemeKeywords'] += '"'

    places = xml.findAll("placekey")
    csv_fields['PlaceKeywords'] = '"'
    if len(places) > 0:
        csv_fields['PlaceKeywords'] += '%s' % (places.pop().text)
        for p in places:
            csv_fields['PlaceKeywords'] += ', %s' % (p.text)
    csv_fields['PlaceKeywords'] += '"'

    #pubdate is correct according to the FGDC spec, but OGP expects the date to be in the same format as TimeStamp
    csv_fields['ContentDate'] = content_date_for_map(xml.find("timeperd").find("caldate").text)
    csv_fields['Originator'] = xml.findAll("origin")[-1].text
    csv_fields['LayerDisplayName'] = xml.find("title").text.replace("Historic Digital Raster Graphic - ", "")
    csv_fields['Publisher'] = xml.find("publish").text

    csv_fields['Access'] = "Public"
    csv_fields['Abstract'] = xml.find("abstract").text
    csv_fields['Location'] = '{"wms": ["https://place.sr.unh.edu:8080/geoserver/wms"]}'
    csv_fields['FgdcText'] = unicode(xml)

    fields = sorted(csv_fields.keys())
    data = []

    stringIO = cStringIO.StringIO()
    writer = UnicodeWriter(stringIO)

    for field in fields:
        v = csv_fields[field]
        if type(csv_fields[field]) == float:
            v = str(v)
            
        data.append(v)

    writer.writerow(data)

    csv_row = stringIO.getvalue()
    
    stringIO.close()

    if return_header:
        stringIO = StringIO.StringIO()
        writer = csv.writer(stringIO)
        writer.writerow(fields)
        header_row = stringIO.getvalue()
        stringIO.close()

        return (header_row, csv_row)
    else:
        return csv_row

def image_path_with_fgdc_to_world_file(image_path, world_file, srs, units="m"):
    image = Image.open(image_path)
    (width, height) = image.size

    xml_path = "%s.xml" % (os.path.splitext(image_path)[0])
    with open(xml_path, "r") as f:
        xml = BeautifulStoneSoup(f)

    north_bound = float(xml.find("northbc").text)
    west_bound = float(xml.find("westbc").text)
    south_bound = float(xml.find("southbc").text)
    east_bound = float(xml.find("eastbc").text)

    srs = "%s" % (srs)
    if not srs.startswith("EPSG:"):
        srs = "EPSG:%s" % (srs)

    (west_bound, north_bound) =  latlng_to_srs(north_bound, west_bound, srs, units) 
    (east_bound, south_bound) = latlng_to_srs(south_bound, east_bound, srs, units)

    x_pixel_width = (east_bound - west_bound) / width
    y_pixel_width = (south_bound - north_bound) / height

    for l in [x_pixel_width, 0, 0, y_pixel_width, west_bound, north_bound]:
        world_file.write("%s\n" % l)

    return world_file

def content_date_for_map(date):
    if (type(date) == unicode or type(date) == str) and len(date) == 4:
        return ogp_timestamp_for_year(date)
    else:
        return ogp_timestamp_for_now()

class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)
