import os, json

from .translate import tr

def configCollection()->dict:
    filename = 'collection.json'
    collection = {}

    filedir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join( filedir, filename )
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            collection = json.load(f)
    except json.JSONDecodeError:
        msg = tr("Error: Invalid JSON file ('{}') - {}").format(filepath, e)
        raise ValueError(msg)
    except Exception as e:
        msg = tr("Error: JSON file ('{}') - {}").format(filepath, e)
        raise ValueError(msg)

    return collection