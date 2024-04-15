# Configurações específicas para o ambiente de produção
SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
prefixo = os.environ.get("COLLECTION_PUBLISHER_PREFIX")
dir_file_processed = os.environ.get("COLLECTION_PUBLISHER_CONTAINER_FILE_PROCESSED")
sat_sensor_incluse = os.environ.get("COLLECTION_PUBLISHER_LIST").split(',')
logpath = os.environ.get("COLLECTION_PUBLISHER_CONTAINER_LOG_DIR")
prefixo_data = os.environ.get("COLLECTION_PUBLISHER_PREFIX_DATA")'''

COG_MIME_TYPE = 'image/tiff; application=geotiff; profile=cloud-optimized'

dict_sat = {'AMZ1-WFI'      :'AMAZONIA_1_WFI',
            'CB4A-WFI'      :'CBERS_4A_WFI',
            'CB4-WFI'       :'CBERS_4_AWFI',
            'CB4-MUX'       :'CBERS_4_MUX',
            'CBERS-WFI'     :'CBERS_WFI_8D',  #CBERS4 + CBERS4a
            'CBERS4-MUX'    :'CBERS_4_MUX_2M',
            'CBERS4-WFI'    :'CBERS_4_WFI_16D',
            'GOES16-L2'     :'GOES_16_L2_CMI',
            'GOES13-L3'     :'GOES_13_L3_IMAGER',
            'landsat'       :'LE07_L2SP',
            'mod13q1'       :'MODIS_13_XXX',
            'mod13q1_bundle':'MODIS_13_BUNDLE_XXX',
            }

assert_list_image = ["CMASK","EVI","NDVI",
                    "CLEAROB","TOTALOB","PROVENANCE",
                    "coastal", "blue", "green", "red", "nir", "nir08",
                    "swir16","swir22","lwir","lwir11",
                    "qa_aerosol","qa_pixel","qa_radsat",
                    "st_qa","st_trad","st_urad","st_drad","st_atran",
                    "st_emis","st_emsd","st_cdist","sr_atmost_opacity","sr_cloud_qa",
                    "red_reflectance","NIR_reflectance","blue_reflectance","MIR_reflectance"
                    "VI_Quality","pixel_reliability","composite_day_of_the_year",
                    "view_zenith_angle","sun_zenith_angle","relative_azimuth_angle",
                    "visual","B01","B02","B02_1km","B03","B04","B05","B06","B07","B08",
                    "B09","B10","B11","B12","B13","B14","B15","B16"
                ]

assert_list_files = ["ang",
                    "mtl.json","mtl.xml","mtl.txt",
                    "sr_stac.json","st_stac.json",
                    "thumb_large","thumb_small",
                    "bundle"
                ]

goes_collections = ['GOES16-L2-CMI-1','GOES13-L3-IMAGER-1']  #Coleção e Versão

