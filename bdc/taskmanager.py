# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Manager Task for Catalog
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
from typing import Union, List

from qgis.PyQt.QtCore import (
    QObject,
    pyqtSignal, pyqtSlot
)

from qgis.core import (
    QgsProject,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsVectorLayer, QgsRasterLayer,
    QgsMessageLog,
    QgsTask
)
from qgis.gui import QgisInterface

from .translate import tr


class TaskProcessor(QObject):
    messageStatus = pyqtSignal(str)
    def __init__(self, iface:QgisInterface, title:str):
        super().__init__()
        self.project = QgsProject.instance()
        self._task = None
        self._mosaic_group = None
        self.propertyName = title
        self.collection = None
        self.message_log = QgsMessageLog()
        self.message_bar = iface.messageBar()

    def _addLayerToMosaicGroup(self, layer:Union[QgsVectorLayer, QgsRasterLayer])->None:
        self.project.addMapLayer( layer, addToLegend=False )
        node = QgsLayerTreeLayer( layer )
        node.setItemVisibilityChecked(False)
        node.setExpanded(False)
        self._mosaic_group.addChildNode( node )

    def setTask(self, task:QgsTask, collection:str)->None:
        self._task = task
        self.collection = collection
        msg = tr("{} - Processing...").format( self.collection )
        self.messageStatus.emit( msg )

    @pyqtSlot(dict)
    def process(self, payload:dict)->None:
        methods = {
            'message_log': self.messageLog,
            'message_bar': self.messageBar,
            'message_status': self.messageStatusText,
            'create_mosaic_group': self.createMosaicGroup,
            'progress_footprint': self.progressFootprint,
            'add_layer_vector': self.addVectorLayer,
            'add_layer_mosaic_group': self.addLayerMosaicGroup
        }
        methods[ payload['type'] ]( payload['data'] )

    def messageLog(self, message:dict)->None:
        self.message_log.logMessage( message=message['text'], tag=self.propertyName, level=message['level'] )

    def messageBar(self, message:dict)->None:
        self.message_bar.popWidget()
        self.message_bar.pushMessage( title=self.propertyName, text=message['text'], level=message['level'], duration=5 )

    def messageStatusText(self, text:str)->None:
        self.messageStatus.emit( text )

    def createMosaicGroup(self, name:str)->None:
        root = self.project.layerTreeRoot()
        self._mosaic_group = QgsLayerTreeGroup( name )
        root.insertChildNode(0, self._mosaic_group)

    def progressFootprint(self, status:dict)->None:
        self._task.setProgress( int( (status['count'] / status['total']) * 100 ) )

    def addVectorLayer(self, source:dict)->None:
        def addStyle(layer):
            filepath = source['style']
            ok, err = layer.loadNamedStyle( filepath )
            if not ok:
                return
            
            layer.triggerRepaint()

        filepath = source['filepath']
        name = os.path.splitext(os.path.basename(filepath))[0]
        layer = QgsVectorLayer( filepath, name, 'ogr' )
        if 'style' in source: 
            addStyle( layer )
        layer.setCustomProperty( self.propertyName, json.dumps({ 'bbox': source['bbox'] }) )        
        if source['add_group']:
            self._addLayerToMosaicGroup( layer )
            return
        
        self.project.addMapLayer( layer,  addToLegend=False )
        root = self.project.layerTreeRoot()
        root.insertLayer(0, layer )

    def addLayerMosaicGroup(self, status:dict)->None:
        name = os.path.splitext(os.path.basename(status['filepath']))[0]
        layer = QgsRasterLayer( status['filepath'], name )
        layer.setCustomProperty( self.propertyName, json.dumps({ 'layers': status['layers'] }) )
        self._addLayerToMosaicGroup( layer )
