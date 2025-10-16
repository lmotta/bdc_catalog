# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BDC Catalog
                                 A QGIS plugin
 Plugin to access Brasil Data Cube for show COG scenes
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

import requests
import json
from typing import Callable, List

from osgeo import gdal, ogr, osr
#gdal.SetConfigOption("GDAL_HTTP_HEADER", "Authorization: Bearer SEU_TOKEN")

from qgis.core import Qgis
from qgis.PyQt.QtCore import QObject

from .bdc_taskmanager import TaskNotifier
from .vsicurl_open import openUrl
from .translate import tr

def intersects(bbox: list, json_geom: dict)->bool:
    geom = ogr.CreateGeometryFromJson( json.dumps( json_geom ) )
    
    ( min_x, min_y, max_x, max_y ) = bbox
    ring = ogr.Geometry( ogr.wkbLinearRing )
    ring.AddPoint_2D( min_x, min_y )
    ring.AddPoint_2D( max_x, min_y )
    ring.AddPoint_2D( max_x, max_y )
    ring.AddPoint_2D( min_x, max_y )
    ring.AddPoint_2D( min_x, min_y )
    geom_bbox = ogr.Geometry( ogr.wkbPolygon )
    geom_bbox.AddGeometry( ring )
    
    return geom_bbox.Intersects( geom )


class BDCStacClient():
    def __init__(self, notifier:TaskNotifier):
        def sr4326():
            sr = osr.SpatialReference()
            sr.ImportFromEPSG( 4326 )
            return sr

        self.SEARCH_URL = 'https://data.inpe.br/bdc/stac/v1/search'  
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

    def search(
            self,
            bbox:list,
            dates:list,
            footprint_band:str,
            isCanceled:Callable[[str], None]
        )->dict:
        def processResponse(response)->dict:
            def getCRS(ds)->dict:
                sr = ds.GetSpatialRef()
                #return f"{sr.GetAuthorityName(None)}-{sr.GetAuthorityCode(None)}"
                return sr.GetAuthorityCode(None)

            def getSpatiaResolution(url:str)->dict:
                r = openUrl( url )
                if not r['is_ok']:
                    return r

                (_, res_x, _,_, _, res_y) = r['dataset'].GetGeoTransform()
                r['dataset'] = None

                return {
                    'is_ok': True,
                    'spatial_res': f"{res_x}x{-1*res_y}"
                }

            def getFootprint(dataset_url):
                band = dataset_url.GetRasterBand(1)
                overview = int(band.GetOverviewCount() / 2)
                if band.GetNoDataValue() is None:
                    band.SetNoDataValue( 0.0 )

                (_, res_x, _, _, _, res_y) = dataset_url.GetGeoTransform()
                mean_res = ( res_x + -1*res_y ) / 2
                mean_size = ( dataset_url.RasterXSize + dataset_url.RasterXSize ) / 2 
                factor = mean_res * mean_size / 100
                factor /= 1120000 # meter->degree
                    
                wkt = gdal.Footprint(
                    None, dataset_url,
                    format='WKT', dstSRS="EPSG:4326",
                    bands=[1], ovr=overview,
                    simplify=factor, maxPoints=4, minRingArea=factor**2/2
                )
                # Return  Multpolygon
                geom = ogr.CreateGeometryFromWkt( wkt )
                geom_ = geom.GetGeometryRef(0)
                json_geom = geom_.ExportToJson()

                return json.loads( json_geom )
                
            def getIdItems(feature:dict)->tuple:
                keys = ('datetime', 'created')
                properties = { k: feature['properties'][ k ] for k in keys }
                orbit = feature['id'].split('_')[ self.collection['orbit_id'] ]
                if 'orbit_len' in self.collection:
                    orbit = orbit[: self.collection['orbit_len'] ]
                properties[ self._feat_key_orbit_crs ] = f"{orbit}_{feature[ self._feat_key_crs ]}"
                
                assets_bands = {}
                for asset, values in feature['assets'].items():
                    if not 'profile=cloud-optimized' in values['type']:
                        continue

                    r = getSpatiaResolution( values['href'] )
                    if not['is_ok']:
                        return ( None, r['message'] )

                    assets_bands[ asset ] = {
                        'href': values['href'],
                        self._feat_key_res_xy: r[ self._feat_key_res_xy ]
                    }

                return feature['id'], ( { 'geometry': feature['geometry'] } | {'properties': properties } | {'bands': assets_bands} )

            if not response.status_code == 200:
                response.close()
                return {
                    'is_ok': False,
                    'message': response.text
                }

            result = response.json()
            response.close()

            if result['context']['matched'] == 0:
                return {
                    'is_ok': True,
                    'matched': result['context']['matched'],
                    'returned': result['context']['returned']
                }
            
            url_next = result['links'][0]['href'] if (len( result['links'] ) > 0 and result['links'][0]['rel'] == 'next') else None
            features = {}
            count = 0
            total = len( result['features'] )
            returned_check = 0
            for feat in result['features']:
                count += 1

                msg = tr("Request ({}) processing {} of {}").format( self._request_count, count, total )
                self.notifier.footprintStatus( msg, total, count )

                url = f"{feat['assets'][ footprint_band ]['href']}"
                r = openUrl( url )
                if not r['is_ok']:
                    return r

                dataset_url = r['dataset']
                feat[ self._feat_key_crs ] = getCRS( dataset_url )

                geom = feat['geometry']
                if not self.collection['exists_geom']:
                    geom = getFootprint( dataset_url )
                    feat['geometry'] = geom

                dataset_url = None

                if not intersects(bbox, geom ):
                    continue

                returned_check += 1

                id, values = getIdItems( feat )
                if id is None:
                    return {
                        'is_ok': False,
                        'message': r['message']
                    }

                features[ id ] = values

                if isCanceled():
                    return {
                        'is_ok': False,
                        'message': tr('Process cancelled by user')
                    }

            return {
                'is_ok': True,
                'url_next': url_next,
                'matched': result['context']['matched'],
                'returned': returned_check,
                'features': features
            }

        def searchStacItems()->dict:
            p = {
                'collections': [ self.collection['id'] ],
                'limit': self.LIMIT,
                'bbox': ','.join( str(f) for f in bbox ),
                'datetime': f"{dates[0]}T00:00:00Z/{dates[1]}T00:00:00Z"
            }
            r = self._getResponse( {'url': self.SEARCH_URL, 'timeout': 10, 'params': p} )
            if not r['is_ok']:
                return r

            return processResponse( r['response'] )

        def fetchNextPage(url:str)->dict:
            r = self._getResponse( {'url':url, 'timeout': 10} )
            if not r['is_ok']:
                return r

            r = processResponse( r['response'] )
            if not r['is_ok'] or r['returned'] == 0:
                return r
            
            self._features |= r['features']

            del r['features']
            return r
        
        def messageTotalFeatures(matched:int)->None:
            filtered = len(self._features)
            msg = tr("STAC - Totals: {} received, {} - filtered").format( matched, filtered )
            self.notifier.message( { 'text': msg, 'level': Qgis.Info if filtered else Qgis.Warning } )

        self._request_count = 1

        self._features.clear()
        r = searchStacItems()
        if not r['is_ok']:
            self.notifier.message( { 'text': r['message'], 'level': Qgis.Critical }, type='message_bar' )
            return False

        matched = r['matched']
        if not matched:
            msg = tr("No scenes found in '{}' collection").format( self.collection['id'] )
            self.notifier.message( { 'text': msg, 'level': Qgis.Info }, type='message_bar' )
            return True

        self._features = r['features']

        if r['url_next'] is None:
            messageTotalFeatures( matched )
            return True

        total_returned = r['returned']
       
        while True:
            self._request_count += 1
            r = fetchNextPage( r['url_next'] )
            if not r['is_ok']:
                self.notifier.message( { 'text': r['message'], 'level': Qgis.Critical }, type='message_bar' )
                return False

            total_returned += r['returned']
            if not total_returned and r['url_next'] is None:
                if not total_returned:
                    self.notifier.message( { 'text': tr('No scenes found'), 'level': Qgis.Info }, type='message_bar' )
                return True
            
            if r['url_next'] is None:
                messageTotalFeatures( matched )
                return True

            msg = tr("Footprint filtered: {} of {}").format( total_returned, matched )
            self.notifier.message( { 'text': msg, 'level': Qgis.Info }, type='message_bar' )

    def getScenesByDateOrbitsCRS(self, spatial_resolution:str)->dict:
        scene_list = {}
        for asset, data in self._features.items():
            p = data['properties']
            scene_key = f"{p['datetime'].split('T')[0]}_{p[ self._feat_key_orbit_crs ]}"
            urls = { asset: { band: value['href'] for band, value in data['bands'].items() if value[ self._feat_key_res_xy ] == spatial_resolution } }
            if not scene_key in scene_list:
                scene_list[ scene_key ] = [ urls ]
                continue
            scene_list[ scene_key ].append( urls )
        
        return scene_list
