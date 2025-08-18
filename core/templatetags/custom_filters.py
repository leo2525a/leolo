# core/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    # Check if the dictionary is valid before trying to get an item
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None