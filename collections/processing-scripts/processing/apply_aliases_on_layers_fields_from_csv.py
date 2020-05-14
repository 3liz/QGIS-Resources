from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSource,
    QgsFeatureRequest,
)


class ApplyAliasesFromCsvAlgorithm(QgsProcessingAlgorithm):

    INPUTS = 'INPUTS'
    TABLE = 'TABLE'
    FIELD_NAME_COLUMN = 'FIELD_NAME_COLUMN'
    FIELD_ALIAS_COLUMN = 'FIELD_ALIAS_COLUMN'
    ONLY_EMPTY_ALIAS = 'ONLY_EMPTY_ALIAS'

    @staticmethod
    def tr(string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ApplyAliasesFromCsvAlgorithm()

    def name(self):
        return 'apply_aliases_from_csv'

    def displayName(self):
        return self.tr('Add aliases based on a table to many layers')

    def group(self):
        return self.tr('Vector')

    def groupId(self):
        return 'vector'

    def shortHelpString(self):
        return self.tr(
            "Add aliases based on a table to many layers")

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
            QgsProcessingParameterFeatureSource(
                self.TABLE,
                self.tr('Field definitions table'),
                [QgsProcessing.TypeVector],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_NAME_COLUMN,
                self.tr('Names'),
                parentLayerParameterName=self.TABLE,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD_ALIAS_COLUMN,
                self.tr('Aliases'),
                parentLayerParameterName=self.TABLE,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ONLY_EMPTY_ALIAS,
                self.tr('Only empty aliases'),
                defaultValue=True,
            )
        )

    def checkParameterValues(self, parameters, context):
        name_column = self.parameterAsFields(parameters, self.FIELD_NAME_COLUMN, context)
        alias_column = self.parameterAsFields(parameters, self.FIELD_ALIAS_COLUMN, context)
        if name_column == alias_column:
            return False, 'Field containing field name and field alias cannot be identical'

        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        if not layers:
            return False, 'At least one layer is required'

        return super().checkParameterValues(parameters, context)

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        table = self.parameterAsLayer(parameters, self.TABLE, context)
        field_name = self.parameterAsFields(parameters, self.FIELD_NAME_COLUMN, context)[0]
        field_alias = self.parameterAsFields(parameters, self.FIELD_ALIAS_COLUMN, context)[0]
        only_empty = self.parameterAsBool(parameters, self.ONLY_EMPTY_ALIAS, context)

        total = len(layers)

        name_index = table.fields().indexFromName(field_name)
        alias_index = table.fields().indexFromName(field_alias)

        request = QgsFeatureRequest()
        request.setFlags(QgsFeatureRequest.NoGeometry)
        request.setSubsetOfAttributes([name_index, alias_index])

        for i, layer in enumerate(layers):
            feedback.pushInfo('Processing layer \'{}\''.format(layer.name()))

            for feature_definition in table.getFeatures(request):
                field_index = layer.fields().indexFromName(feature_definition[field_name])
                # Add alias if field exists
                if field_index >= 0:
                    if layer.attributeAlias(field_index) != '' and only_empty:
                        feedback.pushInfo(' * {} is not updated (was not empty)'.format(field_name))
                        continue
                    layer.setFieldAlias(field_index, feature_definition[field_alias])
                    feedback.pushInfo(' * {} is updated'.format(field_name))

            feedback.setProgress((i + 1) / total * 100)

        return {}
