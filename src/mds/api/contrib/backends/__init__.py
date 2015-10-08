'''
Provides access to pluggable backend infrastructucture.

Target backends must be configured in the settings by adding
the desired backend to the value of the TARGET variable.
'''
import logging

from django.conf import settings
from django.db import models

from .handlers import AbstractHandler, FakeHandler
"""
__all__ = [
    'autocreate',
    'AbstractHandler',
    'register_handler',
    'remove_handler',
    'get_handlers',
    'create',
    'read',
    'update',
    'delete',
]
"""
_handlers = {
    'Concept': [],
    'RelationShip': [],
    'RelationshipCategory':[],
    'Device': [],
    'Encounter': [],
    'Event': [],
    'Instruction': [],
    'Location':[],
    'Notification': [],
    'Procedure':[],
    'Observation':[],
    'Observer': [],
    'Procedure': [],
    'Subject':[],
}

_handler_registry = {}

def autocreate(handler_dict=None):
    ''' Auto configures the backend handlers based on the value of
        TARGETS in the settings.
    '''
    if not handler_dict:
        try:
            handler_dict = settings.TARGETS
        except:
            raise ImportError('TARGETS must be defined in settings.py')

    for model, handler_strs in handler_dict.items():
        for handlers in handler_strs:
            for handler in handler_strs:
                register_handler(model,handler)

def register_handler(model, target):
    if isinstance(target, AbstractHandler):
        handler = target
    else:
        handler = importlib.import_module(target)
    handler_list = _handlers.get(model,[])
    if not handler in handler_list:
        handler_list.append(handler)
    _handlers[model] = handler_list

def remove_handler(model, target):
    handler_list = _handlers.get(model,[])
    if not handler in handler_list:
        handler_list.append(handler)
    _handlers[model] = handler_list


def get_handler_method(handler_instance, method, model):
        method_str = '{method}_{model}'
        handler_instance = handler_getter(auth=auth)
        handler_callable = handler_instance.getattr(
            method_str.format(method=method, model=model.lower()), None)
        return handler_callable
        
def get_handler_instance(handler_module, **initkwargs):
        handler_mod = importlib.import_module(handler_str)
        handler_klazz = getattr(handler_mod, 'get_handler', FakeHandler) 
        return handler_klazz(initkwargs)

def get_handlers(model, method, **initkwargs):
    ''' Returns the callable for sending the instance 
        to the target.
    '''
    if isinstance(model, models.Model):
        model = model.__name__
    handlers = [ get_handler_instance(x, initkwargs) for x in _handlers.get(model, [])]
    handler_callers = [ get_handler_method(x(initkwargs)) for x in handlers]
    return handler_callers

def dispatch(handlers, instance, auth=None, **methodkwargs):
    ''' Invokes the callable handler for each handlers provided in the
        'handlers" iterable. The first item in the handler
    '''
    result = None
    for handler in handlers:
        _result = caller(instance, auth=auth, **methodkwargs)
        result = _result if not result else result
    return result

def create(instance, auth=None, methodkwargs={}, **initkwargs):
    ''' Handles the instance creation in the backend and returns a list
        of objects created.
        
        This effectively wraps a POST call to the dispatch server and
        forwards it to the frontend. The first handler registered will
        be used as the primary 
    '''
    model = instance.__class__.__name__
    handlers = get_handlers(model,'create', **initkwargs)
    result = dispatch(handlers, instance, auth=auth, **methodkwargs)
    return result

def read(instance, auth=None, methodkwargs={},**initkwargs):
    ''' Handles the instance fetch in the backend and returns a list
        of objects created.
        
        This effectively wraps a POST call to the dispatch server and
        forwards it to the frontend. The first handler registered will
        be used as the primary 
    '''
    model = instance.__class__.__name__
    handlers = get_handlers(model,'read', **initkwargs)
    result = dispatch(handlers, instance, auth=auth, **methodkwargs)
    return result

def update(model, obj, auth=None, methodkwargs={}, **initkwargs):
    ''' Handles the instance fetch in the backend and returns a list
        of objects created.
        
        This effectively wraps a PUT call to the dispatch server and
        forwards it to the frontend. The first handler registered will
        be used as the primary 
    '''
    model = instance.__class__.__name__
    handlers = get_handlers(model,'update', **initkwargs)
    result = dispatch(handlers, instance, auth=auth, **methodkwargs)
    return result

def delete(instance, auth=None, methodkwargs={}, **initkwargs):
    ''' Handles the instance delete in the backend and returns a list
        of objects created.
        
        This effectively wraps a DELETE call to the dispatch server and
        forwards it to the frontend. The first handler registered will
        be used as the primary 
    '''
    model = instance.__class__.__name__
    handlers = get_handlers(model,'delete', **initkwargs)
    result = dispatch(handlers, instance, auth=auth, **methodkwargs)
    return result