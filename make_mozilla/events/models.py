from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis import geos, measure
from django_countries import CountryField
from django.utils.safestring import mark_safe
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

from datetime import datetime
from tower import ugettext_lazy as _

from make_mozilla.base.html import bleached

import hashlib


class Venue(models.Model):
    name = models.CharField(max_length=255)
    street_address = models.TextField()
    country = CountryField()
    location = models.PointField(blank=True)

    objects = models.GeoManager()

    def __init__(self, *args, **kwargs):
        super(Venue, self).__init__(*args, **kwargs)
        if self.location is None:
            longitude = float(kwargs.get('longitude', '0'))
            latitude = float(kwargs.get('latitude', '0'))
            self.location = geos.Point(longitude, latitude)

    def __unicode__(self):
        return '%s - %s, %s' % (self.name, self.street_address,  self.country)

    @property
    def latitude(self):
        return self.location.y

    @latitude.setter
    def latitude(self, value):
        self.location.y = value

    @property
    def longitude(self):
        return self.location.x

    @longitude.setter
    def longitude(self, value):
        self.location.x = value

class Event(models.Model):
    name = models.CharField(max_length = 255)
    url_hash = models.CharField(max_length = 20, blank = True)
    description = models.TextField()
    event_url = models.URLField(blank = True)
    venue = models.ForeignKey(Venue)
    start = models.DateTimeField(null = True, blank = True)
    end = models.DateTimeField(null = True, blank = True)
    source = models.CharField(max_length = 255, blank = True)
    source_id = models.CharField(max_length = 255, blank = True)
    organiser_email = models.EmailField(max_length = 255)
    campaign = models.ForeignKey('Campaign', null = True, blank=True)
    kind = models.ForeignKey('EventKind', null = True)
    verified = models.BooleanField(default = False)
    official = models.BooleanField(default = False)
    public = models.BooleanField(default = False)
    pending_deletion = models.BooleanField(default = False)

    objects = models.GeoManager()

    def save(self, *args, **kwargs):
        super(Event, self).save(*args, **kwargs)
        if not self.url_hash:
            # We have to do this after a save, because we need an ID from the DB
            self.url_hash = hashlib.sha224('%d' % self.id).hexdigest()[:9]
            self.save()

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        if self.bsd_hosted():
            return self.event_url
        else:
            return reverse('event', kwargs={'event_hash': self.hash})

    @property
    def hash(self):
        if not self.url_hash:
            self.save()
        return self.url_hash

    @property
    def bleached_description(self):
        return bleached(self.description)

    def bsd_hosted(self):
        return self.source == 'bsd'

    def verify_ownership(self, user):
        return user.email == self.organiser_email

    @classmethod
    def all_upcoming(cls, sort='start'):
        resultset = cls.objects.filter(start__gte = datetime.now()).order_by(sort)
        return resultset

    @classmethod
    def upcoming(cls, sort='start', include_private=False):
        resultset = cls.all_upcoming(sort).filter(verified = True, pending_deletion = False)
        if not include_private:
            resultset = resultset.filter(public=True)
        return resultset

    @classmethod
    def near(cls, latitude, longitude, sort='start', include_private=False):
        point = geos.Point(float(longitude), float(latitude))
        return cls.upcoming(sort, include_private).filter(venue__location__distance_lte=(point, measure.D(mi=50)))

    @classmethod
    def all_user_non_bsd(cls, user):
        return cls.objects.filter(organiser_email = user.email).exclude(source = 'bsd').order_by('start')

    @classmethod
    def all_user_bsd(cls, user):
        return cls.objects.filter(organiser_email = user.email, source = 'bsd').order_by('start')

    @classmethod
    def all_upcoming_bsd(cls):
        return cls.all_upcoming().filter(source = 'bsd')

class EventAndVenueUpdater(object):
    @classmethod
    def update(cls, event, new_event, venue, new_venue):
        if not cls.are_model_instances_identical(venue, new_venue):
            venue = new_venue
        venue.save()
        if not cls.are_model_instances_identical(event, new_event):
            if event.id:
                new_event.id = event.id
            event = new_event
        event.venue = venue
        event.save()

    @classmethod
    def are_model_instances_identical(cls, instance1, instance2):
        if not (type(instance1) == type(instance2)):
            return False
        local_fields = [f for f in instance1._meta.local_fields if not f.primary_key]
        def comparator(initial, field):
            return initial and (field.value_from_object(instance1) == field.value_from_object(instance2))
        return reduce(comparator, local_fields, True)


class Campaign(models.Model):
    name = models.CharField(max_length = 255)
    description = models.TextField()
    logo = models.ImageField(upload_to = 'campaigns', storage = FileSystemStorage(**settings.UPLOADED_IMAGES))
    slug = models.SlugField()
    start = models.DateField()
    end = models.DateField()

    #  campaign logo's were being a pain, hopefully less so now
    def check_logo(self):
        return self.logo.storage.exists(self.logo.name)

    @classmethod
    def current(self):
        today = datetime.today().date()
        try:
            return self.objects.filter(start__lte=today, end__gte=today).order_by('start').get()
        except ObjectDoesNotExist:
            return None

    def __unicode__(self):
        return '%s - %s to %s' % (self.name, self.start, self.end)

class EventKind(models.Model):
    name = models.CharField(max_length = 255)
    description = models.TextField()
    figures = models.TextField(blank=True, null=True)
    additional = models.TextField(blank=True, null=True)
    slug = models.SlugField()

    def __unicode__(self):
        return mark_safe(u'%s' % (self.name))


class Partner(models.Model):
    name = models.CharField(max_length=255)
    website = models.URLField()
    logo = models.ImageField(
        upload_to='partners',
        storage=FileSystemStorage(**settings.UPLOADED_IMAGES)
    )
    featured = models.BooleanField(default=False,
        help_text=_(u'Featured partners are displayed on the home and campaign page'))
    for_campaign = models.ForeignKey(Campaign)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('name',)
