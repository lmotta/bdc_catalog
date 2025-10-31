# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Config Collection function
 
                             -------------------
        begin                : 2025-10-15
        copyright            : (C) 2025 by Luiz Motta
        email                : motta.luiz@gmail.com

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 """

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