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
 This script initializes the plugin, making it known to QGIS.
"""

__author__ = "Luiz Motta"
__date__ = "2025-09-02"
__copyright__ = "(C) 2025, Luiz Motta"
__revision__ = "$Format:%H$"


import os

from qgis.PyQt.QtCore import (
    QObject,
    QDir,
    pyqtSlot
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import  QAction

from qgis.gui import QgisInterface

from .bdc.taskmanager import TaskProcessor
from .bdc.bdc_stacclient import BDCStacClient
from .bdc.bdc_stacprocessor import BDCStacProcessor
from .bdc.config import configCollection

from .bdc.catalogwidget import CatalogWidget
from .bdc.catalog import Catalog

from .bdc.translate import setTranslation


def classFactory(iface:QgisInterface):
    return BDCCatalogPlugin(iface)


class BDCCatalogPlugin(QObject):
    def __init__(self, iface:QgisInterface):
        super().__init__()
        self.iface = iface

        setTranslation( type(self).__name__, os.path.dirname(__file__) )

        self.plugin_name = 'BDCCatalog'
        self.action_name = 'BDC Catalog'
        self.action = None

        # Catalog Widget
        task_processor = TaskProcessor( self.iface, 'BDC Catalog' )
        client = BDCStacClient()
        self._processor = BDCStacProcessor( iface, task_processor, client )
        self._config_collection = configCollection()

        self.catalog = None # initGui

    def initGui(self)->None:
        path = QDir( os.path.dirname(__file__) )
        icon = QIcon( path.filePath('resources/bdccatalog.svg'))
        self.action = QAction( icon, self.action_name, self.iface.mainWindow() )
        self.action.setToolTip( self.action_name )
        self.action.setCheckable( True )
        self.action.triggered.connect(self.on_Clicked)

        self.menu_name = f"&{self.action_name}"
        self.iface.addPluginToWebMenu( self.menu_name, self.action )
        self.iface.webToolBar().addAction(self.action)

        # Catalog Widget
        widget = CatalogWidget( self.iface, self._config_collection, 'bdccatalogwidget' )
        self.catalog = Catalog( widget, self._processor )
        self.catalog.addWidget()

    def unload(self)->None:
        self.iface.removePluginWebMenu( self.menu_name, self.action )
        self.iface.webToolBar().removeAction( self.action )
        self.iface.unregisterMainWindowAction( self.action )
        # Disconnect
        try:
            self.action.triggered.disconnect( self.on_Clicked )
        except Exception:
            pass
        self.action.deleteLater()

        del self.catalog

    @pyqtSlot(bool)
    def on_Clicked(self, enabled:bool)->None:
        self.catalog.enabled( enabled )

