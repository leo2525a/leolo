# core/templatetags/custom_filters.py

from django import template
import json
from django.utils.safestring import mark_safe
from datetime import date

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    # 這個過濾器讓您在樣板中能用變數作為字典的鍵來取值
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None

@register.filter(name='jsonify')
def jsonify(data):
    """
    安全地將 Python 物件（包含日期）轉換為 JSON 字串。
    """
    def date_converter(o):
        if isinstance(o, date):
            return o.isoformat() # 將 date 物件轉為 'YYYY-MM-DD' 格式的字串

    if isinstance(data, dict):
        # 將字典的鍵（如果是 date 物件）也轉換為字串
        str_keyed_data = {k.isoformat() if isinstance(k, date) else k: v for k, v in data.items()}
        return mark_safe(json.dumps(str_keyed_data, default=date_converter))
    
    return mark_safe(json.dumps(data, default=date_converter))