__copyright__ = "Copyright 2020, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"
__revision__ = "$Format:%H$"

from qgis.core import (
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsVectorLayerJoinInfo,
)

# It seems the script is not working for QGIS >= 3.16


class AddJoinsForRelationFieldsAlgorithm(QgsProcessingAlgorithm):

    INPUTS = 'INPUTS'
    DROP_EXISTING_JOINS = 'DROP_EXISTING_JOINS'
    OUTPUT = 'OUTPUT'

    def __init__(self):
        self.layers = None
        self.drop = None
        self.prefix = '{}_'
        super().__init__()

    def createInstance(self):
        return AddJoinsForRelationFieldsAlgorithm()

    def name(self):
        return 'add_joins_for_value_relation_fields'

    def displayName(self):
        return 'Add joins for value relation fields'

    def group(self):
        return 'Vector'

    def groupId(self):
        return 'vector'

    def shortHelpString(self):
        return (
            "Add a vector join if one field is a value relation. All these joins will not be "
            "published as WMS and WFS.")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUTS,
                'Vector layers',
                QgsProcessing.TypeVector,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DROP_EXISTING_JOINS,
                'Drop existing joins before hand',
                defaultValue=True,
            )
        )

    def checkParameterValues(self, parameters, context):
        layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        if not layers:
            return False, 'At least one layer is required'

        return super().checkParameterValues(parameters, context)

    def processAlgorithm(self, parameters, context, feedback):
        self.layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        self.drop = self.parameterAsBool(parameters, self.DROP_EXISTING_JOINS, context)
        # return {}

    # def postProcess(self, context, feedback):
    #     # We try to use postProcess instead of processAlgorithm to propagate joins in the project.
    #     layers = self.layers
    #     drop = self.drop

        total = len(self.layers)
        failed = []
        feedback.pushDebugInfo('{} layer(s) have been selected.'.format(total))

        for i, layer in enumerate(self.layers):
            # Just trying on more time to get the real layer
            layer = context.project().mapLayer(layer.id())
            if not layer:
                feedback.reportError(
                    'Layer {} has not been found in the project. Skipping…'.format(layer.name()))
                continue

            feedback.pushInfo('Processing layer \'{}\' with ID {}'.format(layer.name(), layer.id()))

            joined_fields = []

            if self.drop:
                for vector_join in layer.vectorJoins():
                    feedback.pushInfo('Removing join \'{}\''.format(vector_join.joinFieldName()))
                    layer.removeJoin(vector_join.joinLayerId())

            for field in layer.fields():
                widget = field.editorWidgetSetup()

                if not widget.type() == 'ValueRelation':
                    continue

                config = widget.config()
                target_layer = config['Layer']
                target_field = config['Key']

                source_field = field.name()

                join = QgsVectorLayerJoinInfo()
                join.setJoinFieldName(source_field)
                join.setTargetFieldName(target_field)
                join.setJoinLayerId(target_layer)
                join.setUsingMemoryCache(True)

                join_layer = context.project().mapLayer(target_layer)
                feedback.pushInfo(
                    'Adding join on \'{}\' with prefix \'{}\''.format(
                        field.name(), self.prefix.format(join_layer.name())))
                join.setPrefix(self.prefix.format(join_layer.name()))
                if not layer.addJoin(join):
                    failed.append(layer.name())
                    feedback.reportError('Failed to add the join on {} {}'.format(layer.name(), field.name()))
                    continue

                for join_field in join_layer.fields():
                    joined_fields.append(self.prefix.format(join_layer.name()) + join_field.name())

            # Uncheck WMS
            feedback.pushInfo('Unchecking WMS fields')
            # if Qgis.QGIS_VERSION_INT < 31800:
            layer.setExcludeAttributesWms(joined_fields)
            # else:
            #     # Fix for QGIS >= 3.16
            #     for field in joined_fields:
            #         layer.setFieldConfigurationFlag(
            #             layer.fields().indexFromName(field), QgsField.HideFromWms, True)
            feedback.pushDebugInfo(', '.join(layer.excludeAttributesWms()))

            # Uncheck WFS for ids
            id_fields = [
                f for f in joined_fields if f.endswith('_ogc_fid') or f.endswith('_id')]
            feedback.pushInfo('Unchecking WFS fields')
            # if Qgis.QGIS_VERSION_INT < 31800:
            layer.setExcludeAttributesWfs(id_fields)
            # else:
            #     # Fix for QGIS >= 3.16
            #     for field in id_fields:
            #         layer.setFieldConfigurationFlag(
            #             layer.fields().indexFromName(field), QgsField.HideFromWfs, True)
            feedback.pushDebugInfo(', '.join(layer.excludeAttributesWfs()))

            feedback.setProgress((i + 1) / total * 100)
            # layer.reload() It does nothing, not enough to propagate the join

        if failed:
            msg = 'Some joins failed to be added for : {}'.format(', '.join(failed))
            raise QgsProcessingException(msg)

        feedback.reportError(
            'Everything went fine, BUT you must save your project and reopen it. Joins, WMS and WFS are '
            'not appearing otherwise.')

        return {}
