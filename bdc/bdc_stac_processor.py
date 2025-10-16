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
from qgis.PyQt.QtGui import QColor

from qgis.core import (
    QgsApplication, QgsProject,
    QgsRasterLayer, QgsVectorFileWriter,
    QgsFeature, QgsFields, QgsField,
    QgsCoordinateReferenceSystem,
    QgsJsonUtils,
    QgsTask, Qgis
)
from qgis.gui import QgisInterface

from .bdc_stac import BDCStacClient
from .bdc_taskmanager import TaskNotifier, TaskProcessor, TaskDebugger
from .vsicurl_open import setConfigOptionUrl, setConfigClearUrl
from .translate import tr


class BDCStacProcessor(QObject):
    finished = pyqtSignal()
    def __init__(self, iface:QgisInterface):
        super().__init__()
        self._notifier = TaskNotifier()
        self._processor = TaskProcessor( iface, 'BDC Catalog' )
        self._notifier.sendData.connect( self._processor.process )
        self._footprint_style = os.path.join( os.path.dirname(os.path.abspath(__file__)), 'footprint.qml')

        self._client = BDCStacClient( self._notifier )
        self._vrt_options = None
        
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

    def setCollection(self, collection:dict)->None:
        self._client.collection = collection
        self._vrt_options = { 'separate': True, 'bandList': [1]  }
        if 'nodata' in self._client.collection:
            self._vrt_options['srcNodata'] = self._client.collection['nodata']
        self._vrt_options = gdal.BuildVRTOptions( **self._vrt_options )

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
            setConfigClearUrl()

            self._is_ok_last_processed = False

            if exception:
                self._notifier.message( { 'text': str(exception), 'level': Qgis.Critical }, type='message_bar' )
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
            self._processor.addVectorLayer( data['source'] )
            
            self._processor.createMosaicGroup(f"mosaic.{self._str_search}")
            dir_mosaic_scenes = os.path.join( self.dir_mosaic, self._str_search )
            os.makedirs( dir_mosaic_scenes, exist_ok=True )
            self._addMosaicScenes()

        def run(task:QgsTask)->dict:
            footprint_band = self._client.collection['spatial_res_composite'][ self.spatial_resolution ][0]
            is_ok =  self._client.search( self.bbox, self.dates, footprint_band, task.isCanceled )
            if not is_ok:
                if task.isCanceled():
                    self.is_task_canceled = True
                return { 'is_ok': is_ok }

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

        setConfigOptionUrl()

        self._total_scenes = None
        self._total_mosaic = None

        name = f"Create Footprint - {self._str_search}"
        task = QgsTask.fromFunction( name, run, on_finished=on_finished )
        self._processor.setTask( task, self._client.collection['id'] )
        self.taskManager.addTask( task )
        self.task_id = self.taskManager.taskId(task)

        # DEBUGGER
        # task = TaskDebugger()
        # self._processor.setTask( task, self._client.collection['id'] )
        # on_finished(None,  run(task) )
        #

    def _addMosaicScenes(self)->None:
        def on_finished(exception, data=None)->None:
            setConfigClearUrl()
            if exception:
                self._notifier.message( { 'text': str(exception), 'level': Qgis.Critical }, type='message_bar' )
                self.finished.emit()
                return

            if self.is_task_canceled:
                self.finished.emit()
                return

            msg = tr('Success - {} scenes - {} mosaics').format( self._scenes_total, self._mosaic_total )
            self._notifier.message( { 'text': msg, 'level': Qgis.Success }, type='message_bar' )
            self.finished.emit()

        def run(task:QgsTask)->None:
            def createRasterMosaicVRT(scene_list:List[dict], date_orbit_crs:str)->dict:
                def addBandNames(dataset:QgsRasterLayer, band_names:List[str])->None:
                    for i, name in enumerate( band_names ):
                        band = dataset.GetRasterBand( i + 1 )
                        band.SetDescription( name )

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

                        ds_ = gdal.BuildVRT (vrt_path, vsicurl_band_urls, options=self._vrt_options )
                        addBandNames( ds_, band_names )
                        ds_ = None

                        vrt_paths.append( vrt_path )

                        if task.isCanceled():
                            return { 'is_ok': False, 'message': tr('Process cancelled by user') }

                filepath = os.path.join( dir_mosaic_scenes, f"{name_mosaic}.vrt")
                ds_ = gdal.BuildVRT(filepath, vrt_paths)
                addBandNames( ds_, band_names )
                ds_ = None

                return {
                    'is_ok': True,
                    'filepath': filepath,
                    'layers': [ vrt.split( os.path.sep)[-1] for vrt in vrt_paths ]
                    # 'band_names': band_names
                }


            scene_list = self._client.getScenesByDateOrbitsCRS( self.spatial_resolution )
            mosaic_count = 0
            self._mosaic_total = len( scene_list )
            msg = tr('Mosaic: {} total (Spatial resolution: {})').format(self._mosaic_total, self.spatial_resolution)
            self._notifier.message( { 'text': msg } )
            for date_orbit_crs, data in scene_list.items():
                r = createRasterMosaicVRT( data, date_orbit_crs )
                if not r['is_ok']:
                    args = { 'text': r['message'], 'level': Qgis.Warning }
                    if task.isCanceled():
                        self.is_task_canceled = True
                        args['level'] = Qgis.Critical
                    self._notifier.message( args, type='message_bar' )
                    return

                mosaic_count += 1
                args = {
                    'filepath': r['filepath'],
                    'layers': r['layers'],
                    'total_raster': len(data),
                    'mosaic_count': mosaic_count,
                    'mosaic_total': self._mosaic_total
                    # 'rgb_index': [ r['band_names'].index( b )+1 for b in self._client.collection['spatial_res_composite'][ self.spatial_resolution ] ]
                }
                self._notifier.addLayerMosaicGroup(**args)


        setConfigOptionUrl()
        name = f"Create Mosaics - {self._str_search}"
        task = QgsTask.fromFunction( name, run, on_finished=on_finished )
        self._processor.setTask( task, self._client.collection['id'] )
        self.taskManager.addTask( task )
        self.task_id = self.taskManager.taskId(task)
        
        # DEBUGGER
        # task = TaskDebugger()
        # self._processor.setTask( task, self._client.collection['id'] )
        # on_finished(None, run(task))
        #

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
            self._notifier.message( { 'text': msg, 'level': Qgis.Warning }, type='message_bar' )
            self.finished.emit()
            return

        fetchData = False if ( self._is_ok_last_processed and exists_processed ) else True
        if not fetchData:
            self._addMosaicScenes()
            return

        self._search() # Call _addMosaicScenes

    @pyqtSlot()
    def cancelCurrentTask(self)->None:
        task = self.taskManager.task( self.task_id )
        if not task is None:
            task.cancel()

    def isCancelled(self):
        return self.is_task_canceled