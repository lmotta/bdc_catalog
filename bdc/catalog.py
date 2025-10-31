# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Catalog
 
 Catalog manager for processor and widget
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

from typing import Any
import os
from qgis.PyQt.QtCore import QObject, pyqtSlot

from .catalogwidget import CatalogWidget
from .stacprocessor import StacProcessor

class Catalog(QObject):
    def __init__(self,
            widget:CatalogWidget,
            processor:StacProcessor            
        ):
        super().__init__()

        self.iface = widget.iface
        self.config_collection = widget.config_collection

        self.processor = processor
        self.widget = widget

        self.widget.requestProcessData.connect( self.process )
        self.widget.cancelProcess.connect( self.processor.cancelCurrentTask )

        self.processor.finished.connect( self.widget.finished )
        self.processor.task_processor.messageStatus.connect( self.widget.messageStatus )

    def __del__(self):
        self.iface.mainWindow().statusBar().removeWidget( self.widget )

        self.widget.requestProcessData.disconnect( self.process )
        self.processor.finished.disconnect( self.widget.finished )
        self.processor.task_processor.messageStatus.disconnect( self.widget.messageStatus )

        self.widget.deleteLater()
        self.widget = None

    @pyqtSlot(dict)
    def process(self, values:dict)->None:
        self.processor.setCollection( self.config_collection[ values['collection'] ])
        self.processor.spatial_resolution = values['spatial_resolution']
        self.processor.dates = [ values['ini_date'], values['end_date'] ]
        self.processor.dir_mosaic = os.path.normpath( values['vrt_dir'] )
        self.processor.bbox = values['bbox']

        self.processor.process()

    def addWidget(self)->None:
        self.iface.mainWindow().statusBar().addWidget( self.widget, 1 )
        self.widget.hide()

    def enabled(self, enabled:bool)->None:
        self.widget.show() if enabled else self.widget.hide()