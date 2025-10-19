# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BDC Catalog Manager task processing
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
    TaskProcessor,
    StacClient
)


class BDCStacProcessor(StacProcessor):
    def __init__(self,
            iface:QgisInterface,
            task_processor:TaskProcessor,
            stac_client:StacClient
        ):
        super().__init__( iface, task_processor, stac_client )

    def _search_run(self, task:QgsTask)->bool:
        footprint_band = self._client.collection['spatial_res_composite'][ self.spatial_resolution ][0]
        return self._client.search( self.bbox, self.dates, footprint_band, self.requestProcessData, task.isCanceled )
