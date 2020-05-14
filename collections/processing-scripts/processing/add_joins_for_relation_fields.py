from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsVectorLayerJoinInfo,
)


class AddJoinsForRelationFieldsAlgorithm(QgsProcessingAlgorithm):

    INPUTS = 'INPUTS'
    DROP_EXISTING_JOINS = 'DROP_EXISTING_JOINS'
    OUTPUT = 'OUTPUT'

    @staticmethod
    def tr(string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return AddJoinsForRelationFieldsAlgorithm()

    def name(self):
        return 'add_joins_for_value_relation_fields'

    def displayName(self):
        return self.tr('Add joins for value relation fields')

    def group(self):
        return self.tr('Vector')

    def groupId(self):
        return 'vector'

    def shortHelpString(self):
        return self.tr(
            "Add a vector join if one field is a value relation. All these joins will not be "
            "published as WMS and WFS.")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUTS,
                self.tr('Vector layers'),
                QgsProcessing.TypeVector,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DROP_EXISTING_JOINS,
                self.tr('Drop existing joins before hand'),
                defaultValue=True,
            )
        )

    def checkParameterValues(self, parameters, context):
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        if not layers:
            return False, 'At least one layer is required'

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        drop = self.parameterAsBool(parameters, self.DROP_EXISTING_JOINS, context)

        total = len(layers)
        failed = []
        joined_fields = []

        for i, layer in enumerate(layers):
            feedback.pushInfo('Processing layer \'{}\''.format(layer.name()))
            layer_fields = layer.fields().names()
            if drop:
                for vector_join in layer.vectorJoins():
                    feedback.pushInfo('Removing join \'{}\''.format(vector_join.joinFieldName()))
                    layer.removeJoin(vector_join.joinLayerId())

            for field in layer.fields():
                widget = field.editorWidgetSetup()
                if widget.type() == 'ValueRelation':
                    config = widget.config()
                    feedback.pushInfo('Adding join on \'{}\''.format(field.name()))
                    join = QgsVectorLayerJoinInfo()
                    join.setJoinFieldName(field.name())
                    join.setTargetFieldName(config['Key'])
                    join.setJoinLayerId(config['Layer'])
                    join.setUsingMemoryCache(True)
                    if not layer.addJoin(join):
                        failed.append(layer.name())
                        feedback.reportError('Failed to add the join on {} {}'.format(layer.name(), field.name()))

                    layer.updateFields()
                    joined_fields += [field.name() for field in layer.fields() if field.name() not in layer_fields]

            # Uncheck WMS
            layer.setExcludeAttributesWMS(joined_fields)

            # Uncheck WFS for ids
            id_fields = [f for f in joined_fields if f.endswith('_ogc_fid') or f.endswith('_id')]
            layer.setExcludeAttributesWFS(id_fields)

            feedback.setProgress((i + 1) / total * 100)

        if failed:
            msg = 'Some joins failed to be added for : {}'.format(', '.join(failed))
            raise QgsProcessingException(msg)
        else:
            feedback.reportError('Everything went fine, you should restart QGIS to see the join.')

        return {}
