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
        self.bdc_processor = BDCStacProcessor( iface )
        self.bdc_widget = BdcCatalogWidget( iface, self.bdc_processor.isCancelled, self.config_collection )

        self.bdc_widget.goProcess.connect( self.runProcess )
        self.bdc_widget.cancelProcess.connect( self.bdc_processor.cancelCurrentTask )

        self.bdc_processor.finished.connect( self.bdc_widget.finished )
        self.bdc_processor._processor.messageStatus.connect( self.bdc_widget.messageStatus )

    def __del__(self):
        self.iface.mainWindow().statusBar().removeWidget( self.bdc_widget )

        self.bdc_widget.goProcess.disconnect( self.runProcess )
        self.bdc_processor.finished.disconnect( self.bdc_widget.finished )
        self.bdc_processor._processor.messageStatus.disconnect( self.bdc_widget.messageStatus )

        self.bdc_widget.deleteLater()
        self.bdc_widget = None

    @pyqtSlot(dict)
    def runProcess(self, values:dict)->None:
        self.bdc_processor.setCollection( self.config_collection[ values['collection'] ])
        self.bdc_processor.spatial_resolution = values['spatial_resolution']
        self.bdc_processor.dates = [ values['ini_date'], values['end_date'] ]
        self.bdc_processor.dir_mosaic = values['vrt_dir']
        self.bdc_processor.bbox = values['bbox']

        self.bdc_processor.process()

    def addWidget(self)->None:
        self.iface.mainWindow().statusBar().addWidget( self.bdc_widget, 1 )
        self.bdc_widget.hide()

    def enabled(self, enabled:bool)->None:
        self.bdc_widget.show() if enabled else self.bdc_widget.hide()