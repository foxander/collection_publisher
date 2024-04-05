# Obtém a variável de ambiente "ENVIRONMENT" (pode ser "development" ou "production")
#environment = os.getenv("ENVIRONMENT")

#if environment == "development":
    #SQLALCHEMY_DATABASE_URI='postgresql://postgres:1234@my-pg3/bdcdb'
SQLALCHEMY_DATABASE_URI='postgresql://postgres:secreto@localhost:5432/bdcdb'
prefixo = '/mnt/c/users/fox/projetos/INPE/biginpe/mnt/dados'
dir_file_processed = './processed'
sat_sensor_incluse = ['CBERS','AMAZONIA','GOES',
                      'WFI','AWFI','MUX']
logpath = './log'
prefixo_data = 'data'
'''else:
    # Configurações específicas para o ambiente de produção
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
    prefixo = os.environ.get("COLLECTION_PUBLISHER_PREFIX")
    dir_file_processed = os.environ.get("COLLECTION_PUBLISHER_CONTAINER_FILE_PROCESSED")
    sat_sensor_incluse = os.environ.get("COLLECTION_PUBLISHER_LIST").split(',')
    logpath = os.environ.get("COLLECTION_PUBLISHER_CONTAINER_LOG_DIR")
    prefixo_data = os.environ.get("COLLECTION_PUBLISHER_PREFIX_DATA")'''

COG_MIME_TYPE = 'image/tiff; application=geotiff; profile=cloud-optimized'

dict_sat = {'CB4A-WFI':'CBERS_4A_WFI',
            'CB4-WFI':'CBERS_4_AWFI',
            'CB4-MUX':'CBERS_4_MUX',
            'AMZ1-WFI':'AMAZONIA_1_WFI',
            'CBERS-WFI':'CBERS_4+4A_WFI_8D', #CBERS4 + CBERS4a
            'CBERS4-MUX':'CBERS_4_MUX_2M',
            'CBERS4-WFI':'CBERS_4_WFI_16D',
            'GOES-16':'GOES_16_L2_CMI'}

assert_list_image = ["CMASK","EVI","NDVI",
                    "CLEAROB","TOTALOB","PROVENANCE",
                    "coastal", "blue", "green", "red", "nir", "nir08",
                    "swir16","swir22","lwir","lwir11",
                    "qa_aerosol","qa_pixel","qa_radsat",
                    "st_qa","st_trad","st_urad","st_drad","st_atran",
                    "st_emis","st_emsd","st_cdist","sr_atmost_opacity","sr_cloud_qa",
                    "red_reflectance","NIR_reflectance","blue_reflectance","MIR_reflectance"
                    "VI_Quality","pixel_reliability","composite_day_of_the_year",
                    "view_zenith_angle","sun_zenith_angle","relative_azimuth_angle"
                ]

assert_list_files = ["ang",
                    "mtl.json","mtl.xml","mtl.txt",
                    "sr_stac.json","st_stac.json",
                    "thumb_large","thumb_small",
                    "bundle"
                ]

