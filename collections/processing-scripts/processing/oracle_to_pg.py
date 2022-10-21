import processing

from qgis.core import (
    QgsDataSourceUri,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDatabaseSchema,
    QgsProcessingParameterField,
    QgsProcessingParameterProviderConnection,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProviderRegistry,
)

__copyright__ = "Copyright 2022 , 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"

EXCLUDED_FIELDS = (
    'APIC_CDATE', 'APIC_MDATE', 'APIC_SPACE', 'APIC_STATE', 'APIC_STYLE', 'OBJECTID', 'Shape_Area',
    'Shape_Length', 'FDO_OBJECTID', 'GEOMETRY'
)


class ImportPg(QgsProcessingAlgorithm):

    LAYER = 'LAYER'
    PRIMARY_KEY = 'PRIMARY_KEY'
    DATABASE = 'DATABASE'
    SCHEMA = 'SCHEMA'
    TABLE = 'TABLE'
    OVERWRITE = 'OVERWRITE'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.LAYER,
                "Layer to import",
                [QgsProcessing.TypeVectorAnyGeometry],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.PRIMARY_KEY,
                'Primary key',
                parentLayerParameterName=self.LAYER,
                defaultValue='GID',
            )
        )

        self.addParameter(
            QgsProcessingParameterProviderConnection(
                self.DATABASE,
                "PostgreSQL database",
                "postgres",
            )
        )
        self.addParameter(
            QgsProcessingParameterDatabaseSchema(
                self.SCHEMA,
                "Schema in PostgreSQL",
                self.DATABASE,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.TABLE,
                "Name of the new table",
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.OVERWRITE,
                "Overwrite if necessary the existing table",
                defaultValue=False,
            )
        )

    def checkParameterValues(self, parameters, context):
        connection_name = self.parameterAsConnectionName(parameters, self.DATABASE, context)

        metadata = QgsProviderRegistry.instance().providerMetadata('postgres')
        connection = metadata.findConnection(connection_name)

        schema = self.parameterAsSchema(parameters, self.SCHEMA, context)
        table = self.parameterAsString(parameters, self.TABLE, context)

        overwrite = self.parameterAsBool(parameters, self.OVERWRITE, context)

        if connection.tableExists(schema, table) and not overwrite:
            msg = f"The table '{schema}.{table}' already exists. You must use the checkbox for overwriting"
            return False, msg

        return super().checkParameterValues(parameters, context)

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.LAYER, context)
        connection_name = self.parameterAsConnectionName(parameters, self.DATABASE, context)

        metadata = QgsProviderRegistry.instance().providerMetadata('postgres')
        connection = metadata.findConnection(connection_name)

        schema = self.parameterAsSchema(parameters, self.SCHEMA, context)
        table = self.parameterAsString(parameters, self.TABLE, context)

        primary_key = self.parameterAsString(parameters, self.PRIMARY_KEY, context)

        feature_count = layer.featureCount()
        feedback.pushInfo(f'{feature_count} features in the source table {layer.name()}')

        geom_type = layer.wkbType()

        fields = layer.fields().names()
        included_fields = []
        excluded_fields = []
        for field in fields:
            if field in EXCLUDED_FIELDS:
                excluded_fields.append(field)
            else:
                included_fields.append(field)
        if excluded_fields:
            feedback.pushDebugInfo(
                f"Fields detected but excluded from the import process : {', '.join(excluded_fields)}"
            )
        included_fields = ','.join(included_fields)
        feedback.pushDebugInfo(f"Fields which are kept : {included_fields}")
        options = f"-select {included_fields}"

        feedback.pushDebugInfo("Starting the import")
        processing.run(
            "gdal:importvectorintopostgisdatabaseavailableconnections",
            {
                'DATABASE': connection_name,
                'INPUT': layer,
                'SHAPE_ENCODING': layer.dataProvider().encoding(),
                'GTYPE': geom_type,
                'A_SRS': layer.crs(),
                'T_SRS': layer.crs(),
                'S_SRS': layer.crs(),
                'SCHEMA': schema,
                'TABLE': table,
                'PK': primary_key,
                'PRIMARY_KEY': primary_key,
                'GEOCOLUMN': QgsDataSourceUri(layer.source()).geometryColumn(),
                'DIM': 0,
                'SIMPLIFY': '',
                'SEGMENTIZE': '',
                'SPAT': None,
                'CLIP': False,
                'WHERE': '',
                'GT': '',
                'OVERWRITE': self.parameterAsBool(parameters, self.OVERWRITE, context),
                'APPEND': False,
                'ADDFIELDS': False,
                'LAUNDER': False,
                'INDEX': False,
                'SKIPFAILURES': False,
                'PROMOTETOMULTI': False,
                'PRECISION': False,
                'OPTIONS': options,
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True
        )
        feedback.pushDebugInfo("End of the import process")

        if not connection.tableExists(schema, table):
            raise QgsProcessingException("Error, the destination table has not been found. Please check the logs.")

        data = connection.executeSql(f"SELECT COUNT(*) FROM \"{schema}\".\"{table}\"")
        new_feature_count = data[0][0]
        if new_feature_count == feature_count:
            feedback.pushInfo(f'Import is OK with {new_feature_count} features in the new table {schema}.{table}')
        else:
            feedback.pushWarning(
                f'Import is OK but with a difference of {feature_count - new_feature_count} features in the new table. '
                f'Please check the logs.'
            )

        return {}

    def name(self):
        return 'pg_import'

    def displayName(self):
        return 'Import into PostgreSQL'

    def shortHelpString(self):
        return (
            'This algorithm allow to import a layer into a PostgreSQL database. '
            '\n\n'
            'Some fields will be excluded such as '
            '{}.'.format(', '.join(EXCLUDED_FIELDS))
        )

    def group(self):
        return 'Database'

    def groupId(self):
        return 'database'

    def createInstance(self):
        return self.__class__()
