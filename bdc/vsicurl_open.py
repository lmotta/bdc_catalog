# -*- coding: utf-8 -*-
"""
/***************************************************************************
Open URL for QGIS
                                 Functions open URL for QGIS
                             -------------------
        begin                : 2025-09-02
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

from osgeo import gdal

def setConfigOptionUrl()->None:
    gdal.SetConfigOption('CPL_VSICURL_TIMEOUT', '45')
    gdal.SetConfigOption('CPL_VSICURL_CONNECT_TIMEOUT', '10')
    gdal.SetConfigOption('CPL_VSICURL_RETRIES', '2')
    gdal.SetConfigOption('CPL_VSICURL_RETRY_DELAY', '3')

def setConfigClearUrl()->None:
    gdal.SetConfigOption('CPL_VSICURL_TIMEOUT', None)
    gdal.SetConfigOption('CPL_VSICURL_CONNECT_TIMEOUT', None)
    gdal.SetConfigOption('CPL_VSICURL_RETRIES', None)
    gdal.SetConfigOption('CPL_VSICURL_RETRY_DELAY', None)


def openUrl(url:str)->dict:
    try:
        ds = gdal.Open(f"/vsicurl/{url}", gdal.GA_ReadOnly)

    except Exception as e:
        return {
            'is_ok': False,
            'message': str(e)
        }
    
    return {
        'is_ok': True,
        'dataset': ds
    }
