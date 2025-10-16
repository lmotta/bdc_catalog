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

from qgis.PyQt.QtCore import QObject, pyqtSlot

from qgis.gui import QgisInterface

from .config import configCollection

from .bdc_stac_processor import BDCStacProcessor
from .bdc_widget import BdcCatalogWidget


class BDCCatalog(QObject):
    def __init__(self, iface:QgisInterface):
        super().__init__()

        self.iface = iface

        self.config_collection = configCollection()
        self.processor = BDCStacProcessor( iface )
        self.widget = BdcCatalogWidget( iface, self.processor.isCancelled, self.config_collection )

        self.widget.goProcess.connect( self.runProcess )
        self.widget.cancelProcess.connect( self.processor.cancelCurrentTask )

        self.processor.finished.connect( self.widget.finished )
        self.processor._processor.messageStatus.connect( self.widget.messageStatus )

    def __del__(self):
        self.iface.mainWindow().statusBar().removeWidget( self.widget )

        self.widget.goProcess.disconnect( self.runProcess )
        self.processor.finished.disconnect( self.widget.finished )
        self.processor._processor.messageStatus.disconnect( self.widget.messageStatus )

        self.widget.deleteLater()
        self.widget = None

    @pyqtSlot(dict)
    def runProcess(self, values:dict)->None:
        self.processor.setCollection( self.config_collection[ values['collection'] ])
        self.processor.spatial_resolution = values['spatial_resolution']
        self.processor.dates = [ values['ini_date'], values['end_date'] ]
        self.processor.dir_mosaic = values['vrt_dir']
        self.processor.bbox = values['bbox']

        self.processor.process()

    def addWidget(self)->None:
        self.iface.mainWindow().statusBar().addWidget( self.widget, 1 )
        self.widget.hide()

    def enabled(self, enabled:bool)->None:
        self.widget.show() if enabled else self.widget.hide()