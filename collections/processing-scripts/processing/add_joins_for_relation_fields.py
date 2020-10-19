__copyright__ = "Copyright 2020, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"
__revision__ = "$Format:%H$"

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    Qgis,
    QgsField,
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

        return super().checkParameterValues(parameters, context)

    def prepareAlgorithm(self, parameters, context, feedback):
        # The algorithms take place in the main thread, to try to make vector join working without closing the
        # project, but it still not enough.
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        drop = self.parameterAsBool(parameters, self.DROP_EXISTING_JOINS, context)

        total = len(layers)
        failed = []

        for i, layer in enumerate(layers):
            # Just trying on more time to get the real layer
            layer = context.project().mapLayer(layer.id())
            feedback.pushInfo('Processing layer \'{}\' with ID {}'.format(layer.name(), layer.id()))
            joined_fields = []
            layer_fields = layer.fields().names()
            if drop:
                for vector_join in layer.vectorJoins():
                    feedback.pushInfo('Removing join \'{}\''.format(vector_join.joinFieldName()))
                    layer.removeJoin(vector_join.joinLayerId())

            for field in layer.fields():
                widget = field.editorWidgetSetup()

                if not widget.type() == 'ValueRelation':
                    continue

                config = widget.config()
                feedback.pushInfo('Adding join on \'{}\''.format(field.name()))
                join = QgsVectorLayerJoinInfo()
                join.setJoinFieldName(field.name())
                join.setTargetFieldName(config['Key'])
                join.setJoinLayerId(config['Layer'])
                join.setUsingMemoryCache(True)

                join_layer = context.project().mapLayer(config['Layer'])
                join.setPrefix(join_layer.name())
                if not layer.addJoin(join):
                    failed.append(layer.name())
                    feedback.reportError('Failed to add the join on {} {}'.format(layer.name(), field.name()))
                    continue

                for join_field in join_layer.fields():
                    if not join_field.name() in layer_fields:
                        joined_fields.append('{}{}'.format(join.prefix(), join_field.name()))

            # Uncheck WMS
            feedback.pushInfo('Unchecking WMS fields')
            if Qgis.QGIS_VERSION_INT < 31600:
                layer.setExcludeAttributesWms(joined_fields)
            else:
                for field in joined_fields:
                    layer.setFieldConfigurationFlag(
                        layer.fields().indexFromName(field), QgsField.HideFromWms, True)
            feedback.pushDebugInfo(', '.join(layer.excludeAttributesWms()))

            # Uncheck WFS for ids
            feedback.pushInfo('Unchecking WFS fields')
            id_fields = [f for f in join_layer.fields().names() if f.endswith('_ogc_fid') or f.endswith('_id')]
            if Qgis.QGIS_VERSION_INT < 31600:
                layer.setExcludeAttributesWfs(id_fields)
            else:
                for field in id_fields:
                    layer.setFieldConfigurationFlag(
                        layer.fields().indexFromName(field), QgsField.HideFromWfs, True)
            feedback.pushDebugInfo(', '.join(layer.excludeAttributesWfs()))

            feedback.setProgress((i + 1) / total * 100)
            # layer.reload() It does nothing, not enough to propagate the join

        if failed:
            msg = 'Some joins failed to be added for : {}'.format(', '.join(failed))
            raise QgsProcessingException(msg)
        else:
            feedback.reportError(
                'Everything went fine, BUT you must save your project and reopen it. Joins, WMS and WFS are '
                'not appearing otherwise.')

        return True

    def processAlgorithm(self, parameters, context, feedback):
        """ See prepareAlgorithm(). """
        return {}
