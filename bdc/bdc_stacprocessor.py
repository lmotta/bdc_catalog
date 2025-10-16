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


import os

from .stacprocessor import (
    StacProcessor,
    QgisInterface, QgsTask,
    TaskNotifier,
    TaskProcessor,
    StacClient,
    tr
)


class BDCStacProcessor(StacProcessor):
    def __init__(self,
            iface:QgisInterface,
            task_notifier:TaskNotifier,
            task_processor:TaskProcessor,
            stac_client:StacClient
        ):
        super().__init__( iface, task_notifier, task_processor, stac_client )

    def _search_run(self, task:QgsTask)->dict:
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
        self._createFootprintLayerFile( filepath, 'GeoJSON', features )
        source = {'filepath': filepath, 'add_group': False, 'color': 'Gray', 'opacity': 0.1 }
        
        return { 'is_ok': True, 'source': source }

        return self.is_task_canceled