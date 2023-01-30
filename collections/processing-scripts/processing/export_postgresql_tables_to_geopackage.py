import os

from processing.algs.gdal.GdalUtils import GdalUtils
from qgis.core import (
    QgsDataSourceUri,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterProviderConnection,
    QgsProcessingParameterString,
    QgsProviderRegistry,
)
from qgis.PyQt.QtCore import QCoreApplication


class ExportPostgresqlTablesToGeopackage(QgsProcessingAlgorithm):
    """
    Export tables from postgreSQL listed schemas to geopackage file
    """

    CONNECTION_NAME = 'CONNECTION_NAME'
    SCHEMAS = 'SCHEMAS'
    TABLES_BLOCK_LIST = 'TABLE_BLOCK_LIST'
    DESTINATION = 'DESTINATION'

    @staticmethod
    def tr(string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ExportPostgresqlTablesToGeopackage()

    def name(self):
        return 'export_postgresql_tables_to_geopackage'

    def displayName(self):
        return self.tr('Export PostgreSQL tables to a Geopackage file')

    def group(self):
        return self.tr('Vector')

    def groupId(self):
        return 'vector'

    def shortHelpString(self):
        return self.tr(
            "Choose a PostgreSQL connection, give a list of schemas separated by comma, and the destination GeoPackage "
            "file to create"
        )

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        db_param = QgsProcessingParameterProviderConnection(
            self.CONNECTION_NAME,
            self.tr('PostgreSQL connection'),
            "postgres",
            optional=False,
        )
        self.addParameter(db_param)

        schemas_param = QgsProcessingParameterString(
            self.SCHEMAS,
            self.tr('List of schemas, separated by commas'),
            optional=False
        )
        self.addParameter(schemas_param)

        self.addParameter(
            QgsProcessingParameterString(
                self.TABLES_BLOCK_LIST,
                self.tr('List of tables to NOT export, separated by commas'),
                defaultValue='public.spatial_ref_sys',
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.DESTINATION,
                'GeoPackage file',
                fileFilter='gpkg'
            )
        )

    def getPostgisConnectionUriFromName(self, connection_name):
        """
        Return a QgsDatasourceUri from a PostgreSQL connection name
        """
        metadata = QgsProviderRegistry.instance().providerMetadata('postgres')
        connection = metadata.findConnection(connection_name)
        uri_string = connection.uri()
        uri = QgsDataSourceUri(uri_string)

        return uri

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """
        connection_name = parameters[self.CONNECTION_NAME]
        schemas = self.parameterAsString(parameters, self.SCHEMAS, context)
        schemas = ','.join([s.strip() for s in schemas.split(',')])
        output_path = self.parameterAsString(parameters, self.DESTINATION, context)
        if not output_path.lower().endswith('.gpkg'):
            output_path += '.gpkg'

        if os.path.exists(output_path):
            os.remove(output_path)
            feedback.pushDebugInfo(self.tr('Previous Geopackage has been deleted !'))

        uri = self.getPostgisConnectionUriFromName(connection_name)
        if uri.service():
            ogr_source = 'PG:service=%s schemas=%s ' % (
                uri.service(),
                schemas
            )
        else:
            ogr_source = 'PG:host=%s port=%s dbname=%s user=%s password=%s schemas=%s ' % (
                uri.host(),
                uri.port(),
                uri.database(),
                uri.username(),
                uri.password(),
                schemas
            )

        ogr_arguments = [
            '',
            '-overwrite',
            '-progress',
            '-f', 'GPKG',
            output_path,
            ogr_source,
            '-lco', 'GEOMETRY_NAME=geom',
            '-lco', 'SPATIAL_INDEX=YES',
            '-gt', '50000',
            '--config', 'PG_LIST_ALL_TABLES', 'YES',
            '--config', 'PG_SKIP_VIEWS', 'YES',
            '--config', 'OGR_SQLITE_SYNCHRONOUS', 'OFF',
            '--config', 'OGR_SQLITE_CACHE', '1024'
        ]

        feedback.pushInfo('OGR command = ogr2ogr {}'.format(' '.join(ogr_arguments)))
        GdalUtils.runGdal(['ogr2ogr', GdalUtils.escapeAndJoin(ogr_arguments)], feedback)

        if not os.path.isfile(output_path):
            raise QgsProcessingException(self.tr('GeoPackage has not been sucessfully created.'))

        feedback.pushInfo(self.tr('Geopackage sucessfull created: "{}"'.format(output_path)))

        return {}
