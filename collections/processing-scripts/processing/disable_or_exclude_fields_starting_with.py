from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
)


class DisableOrExcludeFieldsStartWithAlgorithm(QgsProcessingAlgorithm):

    INPUTS = 'INPUTS'
    READ_ONLY_FIELDS = 'READ_ONLY_FIELDS'
    EXCLUDED_FIELDS = 'EXCLUDED_FIELDS'
    EXCLUDE_PRIMARY_KEY = 'EXCLUDE_PRIMARY_KEY'

    @staticmethod
    def tr(string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return DisableOrExcludeFieldsStartWithAlgorithm()

    def name(self):
        return 'disable_or_exclude_fields_start_with'

    def displayName(self):
        return self.tr('Disable or exclude fields from QGIS Server')

    def group(self):
        return self.tr('Vector')

    def groupId(self):
        return 'vector'

    def shortHelpString(self):
        return self.tr("Disable or exclude fields from QGIS Server")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUTS,
                self.tr('Vector layers'),
                QgsProcessing.TypeVector,
                optional=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.READ_ONLY_FIELDS,
                self.tr('Set field read-only when starting with'),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.EXCLUDED_FIELDS,
                self.tr('Exclude field from QGIS Server when starting with'),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.EXCLUDE_PRIMARY_KEY,
                self.tr('Exclude primary key'),
            )
        )

    def checkParameterValues(self, parameters, context):
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        if not layers:
            return False, 'At least one layer is required'

        return super().checkParameterValues(parameters, context)

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        read_only_pattern = self.parameterAsString(parameters, self.READ_ONLY_FIELDS, context)
        excluded_pattern = self.parameterAsString(parameters, self.EXCLUDED_FIELDS, context)
        primary_key = self.parameterAsBool(parameters, self.EXCLUDE_PRIMARY_KEY, context)

        layers = [layer for layer in layers if layer.providerType() == 'postgres']
        if not layers:
            raise QgsProcessingException(self.tr('At least one PostgreSQL layer is required'))

        total = len(layers)

        for i, layer in enumerate(layers):
            feedback.pushInfo('Processing layer \'{}\''.format(layer.name()))

            excluded_fields = []
            pks = layer.primaryKeyAttributes()
            pk_fields = []

            for field in layer.fields():
                name = field.name()
                index = layer.fields().indexFromName(name)
                if read_only_pattern and name.startswith(read_only_pattern):
                    # Set readonly
                    feedback.pushInfo('Set readonly \'{}\''.format(name))
                    config = layer.editFormConfig()
                    config.setReadOnly(index, True)
                    layer.setEditFormConfig(config)
                if excluded_pattern and name.startswith(excluded_pattern):
                    # Disable on WFS and WMS
                    feedback.pushInfo('Set disabled \'{}\''.format(name))
                    excluded_fields.append(name)
                if primary_key and index in pks:
                    # Disable on WMS
                    feedback.pushInfo('Set disabled PK \'{}\''.format(name))
                    pk_fields.append(index)

            if excluded_fields:
                layer.setExcludeAttributesWms(list(layer.excludeAttributesWms()) + excluded_fields)
                layer.setExcludeAttributesWfs(list(layer.excludeAttributesWfs()) + excluded_fields)
            if pk_fields:
                layer.setExcludeAttributesWms(list(layer.excludeAttributesWms()) + pk_fields)

            feedback.setProgress((i + 1) / total * 100)

        return {}
