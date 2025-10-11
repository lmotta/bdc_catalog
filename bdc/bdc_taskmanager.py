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
    QgsMessageLog, Qgis,
    QgsTask
)
from qgis.gui import QgisInterface

from .translate import tr

class TaskDebugger():
    def __init__(self):
        self.isCanceled = lambda : False
        self.isActive = lambda : True

    def setProgress(self, progress):
        #print(f"{progress} %")
        pass

    def cancel(self):
        pass


class TaskProcessor(QObject):
    messageStatus = pyqtSignal(str)
    def __init__(self, iface:QgisInterface):
        super().__init__()
        self.project = QgsProject.instance()
        self._task = None
        self._mosaic_group = None
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
        msg = tr("{} - Processing").format( self.collection )
        self.messageStatus.emit( msg )

    @pyqtSlot(dict)
    def process(self, payload:dict)->None:
        methods = {
            'message_log': self.messageLog,
            'message_bar': self.messageBar,
            'create_mosaic_group': self.createMosaicGroup,
            'footprint_status': self.footprintStatus,
            'add_layer_vector': self.addVectorLayer,
            'add_layer_mosaic_group': self.addLayerMosaicGroup
        }
        methods[ payload['type'] ]( payload['data'] )

    def messageLog(self, message:dict)->None:
        level = message['level'] if 'level' in message else Qgis.Info
        self.message_log.logMessage( message['text'], 'BDC Catalog', level=level )

    def messageBar(self, message:dict)->None:
        level = message['level'] if 'level' in message else Qgis.Info
        self.message_bar.pushMessage('BDC Catalog', message['text'], level, 5 )

    def createMosaicGroup(self, name:str)->None:
        root = self.project.layerTreeRoot()
        self._mosaic_group = QgsLayerTreeGroup( name )
        root.insertChildNode(0, self._mosaic_group)

    def footprintStatus(self, status:dict)->dict:
        self._task.setProgress( int( (status['returned'] / status['matched']) * 100 ) )
        msg = f"{self.collection} - {status['label']}"
        self.messageStatus.emit( msg )

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
        layer.setCustomProperty( 'bdc_catalog', json.dumps({ 'bbox': source['bbox'] }) )        
        if source['add_group']:
            self._addLayerToMosaicGroup( layer )
            return
        
        self.project.addMapLayer( layer,  addToLegend=False )
        root = self.project.layerTreeRoot()
        root.insertLayer(0, layer )

    def addLayerMosaicGroup(self, status:dict)->None:
        name = os.path.splitext(os.path.basename(status['filepath']))[0]
        layer = QgsRasterLayer( status['filepath'], name )
        layer.setCustomProperty( 'bdc_catalog', json.dumps({ 'layers': status['layers'] }) )

        self._addLayerToMosaicGroup( layer )
        self._task.setProgress( int( (status['mosaic_count'] / status['mosaic_total']) * 100 ) )
        msg = tr("{} - Mosaic {} of {}: {} ({})").format( self.collection, status['mosaic_count'], status['mosaic_total'], name, status['total_raster'] )
        self.messageStatus.emit( msg )


class TaskNotifier(QObject):
    sendData = pyqtSignal(dict)
    def __init__(self):
        super().__init__()

    def message(self, message:dict, type:str='message_log')->None:
        self.sendData.emit( {'type': type, 'data': message } )

    def createMosaicGroup(self, name:str)->None:
        self.sendData.emit( {'type': 'create_mosaic_group', 'data': name } )

    def footprintStatus(self, label:str, matched:int, returned:int)->None:
        self.sendData.emit( {
            'type': 'footprint_status',
            'data': { 'label': label, 'matched': matched, 'returned': returned }
        })

    def addVectorLayer(self, source:dict)->None:
        self.sendData.emit( {'type': 'add_layer_vector', 'data': source } )

    def addLayerMosaicGroup(
            self,
            filepath:str,
            layers:List[str],
            total_raster:int,
            mosaic_count:int,
            mosaic_total:int
        )->None:
        self.sendData.emit({
            'type': 'add_layer_mosaic_group',
            'data': {
                'filepath': filepath,
                'layers': layers,
                'total_raster': total_raster,
                'mosaic_count': mosaic_count,
                'mosaic_total': mosaic_total
            }
        })
