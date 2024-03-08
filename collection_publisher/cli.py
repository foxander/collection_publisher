import os
import json
import rasterio
import click
import mimetypes
import re
import shapely.geometry
import pandas as pd
import geopandas as gpd
import rasterio.warp
import rasterio.features
#import warnings
#warnings.filterwarnings("ignore")
#import pkg_resources
#import logging.config

from logging import info,debug,warning, error, basicConfig, INFO
from datetime import datetime
from flask import Flask, current_app
from flask.cli import FlaskGroup, with_appcontext
from bdc_catalog import BDCCatalog
from osgeo import gdal, osr
from sqlalchemy import func
from bdc_catalog.models import Collection, Item, db
from bdc_catalog.utils import multihash_checksum_sha256, geom_to_wkb
from typing import List, Optional
from geoalchemy2.shape import from_shape
from filelock import FileLock
from pathlib import Path

# Obtém a variável de ambiente "ENVIRONMENT" (pode ser "development" ou "production")
environment = os.getenv("ENVIRONMENT")

if environment == "development":
    #SQLALCHEMY_DATABASE_URI='postgresql://postgres:1234@my-pg3/bdcdb'
    SQLALCHEMY_DATABASE_URI='postgresql://postgres:secreto@localhost:5432/bdcdb'
    prefixo = '/mnt/c/users/fox/projetos/INPE/biginpe/mnt/dados'
    dir_file_processed = './processed'
    sat_sensor_incluse = ['CBERS','WFI', 'AWFI','AMAZONIA', 'MUX']
    logpath = '/log'
else:
    # Configurações específicas para o ambiente de produção
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
    prefixo = os.environ.get("COLLECTION_PUBLISHER_PREFIX")
    dir_file_processed = os.environ.get("COLLECTION_PUBLISHER_CONTAINER_FILE_PROCESSED")
    sat_sensor_incluse = os.environ.get("COLLECTION_PUBLISHER_LIST").split(',')
    logpath = os.environ.get("COLLECTION_PUBLISHER_CONTAINER_LOG_DIR")

COG_MIME_TYPE = 'image/tiff; application=geotiff; profile=cloud-optimized'

dict_sat = {'CB4A-WFI':'CBERS_4A_WFI',
            'CB4-WFI':'CBERS_4_AWFI',
            'CB4-MUX':'CBERS_4_MUX',
            'AMZ1-WFI':'AMAZONIA_1_WFI'}

# Logging
logList = []

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    BDCCatalog(app)
    return app

@click.group(cls=FlaskGroup, create_app=create_app)
@click.version_option()
def cli():
    """coletor commands.
    .. note:: You can invoke more than one subcommand in one go.
    """

"""Command line."""

@cli.command()
@click.option('-c', '--collection', type=click.STRING, help='BDC Catalog collection name', required=True)
@click.option('-i', '--input-json', type=click.STRING, help='Input Json', required=True)
@click.option('-l', '--log-level', help='Log level', required=False)
@with_appcontext
def collectionpublisher(
            collection: str,
            input_json: str,
            log_level:str
            ):

        '''fmt = '%Y%m%dT%H%M%S'
        _now_str = datetime.utcnow().strftime(fmt)
        logpath1 = logpath + "_" + _now_str + ".log"

        global logger
        logger = setLogger('collectionpublisher', logpath1, log_level)'''

        if log_level:
            basicConfig(level=log_level)
        else:
            basicConfig(level='INFO')

        if os.path.exists(input_json):
            processar_arquivo(collection, input_json)
        else:
            warning("The file does not exist.")
            logList.append("The file does not exist.")

def guess_mime_type(extension: str, cog=False) -> Optional[str]:
    """Try to identify file mimetype."""
    mime = mimetypes.guess_type(extension)

    if mime[0] in COG_MIME_TYPE and cog:
        return COG_MIME_TYPE

    return mime[0]

def setLogger(log: str, log_path: str, loglevel=INFO):

    '''if log_path != None:
        path_location_log = log_path

    if loglevel != None:
        level_log = loglevel.upper()

    LOGGING_CONFIG = pkg_resources.resource_filename(
        'collection_publisher', 'logging.ini')
    logging.config.fileConfig(LOGGING_CONFIG,
                              disable_existing_loggers=False,
                              defaults={'logfilename': path_location_log,
                                        'loglevel': level_log
                                    }
                              )
    logger = logging.getLogger(log)
    return logger'''

def get_or_create_model(model_class, defaults=None, engine=None, **restrictions):
    """Get or create Brazil Data Cube model.

    Utility method for looking up an object with the given restrictions, creating one if necessary.

    Args:
        model_class (BaseModel) - Base Model of Brazil Data Cube DB
        defaults (dict) - Values to fill out model instance
        restrictions (dict) - Query Restrictions
    Returns:
        BaseModel Retrieves model instance
    """
    if not engine:
        engine = db

    instance = engine.session.query(model_class).filter_by(**restrictions).first()

    if instance:
        return instance, False

    params = dict((k, v) for k, v in restrictions.items())

    params.update(defaults or {})
    instance = model_class(**params)

    engine.session.add(instance)

    return instance, True

def collection_by_identifier(collection_name) -> Collection:
    return Collection.query() \
        .filter(func.concat(Collection.name, '-', Collection.version) == collection_name) \
        .first_or_404(f'Collection {collection_name} not found.')

def epsg_srid(file_path: str) -> int:
    """Get the Authority Code from a data set path.

    Note:
        This function requires GDAL.

    When no code found, returns None.
    """
    with rasterio.open(str(file_path)) as ds:
        crs = ds.crs

    if crs is not None:
        srid = crs.to_epsg()
        if srid is not None:
            return srid

    ref = osr.SpatialReference()
    ds = gdal.Open(str(file_path))
    wkt = ds.GetProjection()

    ref.ImportFromWkt(wkt)

    code = ref.GetAuthorityCode(None)
    return int(code) if str(code).isnumeric() else None

def create_asset(href: str,
                 mime_type: str,
                 role: List[str],
                 absolute_path: str,
                 created=None,
                 is_raster=False,
                 ):
    """Create a valid asset definition for collections.

    Args:
        loggerList_log - log file
        href - Relative path to the asset
        mime_type - Asset Mime type str
        role - Asset role. Available values are: ['data'], ['thumbnail']
        absolute_path - Absolute path to the asset. Required to generate check_sum
        created - Date time str of asset. When not set, use current timestamp.
        is_raster - Flag to identify raster. When set, `raster_size` and `chunk_size` will be set to the asset.
    """

    fmt = '%Y-%m-%dT%H:%M:%S'
    _now_str = datetime.utcnow().strftime(fmt)

    if created is None:
        created = _now_str
    elif isinstance(created, datetime):
        created = created.strftime(fmt)

    debug("Processing the checksum:multihash")

    asset = {
        'href': str(href),
        'type': mime_type,
        'bdc:size': os.stat(absolute_path).st_size,
        'checksum:multihash': multihash_checksum_sha256(str(absolute_path)),
        'roles': role,
        'created': created,
        'updated': _now_str
    }

    debug("Done!!")
    debug("Processing the chunk_x, chunk_y")

    try:
        if is_raster:
            with rasterio.open(str(absolute_path)) as data_set:
                asset['bdc:raster_size'] = dict(
                    x=data_set.shape[1],
                    y=data_set.shape[0],
                )

                chunk_x, chunk_y = data_set.profile.get('blockxsize'), data_set.profile.get('blockxsize')

                if chunk_x is None or chunk_x is None:
                    return asset

                asset['bdc:chunk_size'] = dict(x=chunk_x, y=chunk_y)
    except:
        error("Sorry, error opening image file!")
        logList.append("Sorry, error opening image file!")
        return

    debug("Done!!")

    return asset

def create_item(collection: Collection,
                reprocess: bool,
                item_name: str,
                start_date: datetime,
                end_date: datetime,
                assets_dict: dict
                ) -> bool:

    info(f'Item: {item_name}...')
    logList.append(f'Item: {item_name}...')

    assets = dict()

    cog_mime_type_tiff = 'image/tiff; application=geotiff; profile=cloud-optimized'
    mime_type_png = 'image/png'
    r = re.compile(prefixo)

    try:
        # Pre-compute metadata
        for key in assets_dict.keys():
            if key=="thumbnail":
                #href_pvi = os.path.join(pathdir,assets_dict[key])
                #file_pvi = os.path.join(prefixo, href_pvi)
                #href_pvi = '/'.join(assets_dict[key].split('/')[3:])
                href_pvi = r.sub('',assets_dict[key])
                file_pvi = assets_dict[key]
                assets["thumbnail"] = create_asset(href=str(href_pvi), mime_type=mime_type_png,
                                        role=['thumbnail'], absolute_path=str(file_pvi))
            elif (key=="CMASK") | ("BAND" in key):
                href_tci = r.sub('',assets_dict[key])
                file_tci = assets_dict[key]
                assets[key] = create_asset(href=str(href_tci), mime_type=cog_mime_type_tiff,
                                    role=['data'], absolute_path=file_tci, is_raster=True)
            else:
                href_file = r.sub('',assets_dict[key])
                file_extra = assets_dict[key]
                mini_type_file = guess_mime_type(assets_dict[key])
                assets[key] = create_asset(href=str(href_file), mime_type=mini_type_file,
                                    role=['file'], absolute_path=file_extra)

    except:
        error("Sorry, we were unable to create the Assets to the item!")
        logList.append("Sorry, we were unable to create the Assets to the item!")
        return False

    with current_app._get_current_object().app_context():
        # Let's create a new Item definition
        with db.session.begin_nested():
            item = (
                Item.query()
                .filter(Item.name == item_name,
                        Item.collection_id == collection.id)
                .first()
            )
            if item is None:
                info(f'Creating a new Item in database. Item: {item_name}.')
                logList.append(f'Creating a new Item in database. Item: {item_name}.')
                try:
                    item = Item(collection_id=collection.id, name=item_name)
                    debug("Done!")
                except:
                    error("Sorry, we were unable to create the item to the database")
                    logList.append("Sorry, we were unable to create the item to the database")
                    return False
            else:
                if reprocess:
                    try:
                        where = dict(name=item_name, collection_id=collection.id)
                        item, created = get_or_create_model(Item, defaults=item, **where)
                        info(f"Item {item_name} was modified, will be updated.")
                        logList.append(f"Item {item_name} was modified, will be updated.")
                    except:
                        error('It was not possible to update the data in the database.')
                        logList.append('It was not possible to update the data in the database.')
                        return False
                else:
                    warning('Image metadata is already in the database.')
                    logList.append('Image metadata is already in the database.')
                    return False

        debug("Saving to the database...")

        #if database_save:
        item.assets = assets
        item.cloud_cover = None
        item.start_date = datetime.strptime(start_date,'%Y-%m-%dT%H:%M:%S')
        item.end_date = datetime.strptime(end_date,'%Y-%m-%dT%H:%M:%S')

        item.srid = epsg_srid(str(file_tci))
        debug("Done!")

        try:
            debug("Processing raster_extent...")
            item.geom = from_shape(raster_extent(str(file_tci)))
            debug("Done!")
            debug("Processing footprint...")
            footprint, bbox = get_footprint(file_tci)
            item.footprint = func.ST_SetSRID(func.ST_MakeEnvelope(*footprint), 4326)
            debug("Done!")
            debug("Processing image box...")
            item.bbox = geom_to_wkb(bbox.envelope, srid=4326)
            debug("Done!")
        except:
            error("Error in footprint generation or area of ​​interest generation!")
            logList.append("Error in footprint generation or area of ​​interest generation!")
            return False

        item.is_available = True

        debug("Saving the item to the database...")

        try:
            if not reprocess:
                item.save()
            else:
                item.updated = datetime.utcnow()
                item.save()
                info(f'Item {item_name} with ID:{item.id} was updated in dababase!')
                logList.append(f'Item {item_name} with ID:{item.id} was updated in dababase!')
        except:
            error("Sorry, we were unable to save the item to the database!")
            logList.append("Sorry, we were unable to save the item to the database!")
            return False

        info(f'New Item {item_name} with ID:{item.id} was saved in dababase!')
        logList.append(f'New Item {item_name} with ID:{item.id} was saved in dababase!')

    return True

def get_footprint(imagepath: str, epsg = 'EPSG:4326') -> tuple:
    """Get image footprint

    Args:
        imagepath (str): Image file
        epsg (str): Image's EPSG

    See:
        https://rasterio.readthedocs.io/en/latest/topics/masks.html
    """
    raster_input = gdal.Open(str(imagepath), 0)
    options = gdal.TranslateOptions(format='GTiff', bandList=[1], widthPct=1, heightPct=1 )

    fileAux = str(imagepath).replace('.tif', '_aux.tif')

    # convocar a função Translate e passar o objeto 'options'
    gdal.Translate(destName=fileAux, srcDS=raster_input, options=options)

    raster_input = None

    #imagepath
    with rasterio.open(fileAux, driver = "GTiff") as dataset:
        mask = dataset.dataset_mask()

        geoms = []
        res = {'val': []}
        for geom, val in rasterio.features.shapes(mask, transform=dataset.transform):

            geom = rasterio.warp.transform_geom(dataset.crs, epsg, geom, precision=6)

            res['val'].append(val)

            geoms.append(shapely.geometry.shape(geom))

        # ToDo: Otimizar
        df = pd.DataFrame(data = res)
        gdf = gpd.GeoDataFrame(df, crs=epsg, geometry = geoms)

    os.remove(fileAux)

    return gdf.unary_union.bounds, geoms[0]

def raster_extent(imagepath: str, epsg='EPSG:4326') -> shapely.geometry.Polygon: #-> dict:
    """Get raster extent in arbitrary CRS
    Args:
        imagepath (str): Path to image
        epsg (str): EPSG Code of result crs
    Returns:
        dict: geojson-like geometry
    """
    with rasterio.open(str(imagepath)) as dataset:
        _geom = shapely.geometry.mapping(shapely.geometry.box(*dataset.bounds))
        return shapely.geometry.shape(rasterio.warp.transform_geom(dataset.crs, epsg, _geom, precision=6))

def write_log():

    if not os.path.isdir(logpath): #'processed'):
        os.mkdir(logpath) #'processed')

    fmt = '%Y%m%dT%H%M%S'
    _now_str = datetime.now().strftime(fmt)
    logpath1 = logpath + "/log_" + _now_str + ".log"

    with open(logpath1, 'a+') as f:
        f.write('\n'.join(logList))
    f.close()

def processar_arquivo(collection1:str, filename:str):
    # Verificar se existe um json
    info('Starting to publish the metadata in the database...')
    logList.append('Starting to publish the metadata in the database...')

    try:
        try:
            collection = collection_by_identifier(collection1)
        except:
            error('Error checking this collection. This collection is not valid or does not exist.')
            logList.append('Error checking this collection. This collection is not valid or does not exist.')
            return

        lockfile = filename + ".lock"
        lock = FileLock(lockfile)
        lock.acquire()

        with open(filename, 'r') as f:
            data = json.load(f)
            for i in data:
                # Verifica se no arquivo a coleção equivale a coleção passada
                sat = i['name'].split('_')[0]
                sat2 = "_".join(i['name'].split('_')[:3])
                sensor= i['name'].split('_')[2]

                #Verifica se nome da coleção é valido no arquivo
                if not (sat in sat_sensor_incluse) & (sensor in sat_sensor_incluse):
                    error('The collection parameter does not match what is indicated in the file.')
                    logList.append('The collection parameter does not match what is indicated in the file.')
                    continue

                #Verifica se o nome da coleção é igual nome da coleção no arquivo
                collection_v = "-".join(collection1.split("-")[:2])
                collection_f = dict_sat[collection_v]

                if not collection_f == sat2:
                    error('The collection parameter does not match what is indicated in the file.')
                    logList.append('The collection parameter does not match what is indicated in the file.')
                    continue

                reprocess = False

                for key in i.keys():
                    if key=='reprocess':
                        reprocess = i[key]
                        break

                create_item(collection,
                            reprocess,
                            i['name'],
                            i['start_date'],
                            i['end_date'],
                            i['assets'])
        f.close()
    except IOError:
        error(u'Error reading the file!')
        logList.append(u'Error reading the file!')
    finally:
        lock.release()

        #Move the file for processed path
        if not os.path.isdir(dir_file_processed): #'processed'):
            os.mkdir(dir_file_processed) #'processed')
        fmt = '%Y%m%dT%H%M%S'
        _now_str = datetime.now().strftime(fmt) #utcnow()
        new_filename = (Path(filename).stem) + "_" + _now_str +"_processed.json"
        #new_file = os.path.join("./processed", new_filename)
        new_file = os.path.join(dir_file_processed, new_filename)
        os.rename(filename, new_file)

        #Cleaning unnecessary files if they exist.
        if os.path.exists(lockfile):
            os.remove(lockfile)

    info('End of the process!')
    logList.append('End of the process!')

    #log
    write_log()

cli.add_command(collectionpublisher)

if __name__ == '__main__':
    '''app = create_app()
    with app.app_context():
        collectionpublisher("AMZ1-WFI-L4-SR-1", "exemplo.json", INFO)
        #coletor("AMZ1-WFI-L4-SR-1","amazonia_wfi_2024_01-items.json")'''
    cli()