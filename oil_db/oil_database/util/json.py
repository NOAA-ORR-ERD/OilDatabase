'''
    JSON Oil record utility functions.

    These are general functions to be used primarily for helping us deal
    with an incoming JSON oil record.
'''
from bson.objectid import ObjectId


def jsonify_oil_record(oil):
    try:
        # if we are a PyMODM object, we transform it to a dict
        oil_dict = oil.to_son().to_dict()
    except Exception:
        oil_dict = oil

    fix_bson_ids(oil_dict)

    return oil_dict


def fix_bson_ids(json_data):
    '''
        JSON, specifically the ujson package, is having problems representing
        the BSON special ObjectId fields.  So we need to turn them into
        something representable, like a string, before sending our JSON back
        in a response.
    '''
    if isinstance(json_data, ObjectId):
        return str(json_data)
    elif isinstance(json_data, dict):
        for k, v in json_data.iteritems():
            json_data[k] = fix_bson_ids(v)

        return json_data
    elif isinstance(json_data, (list, tuple)):
        for i, v in enumerate(json_data):
            json_data[i] = fix_bson_ids(v)

        return json_data
    elif isinstance(json_data, set):
        tmp_list = list(json_data)

        for i, v in enumerate(tmp_list):
            tmp_list[i] = fix_bson_ids(v)

        return set(tmp_list)
    else:
        return json_data


def json_to_bson_obj_id(json_data):
    '''
        JSON, specifically the ujson package, is having problems representing
        the BSON special fields.  So any BSON id fields will probably not have
        an ObjectId type, but a string.  So we need to turn it into an ObjectId
        in order to use it.
        - We will not traverse the entire structure for the moment.
        - We will let the caller handle any exceptions
    '''
    if ('_id' in json_data and
            json_data['_id'] is not None and
            not isinstance(json_data['_id'], ObjectId)):
        json_data['_id'] = ObjectId(json_data['_id'])


class ObjFromDict(object):
    '''
        Generalized method for interpreting a nested data structure of
        dicts, lists, and values, such as that coming from a parsed
        JSON string.  We consume this data structure and represent it
        as a structure of linked python objects.

        So instead of needing to access our data like this:
            json_obj['densities'][0]['ref_temp_k']
        we can do this instead:
            json_obj.densities[0].ref_temp_k
    '''
    def __init__(self, data):
        try:
            for name, value in data.iteritems():
                setattr(self, name, self._wrap(value))
        except AttributeError:
            raise ValueError('Top level of JSON structure must be dict')

    def _wrap(self, value):
        if isinstance(value, (tuple, list, set, frozenset)):
            return type(value)([self._wrap(v) for v in value])
        elif isinstance(value, dict):
            return ObjFromDict(value)
        else:
            return value
