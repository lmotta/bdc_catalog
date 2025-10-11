from osgeo import gdal

def setConfigOptionUrl()->None:
    gdal.SetConfigOption('CPL_VSICURL_TIMEOUT', '45')
    gdal.SetConfigOption('CPL_VSICURL_CONNECT_TIMEOUT', '10')
    gdal.SetConfigOption('CPL_VSICURL_RETRIES', '2')
    gdal.SetConfigOption('CPL_VSICURL_RETRY_DELAY', '3')

def setConfigClearUrl()->None:
    gdal.SetConfigOption('CPL_VSICURL_TIMEOUT', None)
    gdal.SetConfigOption('CPL_VSICURL_CONNECT_TIMEOUT', None)
    gdal.SetConfigOption('CPL_VSICURL_RETRIES', None)
    gdal.SetConfigOption('CPL_VSICURL_RETRY_DELAY', None)


def openUrl(url:str)->dict:
    try:
        ds = gdal.Open(f"/vsicurl/{url}", gdal.GA_ReadOnly)

    except Exception as e:
        return {
            'is_ok': False,
            'message': str(e)
        }
    
    return {
        'is_ok': True,
        'dataset': ds
    }
