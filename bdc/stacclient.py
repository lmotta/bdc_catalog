# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Stac Client
                            Abstract Class
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

import requests
from typing import Callable, List

from osgeo import osr
#gdal.SetConfigOption("GDAL_HTTP_HEADER", "Authorization: Bearer SEU_TOKEN")

from .translate import tr

from abc import abstractmethod

from qgis.PyQt.QtCore import QObject, pyqtSignal


class StacClient(QObject):
    def __init__(self):
        def sr4326():
            sr = osr.SpatialReference()
            sr.ImportFromEPSG( 4326 )
            return sr

        self.STAC_URL = None # Sub Class
        self.LIMIT = 10

        self.collection = None # dict
        self._collections_cog_bands_meta = {}

        self._session = requests.Session()
        # session.headers.update({'Authorization': 'Bearer SEU_TOKEN'})

        self._features = {}
        self._feat_key_spatial_res = 'spatial_res'
        self._feat_key_crs = 'crs'
        self._feat_key_orbit_crs = f"orbit_{self._feat_key_crs}"

        self._request_count = None
        
        self._srs4326 = sr4326()

    def _getResponse(self, args:dict)->dict:
        msg_error = None
        try:
            response = self._session.get( **args)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            msg_error = str(err)
        except requests.exceptions.Timeout:
            msg_error = tr("The request has timed out ({}).\nPlease check your internet connection or try again later").format( self.STAC_URL )
        except requests.exceptions.RequestException as err:
            msg_error = str(err)
        
        if not msg_error is None:
            return {
                'is_ok': False,
                'message': msg_error
            }
        
        return {
            'is_ok': True,
            'response': response
        }

    def _setCollectionsCOGBandsMeta(self)->dict:
        def getSpatialRes(value):
            keys = self.collection['spatial_res'].split(',')
            
            spatial_res = value[ keys[0] ][0][ keys[1] ] if (
               isinstance( value[ keys[0]], list ) 
            ) else value[ keys[0] ]

            return f"{int(spatial_res)}x{int(spatial_res)}"

        args = {
            'url': f"{self.STAC_URL}/collections/{self.collection['id']}"
        }
        r = self._getResponse( args )
        if not r['is_ok']:
            return r

        result = r['response'].json()
        isBand = lambda value: (
                'profile=cloud-optimized' in value['type']
            ) and (
                self.collection['band_list'] in value and 
                len( value[ self.collection['band_list'] ] ) == 1
        )
        assets = [ asset for asset, value in result['item_assets'].items() if isBand( value ) ]

        meta = { 
            asset: {
                self._feat_key_spatial_res: getSpatialRes( result['item_assets'][ asset] )
            }
            for asset in assets
        }
        self._collections_cog_bands_meta[ self.collection['id'] ]  = meta
        
        return { 'is_ok': True }

    def getFeatures(self)->List[dict]:
        return self._features

    def getScenesByDateOrbitsCRS(self, spatial_resolution:str)->dict:
        scene_list = {}
        for asset, data in self._features.items():
            p = data['properties']
            scene_key = f"{p['datetime'].split('T')[0]}_{p[ self._feat_key_orbit_crs ]}"
            urls = { asset: { band: f"{value['href']}" for band, value in data['bands'].items() if value[ self._feat_key_spatial_res ] == spatial_resolution } }
            if not scene_key in scene_list:
                scene_list[ scene_key ] = [ urls ]
                continue
            scene_list[ scene_key ].append( urls )
        
        return scene_list

    @abstractmethod
    def search(
            self,
            bbox:list,
            dates:list,
            requestProcessData:pyqtSignal,
            isCanceled:Callable[[str], None]
        )->dict:
        pass

