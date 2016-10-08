'''
Created on Feb 29, 2012

:Authors: Sana Dev Team
:Version: 2.0
'''
import logging
import cjson
    
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.paginator import Paginator, InvalidPage, EmptyPage, PageNotAnInteger
from django.db.models import ForeignKey
from piston.handler import BaseHandler
from piston.utils import rc

from .decorators import validate
from .responses import succeed, error, bad_request
from .utils import logstack, printstack, exception_value
from mds.utils import auth
from mds.api.contrib import backends

__all__ = ['DispatchingHandler', ]


class UnsupportedCRUDException(Exception):
    def __init__(self, value):
        self.value = value
        
    def __unicode__(self):
        return unicode(self.value)

def get_root(request):
    host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    result = scheme + '://' + host
    return result

def get_start_limit(request): 
    get = dict(request.GET.items())
    limit = int(get.get('limit', 0))
    start = int(get.get('start', 1))
    return start, limit
    

class HandlerMixin(object):
    fks = None
    m2m = None
    
    def __init__(self,*args,**kwargs):
        super(HandlerMixin,self)
        self.fks = self.get_foreign_keys()
        self.m2m = self.get_m2m_keys()
        self.model = getattr(self,'model',None)
        self._model = None
            
    def get_foreign_keys(self):
        foreign_keys = []
        if hasattr(self,'model'):
            _meta = getattr(self,'model')._meta
        else:
            return None
        for field in _meta.fields:
            if isinstance(_meta.get_field_by_name(field.name)[0], ForeignKey):
                foreign_keys.append(field.name)
        if not foreign_keys:
            return []
        return foreign_keys
    
    def get_m2m_keys(self):
        m2m = []
        if hasattr(self,'model'):
            _meta = getattr(self,'model')._meta
            for field in _meta.many_to_many:
                m2m.append(field.name)
        return m2m

class DispatchingHandler(BaseHandler,HandlerMixin):
    """Base HTTP handler for Sana api. Uses basic CRUD approach of the  
       django-piston api as a thin wrapper around class specific functions.
    """
    exclude = ['id',]
    allowed_methods = ['GET','POST','PUT','DELETE']

    def queryset(self, request, uuid=None, **kwargs):
        model = self.get_model()
        if uuid:
            return self.self.get_model().objects.get(uuid=uuid)
        else:
            qs = self.get_model().objects.all()
            if kwargs:
                qs.filter(**kwargs)
            return qs
        
    def get_model(self):
        if not self._model:
            self._model = getattr(self, 'model')
        return self._model

    @validate('POST')
    def create(self,request, uuid=None, *args, **kwargs):
        """ POST Request handler. Requires valid form defined by model of  
            extending class.
        """
        logging.info("create(): %s" % (request.user))
        if uuid:
            return self.update(request,uuid=uuid)
        try:
            # Always cache the object
            instance = self._create(request, args, kwargs)
            logging.info('successfully cached object')
            
            # Send to any linked backends
            _instance = backends.create(instance,auth=auth.parse_auth(request))
            # If a remote is listed as the target we 
            # assume uuuid is set by the remote
            if not settings.TARGET == 'SELF':
                if _instance:
                    if  _instance.uuid != instance.uuid:
                        logging.info('updating object uuid=%s' % _instance.uuid)
                        instance.uuid = _instance.uuid
                    else:
                        logging.info('remote uuid is equal')
                else:
                    logging.info('NoneType instance returned')
            # Persist object here
            instance.save()
            logging.info('POST success object.uuid=%s' % instance.uuid)
            model = getattr(self,'model')
            return succeed(model.objects.filter(uuid=instance.uuid))
        except Exception, e:
            logging.error('ERROR')
            return self.trace(request, e)
      
    def read(self,request, uuid=None, related=None,*args,**kwargs):
        """ GET Request handler. No validation is performed. """
        logging.info("read: %s, %s, %s" % (self.model,request.method,request.user))
        size = -1
        try:
            if uuid and related:
                response = self._read_by_uuid(request,uuid, related=related)
                size = response.count() if response else 0
            elif uuid:
                response = self._read_by_uuid(request,uuid)
                size = response.count() if response else 0
            else:
                # get a mutable QueryDict so that any control
                # params that aren't Model fields can be popped-i.e. page
                query_dict = request.GET.copy()
                start = self.get_start(query_dict)
                limit = self.get_limit(query_dict)
                
                attrs = self.flatten_dict(query_dict)
                
                
                # handle m2m fields
                for _m2m in self.m2m:
                    m2m_value = attrs.pop(_m2m, None)
                    if m2m_value:
                        m2m_query = "{0}__uuid__in".format(_m2m)
                        attrs[m2m_query] = m2m_value
                
                # Handle any explicit in queries
                for k,v in attrs.items():
                    if "__in" in k:
                        attrs[k] = [x for x in v.split(",")]
                        
                
                if len(attrs) > 0:
                    qs = BaseHandler.read(self,request,**attrs)
                else:
                    qs = self.queryset(request)
                response, size = self.get_chunk(qs, start, limit)
            return succeed(response, size=size)
        except ValueError, e:
            return bad_request(exception=e)
        except Exception, e:
            return self.trace(request, e)
            
    @validate('PUT')
    def update(self, request, uuid=None):
        """ PUT Request handler. Allows single item updates only. """
        logging.info("update(): %s, %s" % (request.method,request.user))
        try:
            if not uuid:
                raise Exception("UUID required for update.")
            msg = self._update(request, uuid)
            model = getattr(self,'model')
            logging.info("Success updating {klazz}:{uuid}".format(
                klazz=model, uuid=uuid))
            return succeed(model.objects.filter(uuid=uuid))
        except Exception, e:
            return self.trace(request, e)
    
    def delete(self,request, uuid=None):
        """ DELETE Request handler. No validation is performed. """
        logging.info("delete(): %s, %s" % (request.method,request.user))
        try:
            if not uuid:
                raise Exception("UUID required for delete.")
            msg = self._delete(uuid)
            return succeed(msg)
        except Exception, e:
            return self.trace(request, e)


    def get_start(self, query_dict):
        try:
            start = int(query_dict.pop('start'))
        except:
            start = 1
        return start
        
    def get_limit(self, query_dict):
        try:
            limit = int(query_dict.pop('limit'))
        except:
            limit = None
        return limit
        
    def get_chunk(self, qs, start=None, limit=None):
        if start and limit:
            paginator = Paginator(qs, limit)
            try:
                chunk = paginator.page(start).object_list
                size = paginator.num_pages
            except EmptyPage:
                # If page is out of range deliver empty
                chunk = self.empty()
                size = 0 
        else:
            chunk = qs
            size = qs.count() if qs else 0
        return chunk, size
        
        
    def empty(self):
        return self.model.objects.none()

    def trace(self,request, ex=None):
        try:
            if settings.DEBUG:
                logging.error(unicode(ex))
            _,message,_ = logstack(self,ex)
            return error(message)
        except:
            return error(exception_value(ex))
    
    def _create(self,request, *args, **kwargs):
        data = request.form.cleaned_data
        raw_data = request.raw_data
        klazz = getattr(self,'model')
        
        uuid = raw_data.get('uuid',None)
        # Check if exists
        if uuid:
            logging.info("Has uuid: %s" % uuid)
            qs = klazz.objects.filter(uuid=uuid)
            if qs.count() == 1:
                return self._update(request,uuid=uuid)
            elif qs.count() > 1:
                raise MultipleObjectsReturned("{0} '{1}'".format(klazz.__name__, uuid))
            else:
                data['uuid'] = uuid
        created = raw_data.get('created', None)
        # override default created if present
        if created:
            data['created'] = created
        instance = klazz(**data)
        return instance
    
    
    def _read_multiple(self, request, *args, **kwargs):
        """ Returns a zero or more length list of objects.
        """
        start, limit = get_start_limit(request)
        model = self.get_model()
        obj_set = model.objects.all()
        if limit:
            paginator = Paginator(obj_set, limit, 
                                  allow_empty_first_page=True)
            try:
                objs = paginator.page(start).object_list
            except (EmptyPage, InvalidPage):
                objs = paginator.page(paginator.num_pages).object_list      
        else:
            objs = obj_set
        return objs

    def _read_by_uuid(self,request, uuid, related=None):
        """ Reads an object from the database using the UUID as a slug and 
            will return the object along with a set of related objects if 
            specified.
        """
        obj = BaseHandler.read(self,request,uuid=uuid)
        if not related:
            return obj
        return getattr(obj[0], str(related) + "_set").all()

    def _update(self,request, uuid):
        logging.info("_update() %s" % uuid)
        model = getattr(self,'model')
        data = request.raw_data
        if 'uuid' in data.keys():
            uuid = data.pop('uuid')
        
        qs = model.objects.filter(uuid=uuid)
        if qs.count() == 1:
           qs.update(**data)
        # No objects found raise
        elif qs.count() == 0:
            raise ObjectDoesNotExist("{0} '{1}'".format(model.__name__, uuid)) 
        # more than one raise
        else:
            raise MultipleObjectsReturned("{0} '{1}'".format(model.__name__, uuid))
        return model.objects.get(uuid=uuid)
    
    def _delete(self,uuid):
        model = getattr(self,'model')
        model.objects.delete(uuid=uuid)
        return "Successfully deleted {0}: {1}".format(model.__class__.__name__,uuid)

