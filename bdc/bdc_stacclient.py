# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BDC Catalog
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

import json
from typing import Callable

from osgeo import gdal, ogr

from qgis.core import Qgis

from qgis.PyQt.QtCore import pyqtSignal

from .translate import tr

from .stacclient import StacClient
from .vsicurl_open import openUrl

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


class BDCStacClient(StacClient):
    def __init__(self):
        super().__init__()

        self.TAG_ATT = 'BDC'
        self.STAC_URL = 'https://data.inpe.br/bdc/stac/v1'
        self._verify_ssl = False

    def _setCollectionsCOGBandsMeta(self)->dict:
        args = {
            'url': f"{self.STAC_URL}/collections/{self.collection['id']}"
        }
        r = self._getResponse( args )
        if not r['is_ok']:
            return r

        result = r['response'].json()
        assets = [ asset for asset, value in result['item_assets'].items() if 'profile=cloud-optimized' in value['type'] ]
        bands = {
            f"{item['name']},{item['common_name']}": {
                self._feat_key_spatial_res: item['resolution_x']
            } for item in result['properties']['eo:bands']
        }
        meta = {}
        for asset in assets:
            for key, value in bands.items():
                if asset in key:
                   sr = f"{int( value[ self._feat_key_spatial_res ] )}"
                   sr = f"{sr}x{sr}"
                   meta[ asset ] = { self._feat_key_spatial_res: sr }
                   break

        self._collections_cog_bands_meta[ self.collection['id'] ]  = meta
        
        return { 'is_ok': True }

    def search(
            self,
            bbox:list,
            dates:list,
            footprint_band:str,
            requestProcessData:pyqtSignal,
            isCanceled:Callable[[str], None]
        )->dict:
        def processResponse(response)->dict:
            def getCRS(ds)->dict:
                sr = ds.GetSpatialRef()
                return sr.GetAuthorityCode(None)

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
                
            getNameFromFeature = lambda feature: feature['id']
            getCRSFromFeature = lambda feature: str( feature[ self._feat_key_crs ] )

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

                text = tr("Request ({}) processing {} of {}").format( self._request_count, count, total )
                requestProcessData.emit({
                    'type': 'message_status',
                    'data': text
                })
                requestProcessData.emit({
                    'type': 'progress_footprint',
                    'data': { 'count': count, 'total': total }
                })

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

                id, values = self._getIdItems( feat, getNameFromFeature, getCRSFromFeature )
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
            r = self._getResponse( {'url': f"{self.STAC_URL}/search", 'timeout': 10, 'params': p} )
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
        
        def messageTotalFeatures(total:int)->None:
            filtered = len(self._features)
            msg = tr("STAC - Totals: {} received, {} - filtered").format( total, filtered )
            requestProcessData.emit( {
                'type': 'message_log',
                'data': { 'text': msg, 'level': Qgis.Info }
            })

        r = self._setCollectionsCOGBandsMeta()
        if not r['is_ok']:
            requestProcessData.emit( {
                'type': 'message_bar',
                'data':{ 'text': r['message'], 'level': Qgis.Critical }
            })
            return False

        self._request_count = 1

        self._features.clear()
        r = searchStacItems()
        if not r['is_ok']:
            requestProcessData.emit( {
                'type': 'message_bar',
                'data':{ 'text': r['message'], 'level': Qgis.Critical }
            })
            return False

        #matched = r['matched']
        returned = r['returned']
        if not returned:
            msg = tr("No scenes found in '{}' collection").format( self.collection['id'] )
            requestProcessData.emit( {
                'type': 'message_bar',
                'data':{ 'text': msg, 'level': Qgis.Info }
            })
            return True

        self._features = r['features']

        if r['url_next'] is None:
            messageTotalFeatures( returned )
            return True

        total_returned = r['returned']
       
        while True:
            self._request_count += 1
            r = fetchNextPage( r['url_next'] )
            if not r['is_ok']:
                requestProcessData.emit( {
                    'type': 'message_bar',
                    'data':{ 'text': r['message'], 'level': Qgis.Critical }
                })
                return False

            total_returned += r['returned']
            if not total_returned and r['url_next'] is None:
                if not total_returned:
                    requestProcessData.emit( {
                        'type': 'message_bar',
                        'data':{ 'text': tr('No scenes found'), 'level': Qgis.Info }
                    })
                return True
            
            if r['url_next'] is None:
                messageTotalFeatures( returned )
                return True

            msg = tr("Footprint filtered: {} of {}").format( total_returned, returned )
            requestProcessData.emit( {
                'type': 'message_bar',
                'data': { 'text': msg, 'level': Qgis.Info }
            })
