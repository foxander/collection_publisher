import os
import json
import click
import mimetypes
import re
import shapely.geometry
import pandas as pd
import geopandas as gpd
import rasterio
import rasterio.warp
import rasterio.features
import rasterio.profiles
import traceback
import shutil

from logging import info,debug,warning, error, basicConfig, INFO
from datetime import datetime
from flask import Flask, current_app
from flask.cli import FlaskGroup, with_appcontext
from bdc_catalog import BDCCatalog
from osgeo import gdal, osr
from sqlalchemy import func
from bdc_catalog.models import Collection, Item, db, Tile
from bdc_catalog.utils import multihash_checksum_sha256, geom_to_wkb
from typing import List, Optional, Any
from geoalchemy2.shape import from_shape
from filelock import FileLock
from pathlib import Path
from netCDF4 import Dataset
from .config import *

# Logging
logList = []

fileslist = []

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
@click.option('-i', '--input-json', type=click.STRING, help='Input Json', required=False)
@click.option('-l', '--log-level', help='Log level', required=False)
@click.option('-d', '--directory', type=click.STRING, help='Directories where .json files are located', required=False)
@click.option('-a', '--authenticate', help='Checks authenticity of '.json' files', required=False)
@with_appcontext
def collectionpublisher(
            collection: str,
            input_json: str,
            log_level:str,
            directory= None,
            authenticate = False
            ):

        if log_level:
            basicConfig(level=log_level)
        else:
            basicConfig(level='INFO')

        if directory: #Procura mais arquivos '.json' numa árvore de diretórios
            for (root, _, files) in os.walk(directory, topdown=True):
                if 'items.json' in files:
                    found = os.path.join(root, directory)
                    fileslist.append(found)
        else:
            fileslist.append(input_json)

        for filejson in fileslist:
            if os.path.exists(filejson): #input_json
                process_file(collection, filejson, authenticate)
            else:
                warning("The file does not exist.")
                logList.append("The file does not exist.")

def guess_mime_type(extension: str, cog=False) -> Optional[str]:
    """Try to identify file mimetype."""
    mime = mimetypes.guess_type(extension)

    if mime[0] in COG_MIME_TYPE and cog:
        return COG_MIME_TYPE

    return mime[0]

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
    file_size = None

    debug("Checking if the file exists...")

    file_size = os.stat(absolute_path).st_size

    if file_size is None:
        info(f"The file {absolute_path}, not found in the directory.")
        logList.append(f"The file {absolute_path}, not found in the directory.")

    if created is None:
        created = _now_str
    elif isinstance(created, datetime):
        created = created.strftime(fmt)

    debug("Processing the checksum:multihash")

    asset = {
        'href': str(href),
        'type': mime_type,
        'bdc:size': file_size,
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
                cloud_cover: float,
                tile_id: str,
                item_name: str,
                start_date: datetime,
                end_date: datetime,
                assets_dict: dict
                ) -> bool:

    info(f'Item: {item_name}...')
    logList.append(f'Item: {item_name}...')

    assets = dict()

    file_tci = ''

    mime_type_png = 'image/png'
    r = re.compile(prefixo)

    with current_app._get_current_object().app_context():

        if tile_id is not None:
            tile = Tile.query().filter(
            Tile.name == tile_id,
            ).first()

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

        try:
            # Pre-compute metadata
            for key in assets_dict.keys():
                if (key=="thumbnail") | (key=="PVI"):
                    href_pvi = prefixo_data + (r.sub('',assets_dict[key]))
                    file_pvi = assets_dict[key]
                    assets["thumbnail"] = create_asset(href=str(href_pvi), mime_type=mime_type_png,
                                            role=['thumbnail'], absolute_path=str(file_pvi))
                elif (key in assert_list_image) | ("BAND" in key):
                    href_tci = prefixo_data + (r.sub('',assets_dict[key]))
                    file_tci = assets_dict[key]
                    mini_type_file = guess_mime_type(assets_dict[key])
                    assets[key] = create_asset(href=str(href_tci), mime_type=mini_type_file,
                                        role=['data'], absolute_path=file_tci, is_raster=True)
                elif (key in assert_list_files):
                    href_file = prefixo_data + (r.sub('',assets_dict[key]))
                    file_extra = assets_dict[key]
                    mini_type_file = guess_mime_type(assets_dict[key])
                    assets[key] = create_asset(href=str(href_file), mime_type=mini_type_file,
                                        role=['file'], absolute_path=file_extra)
                else:
                    error(f"Sorry, invalid key! {key}")
                    logList.append(f"Sorry, invalid key! {key}")
                        
        except:
            error("Sorry, we were unable to create the Assets to the item! {}".format(traceback.format_exc()))
            logList.append("Sorry, we were unable to create the Assets to the item! {}".format(traceback.format_exc()))
            return False

        debug("Saving to the database...")

        item.assets = assets
        item.cloud_cover = cloud_cover
        item.start_date = datetime.strptime(start_date,'%Y-%m-%dT%H:%M:%S')
        item.end_date = datetime.strptime(end_date,'%Y-%m-%dT%H:%M:%S')

        if (collection.identifier in goes_collections):
            if file_tci:
                nc = Dataset(file_tci)
                # Extent
                llx = nc.variables['geospatial_lat_lon_extent'].geospatial_westbound_longitude
                lly = nc.variables['geospatial_lat_lon_extent'].geospatial_southbound_latitude
                urx = nc.variables['geospatial_lat_lon_extent'].geospatial_eastbound_longitude
                ury = nc.variables['geospatial_lat_lon_extent'].geospatial_northbound_latitude
                boxer = str(llx) + ',' + str(lly) + ',' + str(urx) + ',' + str(ury)
                bboxer = parse_bbox(boxer)

        item.srid = epsg_srid(str(file_tci))
        if tile_id is not None:
                item.tile_id = tile.id

        debug("Done!")

        try:
            debug("Processing raster_extent...")
            if (collection.identifier in goes_collections):
                item.footprint = item.bbox = geom_to_wkb(bboxer.envelope)
            else:
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
    with rasterio.open(str(imagepath), driver = "GTiff") as dataset:
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
    try:
        if not os.path.isdir(logpath):
            os.mkdir(logpath)

        fmt = '%Y%m%dT%H%M%S'
        _now_str = datetime.now().strftime(fmt)
        logpath1 = logpath + "/log_" + _now_str + ".log"

        with open(logpath1, 'a+') as f:
            f.write('\n'.join(logList))
        f.close()
    except:
        error('Error when trying to create the "./log" directory!')
        logList.append('Error when trying to create the "./log" directory!')

def authenticity(name:str, collection:str)->bool:

    # Verifica se no arquivo a coleção equivale a coleção passada
    sat = name.split('_')[0]    #Satelite name

    if sat == 'CBERS' | sat == 'AMAZONIA':
        sensor= name.split('_')[2]  #Sensor name
        #Verifica se nome da coleção é valido no arquivo
        if not sensor in sat_sensor_incluse:
            return False
    elif sat == 'GOES':
        #regex
        pass
    elif sat == 'MODIS':
        pass
    elif sat == 'MOSAIC':
        #regex
        pass
    elif sat == 'LE07':  #Landsat7
        pass
    else:
        # Nome não corresponde a nenhuma coleção dentro do banco de dados
        return False

    #Verifica se o nome da coleção é igual nome da coleção no arquivo
    sat_sensor = "_".join(name.split('_')[:3])
    collection_v = "-".join(collection.split("-")[:2])
    collection_f = dict_sat[collection_v]

    if not collection_f == sat_sensor:
        return False

    return True

def parse_bbox(value: Any):
        fragments = value.split(',')

        if len(fragments) != 4:
            error(f'{value!r} is not a valid bbox. [xmin, ymin, xmax, ymax]')
            logList.append(f'{value!r} is not a valid bbox. [xmin, ymin, xmax, ymax]')

        try:
            xmin, ymin, xmax, ymax = [float(elm) for elm in fragments]

            return shapely.geometry.box(xmin, ymin, xmax, ymax)
        except ValueError:
            error(f'{fragments} has invalid float type')
            logList.append(f'{fragments} has invalid float type')

def process_file(collection1:str, filename:str, authenticate:bool):
    # Verificar se existe um json
    info('Starting to publish the metadata in the database...')
    logList.append('Starting to publish the metadata in the database...')

    publish_fail = []

    try:
        try:
            collection = collection_by_identifier(collection1)
        except:
            error('Error checking this collection. This collection is not valid or does not exist.')
            logList.append('Error checking this collection. This collection is not valid or does not exist.')
            return

        info(f"Collection {collection.identifier} (id={collection.id}) found.")
        logList.append(f"Collection {collection.identifier} (id={collection.id}) found.")

        lockfile = os.path.join("/tmp", os.path.basename(filename)) + ".lock"
        info(f"Creating lock file in {lockfile}")
        lock = FileLock(lockfile)
        lock.acquire()

        with open(filename, 'r') as f:
            data = json.load(f)
            info(f"File {str(filename)} loaded, {len(data)} items to check.")
            logList.append(f"File {str(filename)} loaded, {len(data)} items to check.")
            count = 1        
            for i in data:
                        if authenticate:
                                #Verifica a autenticidade do arquivo passado
                                if not authenticity(i['name'], collection1, count/len(data)):
                                    error('The collection parameter does not match what is indicated in the file.')
                                    logList.append('The collection parameter does not match what is indicated in the file.')
                                    error(f"Error preparing to create item {i['name']} [{count}/{len(data)}]")
                                    logList.append(f"Error preparing to create item {i['name']} [{count}/{len(data)}]")
                                    count+=1
                                    publish_fail.append(i['name'])
                                    continue

                        reprocess = False
                        cloud_cover = None
                        tile_id = None

                        for key in i.keys():
                                    if key=='reprocess':
                                                reprocess = i[key]
                                                continue
                                    if key=='cloud_cover':
                                                cloud_cover = i[key]
                                                continue
                                    if key=='tile_id':
                                                tile_id = i[key]
                                                continue

                                
                        info(f"Preparing to create item {i['name']} [{count}/{len(data)}]")
                        logList.append(f"Preparing to create item {i['name']} [{count}/{len(data)}]")

                        if not create_item(collection,
                                        reprocess,
                                        cloud_cover,
                                        tile_id,
                                        i['name'],
                                        i['start_date'],
                                        i['end_date'],
                                        i['assets']):
                                                    publish_fail.append(i['name'])
                                                    
                                    
                        count+=1
        f.close()
    except IOError:
        error(u'Error reading the file! {}'.format(traceback.format_exc()))
        logList.append(u'Error reading the file! {}'.format(traceback.format_exc()))
    finally:
        lock.release()

        #Move the file for processed path
        if not os.path.isdir(dir_file_processed):
            try:
                os.mkdir(dir_file_processed)
            except:
                error('Error when trying to create the "./processed" directory!')
                logList.append('Error when trying to create the "./processed" directory!')
                info('End of the process!')
                logList.append('End of the process!')
                write_log()
                return
                        
        fmt = '%Y%m%dT%H%M%S'
        _now_str = datetime.now().strftime(fmt) #utcnow()
        new_filename = (Path(filename).stem) + "_" + _now_str +"_processed.json"
        new_file = os.path.join(dir_file_processed, new_filename)
        try:
            shutil.move(filename, new_file)
        except:
            error('Error moving JSON file.')
            logList.append('Error moving JSON file.')

        #Cleaning unnecessary files if they exist.
        try:
            if os.path.exists(lockfile):
                os.remove(lockfile)
        except:
            error('Error when trying to delete the .lock file!')
            logList.append('Error when trying to delete the .lock file!')

    if publish_fail:
        for namefail in publish_fail:
            info(f'Item {namefail} has not been published!')
            logList.append(f'Item {namefail} has not been published!')
    else:
        info('Success: All items have been published!')
        logList.append('Success: All items have been published!')

    info('End of the process!')
    logList.append('End of the process!')

    #log
    write_log()

cli.add_command(collectionpublisher)

if __name__ == '__main__':
   cli()
