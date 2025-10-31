# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Manager task processing
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

import json
import os
from typing import List

from osgeo import gdal
gdal.UseExceptions()

from qgis.PyQt.QtCore import (
    QObject,
    QMetaType,
    pyqtSlot, pyqtSignal
)

from qgis.core import (
    QgsApplication, QgsProject,
    QgsRasterLayer, QgsVectorFileWriter,
    QgsFeature, QgsFields, QgsField,
    QgsCoordinateReferenceSystem,
    QgsJsonUtils,
    QgsTask, Qgis
)
from qgis.gui import QgisInterface

from .taskmanager import TaskProcessor
from .stacclient import StacClient

from .translate import tr

# from .debugtask import DebugTask # DEBUG

class StacProcessor(QObject):
    finished = pyqtSignal()
    addMosaicScenes = pyqtSignal()
    requestProcessData = pyqtSignal(dict)
    def __init__(self,
            iface:QgisInterface,
            task_processor:TaskProcessor,
            stac_client:StacClient
        ):
        super().__init__()
        self.task_processor = task_processor
        self.requestProcessData.connect( self.task_processor.process )
        self._client = stac_client

        self._footprint_style = os.path.join( os.path.dirname(os.path.abspath(__file__)), 'footprint.qml')
        
        self._vrt_options = {
            'separate': True,
            'bandList': [1],
            'callback': self._callbackVRTBuild,
            'callback_data': None # QgsTask object will be set during VRT build
        }
        self.spatial_resolution = None
        self.dates = None
        self.dir_mosaic = None
        self.bbox = None

        self._last_search_params = { 'collection': None, 'spatial_resolution': None, 'dates': None, 'bbox': None  }
        self._is_ok_last_processed = None
        
        self._str_search = None

        self._scenes_total = None
        self._mosaic_total = None

        self.project = QgsProject.instance()
        self.map_canvas = iface.mapCanvas()
        self.taskManager = QgsApplication.taskManager()
        self.task_id = None
        self.is_task_canceled = False

        self._tag_att_values_source = {
            'vrt': 'VRT',
            'url': 'URL'
        }

        self.addMosaicScenes.connect( self._onAddMosaicScenes )

    def _search_run(self, task:QgsTask)->bool:
        return self._client.search( self.bbox, self.dates, self.requestProcessData, task.isCanceled )

    def setCollection(self, collection:dict):
        self._client.collection = collection
        if 'srcNodata' in self._vrt_options:
            del self._vrt_options['srcNodata']
        if 'nodata' in self._client.collection:
            self._vrt_options['srcNodata'] = self._client.collection['nodata']

    def _callbackVRTBuild(self, complete:float, message:str, user_data:QgsTask)->None:
        if user_data.isCanceled():
            return 0

        user_data.setProgress( complete*100 )
        return 1

    def _search(self)->None:
        def createFootprintLayerFile(filepath:str, driver:str, features:dict)->None:
            # Create layer
            field_types = [
                {
                    'name': 'id',
                    'type': QMetaType.QString,
                    'length': 100,
                },
                {
                    'name': 'properties',
                    'type': QMetaType.QString,
                    'length': 500,
                },
                {
                    'name': 'bands',
                    'type': QMetaType.QString,
                    'length': 0, # Unlimit
                }
            ]
            fields = QgsFields()
            for field in field_types:
                fields.append(
                    QgsField( name=field['name'], type=field['type'], len=field['length'] )
                )
            asset = list( features.keys() )[0]
            geom = QgsJsonUtils.geometryFromGeoJson(json.dumps( features[ asset ]['geometry'] ) )
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = driver
            writer = QgsVectorFileWriter.create(
                filepath,
                fields,
                geom.wkbType(),
                QgsCoordinateReferenceSystem('EPSG:4326'),
                self.project.transformContext(),
                options
            )
            # Populate
            for asset, data in features.items():
                feature = QgsFeature()

                geom = QgsJsonUtils.geometryFromGeoJson(json.dumps(data['geometry']))
                feature.setGeometry( geom )

                atts = [asset] + [ json.dumps( data[k] ) for k in data if not k == 'geometry' ]
                feature.setAttributes( atts )

                writer.addFeature( feature )
            writer = None

        def on_finished(exception, data:dict)->None:
            self._is_ok_last_processed = False

            if exception:
                self.requestProcessData.emit({
                    'type': 'message_bar',
                    'data': { 'text': str(exception), 'level': Qgis.Critical }
                })
                self.finished.emit()
                return

            if self.is_task_canceled:
                self.finished.emit()
                return

            if not data['is_ok']:
                self.finished.emit()
                return

            self._is_ok_last_processed = True

            features = self._client.getFeatures()
            self._scenes_total = len( features )
            if not self._scenes_total:
                self.finished.emit()
                return

            data['source']['style'] = self._footprint_style
            data['source']['bbox'] = self.bbox
            self.task_processor.addVectorLayer( data['source'] )
            
            self.task_processor.createMosaicGroup(f"mosaic.{self._str_search}")
            dir_mosaic_scenes = os.path.join( self.dir_mosaic, self._str_search )
            os.makedirs( dir_mosaic_scenes, exist_ok=True )

            self.addMosaicScenes.emit()

        def run(task:QgsTask)->dict:
            # self.debug.active() # DEBUG

            if not self._search_run( task ):
                if task.isCanceled():
                    self.is_task_canceled = True
                return { 'is_ok': False }

            features = self._client.getFeatures()
            if not len( features):
                return { 'is_ok': True }

            filepath = os.path.join( self.dir_mosaic, f"footprint.{self._str_search}.geojson" )
            createFootprintLayerFile( filepath, 'GeoJSON', features )
            source = {'filepath': filepath, 'add_group': False, 'color': 'Gray', 'opacity': 0.1 }
            
            return { 'is_ok': True, 'source': source }

        self._last_search_params = {
            'collection': self._client.collection['id'],
            'spatial_resolution': self.spatial_resolution,
            'dates': self.dates,
            'bbox': self.bbox            
        }

        self._total_scenes = None
        self._total_mosaic = None

        name = f"Create Footprint - {self._str_search}"
        task = QgsTask.fromFunction( name, run, on_finished=on_finished )
        self.task_processor.setTask( task, self._client.collection['id'] )
        self.taskManager.addTask( task )
        self.task_id = self.taskManager.taskId(task)

        # self.debug = DebugTask() # DEBUG

    def _onAddMosaicScenes(self)->None:
        def on_finished(exception, data:dict)->None:
            if exception:
                self.requestProcessData.emit({
                    'type': 'message_bar',
                    'data': { 'text': str(exception), 'level': Qgis.Critical }
                })
                self.finished.emit()
                return

            if not data['is_ok']:
                self.finished.emit()
                return

            msg = tr('Success - {} scenes - {} mosaics').format( self._scenes_total, self._mosaic_total )
            self.requestProcessData.emit({
                'type': 'message_bar',
                'data': { 'text': msg, 'level': Qgis.Success }
            })

            self.finished.emit()

        def run(task:QgsTask)->None:
            def createRasterMosaicVRT(scene_list:List[dict], date_orbit_crs:str)->dict:
                def writeVRTSource(filepath, source_type):
                    data = {
                        'collection_id': self._client.collection['id'],
                        'source_type': source_type
                    }
                    with open( f"{filepath}.{self._client.TAG_ATT}.json", "w", encoding="utf-8") as f:
                        json.dump( data, f, indent=4 )

                def addBandNames(dataset:QgsRasterLayer, band_names:List[str])->None:
                    for i, name in enumerate( band_names ):
                        band = dataset.GetRasterBand( i + 1 )
                        band.SetDescription( name )

                self._vrt_options['callback_data'] = task
                options = gdal.BuildVRTOptions( **self._vrt_options )

                name_mosaic = f"{self._client.collection['id']}.{date_orbit_crs}_{self.spatial_resolution}"
                dir_mosaic_scenes = os.path.join( self.dir_mosaic, self._str_search )
                dir_scenes = os.path.join( dir_mosaic_scenes, name_mosaic )
                os.makedirs(dir_scenes, exist_ok=True)
                vrt_paths = []
                for scene in scene_list:
                    for scene_id, band_urls in scene.items():
                        vrt_path = os.path.join( dir_scenes, f"{scene_id}_{self.spatial_resolution}.vrt")

                        vsicurl_band_urls = [f"/vsicurl/{url}" for url in band_urls.values()]
                        band_names = list( band_urls.keys() )
                        
                        # Reorder urls and band names to have RGB first
                        rgb_index = [ band_names.index( b ) for b in self._client.collection['spatial_res_composite'][ self.spatial_resolution ] ]
                        url_rgb = [ vsicurl_band_urls[i] for i in rgb_index ]
                        for i in sorted( rgb_index, reverse=True ):
                            del vsicurl_band_urls[i]
                            del band_names[i]
                        vsicurl_band_urls = url_rgb + vsicurl_band_urls
                        band_names = self._client.collection['spatial_res_composite'][ self.spatial_resolution ] + band_names

                        ds_ = gdal.BuildVRT (vrt_path, vsicurl_band_urls, options=options )
                        if ds_ is None:
                            return {
                                'is_ok': False,
                                'message': tr('Error building VRT for scene {}').format( scene_id ),
                                'level': Qgis.Critical

                            }
                        if task.isCanceled():
                            ds_ = None
                            return {
                                'is_ok': False,
                                'message': tr('Process cancelled by user'),
                                'level': Qgis.Critical
                            }

                        addBandNames( ds_, band_names )
                        ds_ = None
                        writeVRTSource( vrt_path, self._tag_att_values_source['url'])

                        vrt_paths.append( vrt_path )

                filepath = os.path.join( dir_mosaic_scenes, f"{name_mosaic}.vrt")
                ds_ = gdal.BuildVRT(filepath, vrt_paths)
                if ds_ is None:
                    return {
                        'is_ok': False,
                        'message': tr('Error building mosaic VRT for date/orbit/crs {}').format( date_orbit_crs ),
                        'level': Qgis.Critical
                    }
                if task.isCanceled():
                    ds_ = None
                    return {
                        'is_ok': False,
                        'message': tr('Process cancelled by user'),
                        'level': Qgis.Critical
                    }

                addBandNames( ds_, band_names )
                ds_ = None
                writeVRTSource( filepath, self._tag_att_values_source['vrt'])

                return {
                    'is_ok': True,
                    'filepath': filepath,
                    'layers': [ vrt.split( os.path.sep)[-1] for vrt in vrt_paths ]
                }

            # self.debug.active() # DEBUG

            scene_list = self._client.getScenesByDateOrbitsCRS( self.spatial_resolution )
            mosaic_count = 0
            self._mosaic_total = len( scene_list )
            msg = tr('Mosaic: {} total (Spatial resolution: {})').format(self._mosaic_total, self.spatial_resolution)
            self.requestProcessData.emit({
                'type': 'message_log',
                'data': { 'text': msg, 'level': Qgis.Info }
            })
            for date_orbit_crs, data in scene_list.items():
                mosaic_count += 1
                args = (
                    self._client.collection['id'],
                    mosaic_count, self._mosaic_total,
                    f"{self._client.collection['id']}.{date_orbit_crs}_{self.spatial_resolution}",
                    len(data)
                )
                text = tr("{} - Mosaic {} of {}: {} ({})").format( *args )
                self.requestProcessData.emit({
                    'type': 'message_status',
                    'data': text
                })

                r = createRasterMosaicVRT( data, date_orbit_crs )
                if not r['is_ok']:
                    if task.isCanceled():
                        self.is_task_canceled = True
                    self.requestProcessData.emit({
                        'type': 'message_bar',
                        'data': { 'text': r['message'], 'level': r['level']  }
                    })
                    return { 'is_ok': False }
                
                args = {
                    'filepath': r['filepath'],
                    'layers': r['layers']
                }
                self.requestProcessData.emit({
                    'type': 'add_layer_mosaic_group',
                    'data': args
                })

            return { 'is_ok': True }
                
        name = f"Create Mosaics - {self._str_search}"
        task = QgsTask.fromFunction( name, run, on_finished=on_finished )
        self.task_processor.setTask( task, self._client.collection['id'] )
        self.taskManager.addTask( task )
        self.task_id = self.taskManager.taskId( task )
        
    def process(self)->None:
        def checkDataProcessed()->dict:
            p = {
                'collection': self._client.collection['id'],
                'dates': self.dates,
                'bbox': self.bbox,
            }
            total = len( p )
            count = 0
            for k in p:
                if not p[ k ] == self._last_search_params[ k ]:
                    break
                count += 1
            
            return count == total

        bbox_str = '_'.join( [ f"{c:.4f}" for c in self.bbox ] )
        self._str_search = f"{self._client.collection['id']}_{'_'.join( self.dates )}_{bbox_str}"
        self.is_task_canceled = False

        exists_processed = checkDataProcessed()
        exists_spatial_resolution = ( self.spatial_resolution == self._last_search_params['spatial_resolution'] )
        if self._is_ok_last_processed and exists_processed and exists_spatial_resolution:
            msg = tr("Search complete. Showing last result - {}.").format( self._str_search )
            self.requestProcessData.emit({
                'type': 'message_bar',
                'data': { 'text': msg, 'level': Qgis.Warning }
            })

            self.finished.emit()
            return

        fetchData = False if ( self._is_ok_last_processed and exists_processed ) else True
        if not fetchData:
            self._onAddMosaicScenes()
            return

        self._search() # Call _onAddMosaicScenes after search finished


    @pyqtSlot()
    def cancelCurrentTask(self)->None:
        task = self.taskManager.task( self.task_id )
        if not task is None:
            task.cancel()

    def isCancelled(self):
        return self.is_task_canceled
