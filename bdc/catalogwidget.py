# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Catalog Widget
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

from typing import Callable, List

from qgis.PyQt.QtCore import (
    Qt, QObject,
    QSize,
    QDir,
    QDate, QTimer,
    pyqtSignal, pyqtSlot,
    QEvent
    
)
from qgis.PyQt.QtGui import (
    QColor, QIcon
)
from qgis.PyQt.QtWidgets import (
    QWidget, QLabel, QComboBox, QDateEdit, QToolButton,
    QLayout, QHBoxLayout, QStackedLayout,
    QFileDialog,
    QSizePolicy    
)

from qgis.gui import QgisInterface

from qgis.core import (
    Qgis, QgsApplication, QgsProject,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsRectangle,
    QgsSettings
)
from qgis.gui import QgsHighlight

from .translate import tr


class HighlightManager:
    def __init__(self, iface):
        self.canvas = iface.mapCanvas()
        self.highlight = None

        self.blink_count = 0
        self.blink_total = 0
        self.blink_timer = None

    def setGeometry(self, geom:QgsGeometry)->None:
        if self.highlight:
            hl = self.highlight
            hl.hide()
            del hl
        self.highlight = QgsHighlight(self.canvas, geom, None)
        self.highlight.hide()
        color = QColor('Red')
        self.highlight.setColor(color)
        color.setAlpha(30)
        self.highlight.setFillColor(color)

    def blink(self)->None:
        def blink_highlight():
            self.blink_count += 1
            if self.blink_count == self.blink_total:
                self.blink_timer.stop()
                self.highlight.hide()
                return

            self.highlight.hide() if self.highlight.isVisible() else self.highlight.show()

        self.blink_count = 0
        self.blink_total = 5
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(blink_highlight)

        self.is_blinking = True
        self.blink_timer.start(150)

    def show(self)->None:
        if self.highlight and not self.highlight.isVisible():
            self.highlight.show()

    def remove(self)->None:
        if self.highlight and self.highlight.isVisible():
            self.highlight.hide()


class ToolButtonExtent(QToolButton):
    def __init__(self, parent:QObject, iface:QgisInterface):
        super().__init__( parent )
        self.extent_4326 = None
        self.hl_manager = HighlightManager( iface )
        self.canvas = iface.mapCanvas()
        self.project = QgsProject.instance()
        self.crs_4326 = QgsCoordinateReferenceSystem('EPSG:4326')

    def _show(self, extent:QgsRectangle)->None:
        geom = QgsGeometry.fromRect( extent )
        self.hl_manager.setGeometry(geom)
        self.hl_manager.show()

    def getExtent(self)->List[float]:
        extent = self.canvas.extent()
        self._show( extent )

        crs = self.canvas.mapSettings().destinationCrs()
        crs_4326 = QgsCoordinateReferenceSystem('EPSG:4326')
        transform = QgsCoordinateTransform(crs, crs_4326, self.project)
        self.extent_4326 = transform.transform( extent )

        bbox = [
            self.extent_4326.xMinimum(), self.extent_4326.yMinimum(),
            self.extent_4326.xMaximum(), self.extent_4326.yMaximum()
        ]
        txt = ','.join( f"{coord:.4f}" for coord in bbox )
        msg = tr("Extent (WGS 84): {}").format(txt)
        self.setToolTip(msg)

        return bbox

    @pyqtSlot(QEvent)
    def enterEvent(self, event:QEvent)->None:
        if self.extent_4326 is None:
            return

        crs = self.canvas.mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(self.crs_4326, crs, self.project)
        extent = transform.transform( self.extent_4326 )
        self._show( extent )

        super().enterEvent(event)

    @pyqtSlot(QEvent)
    def leaveEvent(self, event:QEvent)->None:
        self.hl_manager.remove()
        super().leaveEvent(event)


class CatalogWidget(QWidget):
    goProcess = pyqtSignal(dict)
    cancelProcess = pyqtSignal()
    def __init__(self,
            iface:QgisInterface,
            isCancelled:Callable[[None], bool],
            config_collection:dict,
            setting_key:str
        ):
        def setDateWidget(dt):
            dt.setDisplayFormat('yyyy-MM-dd')
            dt.setCalendarPopup(True)
            dt.setMaximumWidth(115)

        def setSyleWidget(widget):
            widget.setAttribute(Qt.WA_StyledBackground, True)
            style = """
                QWidget#OBJECTNAME {
                    background-color: rgba(180, 180, 180, 30);
                    border: 1px solid rgba(180, 180, 180, 80);
                    border-radius: 4px;
                }
            """
            style = style.replace('OBJECTNAME', widget.objectName())
            widget.setStyleSheet(style)

        def createButton(
            icon:QIcon,
            tooltip:str,
            slot:Callable[[None], None]
        )->QToolButton:
            btn = QToolButton( self )
            btn.setAutoRaise(True)
            btn.setIcon( icon )
            btn.setToolTip( tooltip )
            btn.setIconSize(QSize(16, 16))
            btn.released.connect( slot )

            return btn

        def createButtonExtent()->ToolButtonExtent:
            btn = ToolButtonExtent( self, iface )
            btn.setAutoRaise(True)
            btn.setIcon( QgsApplication.getThemeIcon('extents.svg') )
            btn.setToolTip( self._fmt_extent.format( tr('No Extent Captured') ) )
            btn.setIconSize(QSize(16, 16))
            btn.released.connect( self.on_CaptureExtent )

            return btn

        def createToggleButton(is_run:bool)->None:
            btn = createButton(
                self._toggle_button_run[ is_run ]['icon'],
                self._toggle_button_run[ is_run ]['tooltip'],
                self.on_ToggleRun
            )
            btn.setAttribute(Qt.WA_StyledBackground, True)
            btn.setObjectName('mspc_toggle')
            setSyleWidget(btn)
            btn.is_run = is_run

            return btn

        def createCollectionSpatialResolutionComboBox()->None:
            cb_collection = QComboBox(self)
            cb_collection.setToolTip( tr('Select a satellite collection'))
            cb_collection.addItems([ k for k in self.config_collection.keys() ])
            cb_collection.setMinimumContentsLength(8)
            cb_collection.setSizeAdjustPolicy(QComboBox.AdjustToContents)

            cb_spatial_resolution = QComboBox(self)
            cb_spatial_resolution.setToolTip(   tr('Select the spatial resolution of the bands') )
            cb_spatial_resolution.addItems( [ k for k in self.config_collection[ cb_collection.currentText() ]['spatial_res_composite'].keys() ] )
            cb_spatial_resolution.setMinimumContentsLength(8)
            cb_spatial_resolution.setSizeAdjustPolicy(QComboBox.AdjustToContents)

            cb_collection.currentIndexChanged[str].connect( self.on_UpdateItemsSpatialResolution )

            return cb_collection, cb_spatial_resolution

        def createDatesWidgets():
            dt_ini = QDateEdit(QDate.currentDate().addDays(-7), self)
            dt_ini.setToolTip( tr('Select start date') )
            setDateWidget(dt_ini)
            dt_end = QDateEdit(QDate.currentDate(), self)
            dt_end.setToolTip( tr('Select end date') )
            setDateWidget(dt_end)

            return dt_ini, dt_end

        def createControls():
            widget = QWidget(self)
            widget.setObjectName('bdc_controls')
            setSyleWidget( widget )
            lyt = QHBoxLayout( widget )
            lyt.setContentsMargins(6, 0, 6, 0)
            lyt.setSpacing(8)
            lyt.addWidget( self.cbx_collection )
            lyt.addWidget( self.cbx_spatial_resolution )
            lyt.addWidget( self.dt_ini )
            lyt.addWidget( self.dt_end )
            lyt.addWidget( self.btn_folder )
            lyt.addWidget( self.btn_extent )

            return widget

        def createStatusWidget():
            widget = QWidget(self)
            widget.setObjectName('bdc_status')
            setSyleWidget(widget)
            lyt = QHBoxLayout(widget)
            lyt.setContentsMargins(6, 0, 6, 0)
            lyt.setSpacing(8)
            lbl = QLabel('', widget)
            lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            lyt.addWidget(lbl)

            return widget, lbl

        super().__init__( iface.mainWindow() )

        self.isCancelled = isCancelled
        self.config_collection = config_collection
        self.setting_key_vrt_dir = f"{setting_key}/vrt_dir"

        self._toggle_button_run = {
            True: {
                'icon': QgsApplication.getThemeIcon('mTaskRunning.svg'),
                'tooltip': tr('Run'),
                'stack_index': 0
            },
            False: {
                'icon': QgsApplication.getThemeIcon('mTaskCancel.svg'),
                'tooltip': tr("Cancel"),
                'stack_index': 1
            }
        }
        self._bbox = None
        self.iface = iface
        self.project = QgsProject.instance()
        self.setting = QgsSettings()

        self._fmt_extent = tr('Current Extent (WGS 84): {}')
        self._title_folder = tr('Select folder for VRT creation')

        self.btn_toggle = createToggleButton(True)

        self.lbl_status = QLabel('', self)
        self.lbl_status.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        ( self.cbx_collection, self.cbx_spatial_resolution ) = createCollectionSpatialResolutionComboBox()

        ( self.dt_ini, self.dt_end ) = createDatesWidgets()

        self.btn_folder = createButton(
            QgsApplication.getThemeIcon('mIconFolderOpen.svg'),
            self._title_folder,
            self.on_SelectFolderVRT
        )
        last_dir = self.setting.value( self.setting_key_vrt_dir, type=str )
        if ( last_dir and QDir(last_dir).exists() ):
            self.btn_folder.setToolTip( last_dir )
        
        self.btn_extent = createButtonExtent()

        # --- View 1 ---
        self.controls = createControls()

        # --- View 2 ---
        self.status, self.lbl_status = createStatusWidget()

        self.stack = QStackedLayout()
        self.stack.setSizeConstraint(QLayout.SetMinimumSize)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.setStackingMode(QStackedLayout.StackOne)
        self.stack.addWidget(self.controls)  # index 0
        self.stack.addWidget(self.status)    # index 1
        self.stack.setCurrentIndex(0)

        main = QHBoxLayout(self)
        main.setContentsMargins(4, 0, 4, 0)
        main.setSpacing(8)
        main.addLayout(self.stack)
        main.addWidget(self.btn_toggle)
        main.addStretch()

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setMaximumHeight(28)

    def _toggleButton (self, is_run:bool)->None:
        self.btn_toggle.is_run = is_run

        status = self._toggle_button_run[ is_run ]
        self.btn_toggle.setIcon( status['icon']  )
        self.btn_toggle.setToolTip( status['tooltip'] )
        
        self.stack.setCurrentIndex( status['stack_index'] )

    @pyqtSlot(str)
    def on_UpdateItemsSpatialResolution(self, collection:str)->None:
        self.cbx_spatial_resolution.clear()
        self.cbx_spatial_resolution.addItems( [ k for k in self.config_collection[ collection ]['spatial_res_composite'].keys() ] )

    @pyqtSlot()
    def on_SelectFolderVRT(self)->None:
        dir = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            self._title_folder,
            '' if self.btn_folder.toolTip == self._title_folder else self.btn_folder.toolTip(),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if dir:
            self.btn_folder.setToolTip( dir )
            self.setting.setValue( self.setting_key_vrt_dir, dir )

    @pyqtSlot()
    def on_CaptureExtent(self)->None:
        canvas = self.iface.mapCanvas()
        if not canvas:
            return

        self._bbox = self.btn_extent.getExtent()

        scale = canvas.scale()
        canvas.zoomScale( scale * 1.1)
        self.btn_extent.hl_manager.blink()

    @pyqtSlot()
    def on_ToggleRun(self)->None:
        def values()->dict:
            fmt_date = 'yyyy-MM-dd'

            return {
                'collection': self.cbx_collection.currentText(),
                'spatial_resolution': self.cbx_spatial_resolution.currentText(),
                'ini_date': self.dt_ini.date().toString( fmt_date ),
                'end_date': self.dt_end.date().toString( fmt_date ),
                'bbox': self._bbox,
                'vrt_dir': self.btn_folder.toolTip()
            }

        def checkValues()->dict:
            messages = []
            if self._bbox is None:
                messages.append( tr('Extent not captured') )
            if self.btn_folder.toolTip() == self._title_folder:
                messages.append( tr('VRT folder not selected') )

            return { 'is_ok': True } if not len(messages) else { 'is_ok': False, 'message': ' and '.join( messages )}

        self.iface.messageBar().clearWidgets()

        if self.btn_toggle.is_run:
            r = checkValues()
            if not r['is_ok']:
                self.iface.messageBar().pushMessage('BDC Catalog', r['message'], Qgis.Warning, 5 )
                return
        
        # Required for duplicate searches. BDCStacProcessor.process.checkDataProcessed 
        is_run_current = self.btn_toggle.is_run
        self._toggleButton(False) 

        self.goProcess.emit( values() ) if is_run_current else self.cancelProcess.emit()
        
        if not is_run_current:
            self.btn_toggle.setEnabled(False)
            return

    @pyqtSlot()
    def finished(self)->None:
        self.btn_toggle.setEnabled(True)
        self._toggleButton( True )

    @pyqtSlot(str)
    def messageStatus(self, message:str)->None:
        self.lbl_status.setText( message )
