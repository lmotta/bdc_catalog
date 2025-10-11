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

from .bdc.bdc_catalog import BDCCatalog
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
        self.bdc_action = None

        self.bdc = BDCCatalog(iface)

    def initGui(self)->None:
        path = QDir( os.path.dirname(__file__) )
        icon = QIcon( path.filePath('resources/bdccatalog.svg'))
        self.bdc_action = QAction( icon, self.action_name, self.iface.mainWindow() )
        self.bdc_action.setToolTip( self.action_name )
        self.bdc_action.setCheckable( True )
        self.bdc_action.triggered.connect(self.on_BdcClicked)

        self.menu_name = f"&{self.action_name}"
        self.iface.addPluginToWebMenu( self.menu_name, self.bdc_action )
        self.iface.webToolBar().addAction(self.bdc_action)

        self.bdc.addWidget()

    def unload(self)->None:
        self.iface.removePluginMenu( self.menu_name, self.bdc_action )
        self.iface.webToolBar().removeAction( self.bdc_action )
        # Disconnect
        try:
            self.bdc_action.triggered.disconnect( self.on_BdcClicked )
        except Exception:
            pass
        self.bdc_action.deleteLater()

        del self.bdc

    @pyqtSlot(bool)
    def on_BdcClicked(self, enabled:bool)->None:
        self.bdc.enabled( enabled )

