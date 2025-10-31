# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Debug Task
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

import debugpy

class DebugTask():
    def __init__(self):
        self.client = ('localhost', 5678)

    def active(self):
        debugpy.connect( self.client )
        debugpy.wait_for_client()
