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

from .taskmanager import TaskNotifier
from .translate import tr

from abc import ABC, abstractmethod

class StacClient(ABC):
    def __init__(self, notifier:TaskNotifier):
        def sr4326():
            sr = osr.SpatialReference()
            sr.ImportFromEPSG( 4326 )
            return sr

        self.SEARCH_URL = None # Sub Class
        self.LIMIT = 10

        self.notifier = notifier
        self.collection = None # dict

        self._session = requests.Session()
        # session.headers.update({'Authorization': 'Bearer SEU_TOKEN'})

        self._features = {}
        self._feat_key_res_xy = 'spatial_res'
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
            msg_error = tr("The request has timed out ({}).\nPlease check your internet connection or try again later").format( self.SEARCH_URL )
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

    def getFeatures(self)->List[dict]:
        return self._features

    @abstractmethod
    def search(
            self,
            bbox:list,
            dates:list,
            isCanceled:Callable[[str], None]
        )->dict:
        pass

    @abstractmethod
    def getScenesByDateOrbitsCRS(self, spatial_resolution:str)->dict:
        pass

