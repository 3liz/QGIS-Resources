# -*- coding: utf-8 -*-
"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'Michaël Douchin'

import os
from pathlib import Path
from sys import platform
import re
import csv
import json
from glob import glob
from xml.etree import cElementTree as et
from xml.etree.ElementTree import ParseError as et_error

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProject,
    QgsDataSourceUri,
    QgsLayoutItemPicture,
    QgsSettings,
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterBoolean
)


class AuditQGISProjects(QgsProcessingAlgorithm):
    """
    List all the QGIS projects of a directory and fetch key datas
    """
    PROJECTS_ROOT_DIRECTORY = 'PROJECTS_ROOT_DIRECTORY'
    OUTPUT_CSV_PROJECTS_PATH = 'OUTPUT_CSV_PROJECTS_PATH'
    OUTPUT_CSV_LAYERS_PATH = 'OUTPUT_CSV_LAYERS_PATH'
    OUTPUT_CSV_TABLES_PATH = 'OUTPUT_CSV_TABLES_PATH'
    DONT_RESOLVE_LAYERS = 'DONT_RESOLVE_LAYERS'
    LAYER_NAME_FILTER = 'LAYER_NAME_FILTER'
    LAYER_DATASOURCE_FILTER = 'LAYER_DATASOURCE_FILTER'
    GET_LIZMAP_CONFIG_PROPERTIES = 'GET_LIZMAP_CONFIG_PROPERTIES'

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return AuditQGISProjects()

    def name(self):
        return 'audit_qgis_projects'

    def displayName(self):
        return self.tr('Audit QGIS projects')

    def group(self):
        return self.tr('Projects')

    def groupId(self):
        return 'projects'

    def shortHelpString(self):
        return self.tr(
            'Fetch the properties of all the QGIS *.qgs projects'
            ' found in a directory and its subdirectories.'
            '\n'
            'You can also find specific projects matching layers name or datasources.'
            '\n'
            'This algorithm creates CSV file(s) containing the list of projects properties'
            ' and optionally the list of layers (unique datasources and related projects)'
        )

    def helpUrl(self):
        url = 'https://gist.github.com/mdouchin/cd89a259d3560635d4bb8708ad430caa#file-readme-md'
        return url

    def initAlgorithm(self, config=None):
        # Settings
        s = QgsSettings()

        # Root directory
        projects_root_directory = s.value("lizmap/audit_projects_root_directory", Path.home())
        input_param = QgsProcessingParameterFile(
            self.PROJECTS_ROOT_DIRECTORY,
            self.tr('Local directory containing projects'),
            defaultValue=projects_root_directory,
            behavior=QgsProcessingParameterFile.Folder,
            optional=False
        )
        input_param.setHelp(self.tr(
            'The QGIS projects contained in this directory and sub-directories'
            ' will be analysed to gather their key parameters.'
        ))
        self.addParameter(input_param)

        # CSV file to create
        output_csv_projects_path = s.value(
            "lizmap/audit_output_csv_projects_path",
            os.path.join(Path.home(), 'qgis_projects_audit.csv')
        )
        input_param = QgsProcessingParameterFileDestination(
            self.OUTPUT_CSV_PROJECTS_PATH,
            self.tr('Output CSV file with the list of projects and their properties'),
            fileFilter='*.csv',
            optional=False,
            defaultValue=output_csv_projects_path
        )
        input_param.setHelp(self.tr(
            'This algorithm will create a Comma Separated Values (CSV) file'
            ' containing the list of projects with their properties.'
            ' Please choose the path.'
        ))
        self.addParameter(input_param)

        # CSV file containing unique datasources
        output_csv_layers_path = s.value(
            "lizmap/audit_output_csv_layers_path",
            os.path.join(Path.home(), 'qgis_layers_audit.csv')
        )
        input_param = QgsProcessingParameterFileDestination(
            self.OUTPUT_CSV_LAYERS_PATH,
            self.tr('Output CSV file with the list of distinct layers datasources'),
            fileFilter='*.csv',
            optional=True,
            defaultValue=output_csv_layers_path
        )
        input_param.setHelp(self.tr(
            'This algorithm will create an optional Comma Separated Values (CSV) file'
            ' containing the list of distinct datasources of layers and their projects'
        ))
        self.addParameter(input_param)

        # CSV file containing unique PostgreSQL tables
        output_csv_tables_path = s.value(
            "lizmap/audit_output_csv_tables_path",
            os.path.join(Path.home(), 'qgis_tables_audit.csv')
        )
        input_param = QgsProcessingParameterFileDestination(
            self.OUTPUT_CSV_TABLES_PATH,
            self.tr('Output CSV file with the list of distinct PostgreSQL tables'),
            fileFilter='*.csv',
            optional=True,
            defaultValue=output_csv_tables_path
        )
        input_param.setHelp(self.tr(
            'This algorithm will create an optional Comma Separated Values (CSV) file'
            ' containing the list of distinct PostgreSQL tables and their projects'
        ))
        self.addParameter(input_param)

        # Choose to resolve layers, to find invalid layers
        # If set to True, this would be much longer
        # And will not work out of QGIS Desktop
        # See https://github.com/qgis/QGIS/issues/34408
        dont_resolve_layers = s.value("lizmap/audit_dont_resolve_layers", True)
        if dont_resolve_layers in ('True', 'False'):
            dont_resolve_layers = eval(dont_resolve_layers)
        input_param = QgsProcessingParameterBoolean(
            self.DONT_RESOLVE_LAYERS,
            self.tr('Do not resolve layers'),
            defaultValue=dont_resolve_layers,
            optional=False
        )
        input_param.setHelp(self.tr(
            'If checked, the algorithm will load every layer of every project'
            ' to find invalid layers.'
            ' This could be very long depending on the number of projects,'
            ' and layers, and should be used only in QGIS Desktop context'
        ))
        self.addParameter(input_param)

        # Filter projects containing layer names
        layer_name_filter = s.value("lizmap/audit_layer_name_filter", '')
        input_param = QgsProcessingParameterString(
            self.LAYER_NAME_FILTER,
            self.tr('Filter projects with layers names like...'),
            defaultValue=layer_name_filter,
            optional=True
        )
        input_param.setHelp(self.tr(
            'If this input is not empty, the output CSV will list only'
            ' the projects containing layers corresponding to the written text.'
            ' You can write a full name or an extract.'
        ))
        self.addParameter(input_param)

        # Filter projects containing layer datasources
        layer_datasource_filter = s.value("lizmap/audit_layer_datasource_filter", '')
        input_param = QgsProcessingParameterString(
            self.LAYER_DATASOURCE_FILTER,
            self.tr('Filter projects with layers XML definition containing...'),
            defaultValue=layer_datasource_filter,
            optional=True
        )
        input_param.setHelp(self.tr(
            'If this input is not empty, the output CSV will list only'
            ' the projects containing layers corresponding to the written datasource.'
            ' You can write a full datasource or an extract.'
        ))
        self.addParameter(input_param)

        # Lizmap related data
        # If set to True, the script will look for a */qgs.cfg file
        # and fetch more properties from it
        get_lizmap_config_properties = s.value("lizmap/audit_get_lizmap_config_properties", False)
        if get_lizmap_config_properties in ('True', 'False'):
            get_lizmap_config_properties = eval(get_lizmap_config_properties)
        input_param = QgsProcessingParameterBoolean(
            self.GET_LIZMAP_CONFIG_PROPERTIES,
            self.tr('Get Lizmap configuration properties (from Lizmap *.cfg file'),
            defaultValue=get_lizmap_config_properties,
            optional=False
        )
        input_param.setHelp(self.tr(
            'If checked, the algorithm will search for a Lizmap *.cfg file'
            ' and fetch more properties from it.'
        ))
        self.addParameter(input_param)

    def getMemoryUsage(self):
        has_psutil = True
        used_memory = None
        used_memory_mb = None
        # Use psutil if available
        # else on linux use quick&dirty os call
        try:
            import psutil
        except ImportError:
            has_psutil = False

        if has_psutil:
            process = psutil.Process(os.getpid())
            used_memory = process.memory_info().rss
        else:
            if platform == "linux" or platform == "linux2":
                total_memory, used_memory, free_memory = map(
                    int,
                    os.popen('free -t -b').readlines()[-1].split()[1:]
                )
        if used_memory:
            used_memory_mb = float(used_memory / 1024 / 1024)

        return used_memory_mb

    def processAlgorithm(self, parameters, context, feedback):

        # Parameters
        projects_root_directory = parameters[self.PROJECTS_ROOT_DIRECTORY]
        output_csv_projects_path = parameters[self.OUTPUT_CSV_PROJECTS_PATH]
        output_csv_layers_path = parameters[self.OUTPUT_CSV_LAYERS_PATH]
        output_csv_tables_path = parameters[self.OUTPUT_CSV_TABLES_PATH]
        dont_resolve_layers = self.parameterAsBool(parameters, self.DONT_RESOLVE_LAYERS, context)
        layer_name_filter = self.parameterAsString(parameters, self.LAYER_NAME_FILTER, context).strip()
        layer_datasource_filter = self.parameterAsString(parameters, self.LAYER_DATASOURCE_FILTER, context).strip()
        get_lizmap_config_properties = self.parameterAsBool(parameters, self.GET_LIZMAP_CONFIG_PROPERTIES, context)

        # Store settings
        s = QgsSettings()
        s.setValue("lizmap/audit_projects_root_directory", projects_root_directory)
        s.setValue("lizmap/audit_output_csv_projects_path", output_csv_projects_path)
        s.setValue("lizmap/audit_output_csv_layers_path", output_csv_layers_path)
        s.setValue("lizmap/audit_output_csv_tables_path", output_csv_tables_path)
        s.setValue("lizmap/audit_dont_resolve_layers", str(dont_resolve_layers))
        s.setValue("lizmap/audit_layer_name_filter", str(layer_name_filter))
        s.setValue("lizmap/audit_layer_datasource_filter", str(layer_datasource_filter))
        s.setValue("lizmap/audit_get_lizmap_config_properties", str(get_lizmap_config_properties))

        # List project files
        feedback.pushInfo(self.tr('Fetching the list of QGIS project files...'))
        qgis_project_files = [y for x in os.walk(projects_root_directory) for y in glob(os.path.join(x[0], '*.qg?'))]

        # Do nothing if there are no projects
        if not qgis_project_files:
            feedback.pushInfo(self.tr('-> No project found in the given directory !'))
            return {}

        # Sort project paths alphabetically
        def sort_case_insensitive(e):
            return e.lower()

        qgis_project_files.sort(key=sort_case_insensitive)

        # Report the number of projects found
        feedback.pushInfo(
            self.tr('-> {} projects have been found in the directory and its subdirectories.'.format(
                len(qgis_project_files)
            ))
        )

        # Objects used to store the projects and layers properties
        projects = []
        exported_datasources = {}
        unique_postgresql_tables = {}
        filtered_project_number = 0

        # Loop for each project
        feedback.pushInfo(self.tr('Parsing each project file...'))
        total = len(qgis_project_files)
        for current, project_file in enumerate(qgis_project_files):
            # Stop the algorithm if the cancel button has been clicked
            if feedback.isCanceled():
                break

            # Get system memory used before reading the project
            start_memory = self.getMemoryUsage()

            # Load project
            p = QgsProject()
            if not dont_resolve_layers:
                p.read(
                    project_file
                )
            else:
                p.read(
                    project_file,
                    QgsProject.ReadFlag.FlagDontResolveLayers
                )

            # Get memory after reading project
            end_memory = self.getMemoryUsage()

            # Projet info object
            project = {}

            project_relative_file = project_file.replace(projects_root_directory, '')
            # Print project relative path
            feedback.pushInfo(
                '* {} - {}'.format(
                    str(current).zfill(len(str(total))),
                    project_relative_file
                )
            )
            # Progress bar
            feedback.setProgress(int(100 * current / total))

            # Parse layers
            name_matches = []
            datasource_matches = []
            for lid in p.mapLayers():
                # Get layer
                layer = p.mapLayer(lid)
                xml_properties = layer.originalXmlProperties()
                try:
                    root = et.fromstring(xml_properties)
                    datasource = root.find('datasource').text
                except et_error:
                    datasource = 'GHOST'
                    feedback.reportError(
                        self.tr('Project: {} - Layer "{}" ({}) - Error while parsing datasource: ghost layer ?').format(
                            project_relative_file,
                            layer.name(),
                            layer.id()
                        ),
                        False
                    )

                datasource = datasource.strip()
                match_name = True
                match_datasource = True

                # Check if the layer name matches the optional filter
                layer_name = layer.name().strip()
                if layer_name_filter:
                    if layer_name_filter.lower() in layer_name.lower():
                        name_matches.append(layer.id())
                    else:
                        match_name = False

                # Check if the datasource matches the optional filter
                if layer_datasource_filter:
                    if layer_datasource_filter in datasource:
                        datasource_matches.append(layer.id())
                    else:
                        match_datasource = False

                # Do not add the layer to the exported layers if there is no match
                if not match_name or not match_datasource:
                    continue

                # Do not add the layer datasource in the exported datasources object
                if not datasource:
                    continue

                # Add PostgreSQL schema and table if needed
                if output_csv_tables_path != 'TEMPORARY_OUTPUT' and layer.providerType() == 'postgres':
                    try:
                        uri = QgsDataSourceUri(datasource)
                        if uri:
                            table_name = '"{}"."{}"'.format(
                                uri.schema(),
                                uri.table(),
                            )
                            if table_name not in unique_postgresql_tables:
                                unique_postgresql_tables[table_name] = []
                            if project_relative_file not in unique_postgresql_tables[table_name]:
                                unique_postgresql_tables[table_name].append(project_relative_file)

                    except Exception:
                        print(self.tr('Error while parsing the PostgreSQL layer datasource'))

                # Compute the layer properties to keep
                if output_csv_layers_path != 'TEMPORARY_OUTPUT':
                    if datasource not in exported_datasources:
                        exported_datasources[datasource] = {
                            'names': [],
                            'projects': [],
                        }
                    if layer_name not in exported_datasources[datasource]['names']:
                        exported_datasources[datasource]['names'].append(layer_name)
                    if project_relative_file not in exported_datasources[datasource]['projects']:
                        exported_datasources[datasource]['projects'].append(project_relative_file)

            # Do not continue if the project does not contain filtered layers
            if layer_name_filter and not name_matches:
                feedback.pushInfo(self.tr('-> No layers for this project matches the given name filter. Skipping.'))
                continue
            if layer_datasource_filter and not datasource_matches:
                feedback.pushInfo(self.tr('-> No layers for this project matches the given XML filter. Skipping.'))
                continue

            filtered_project_number += 1

            # File name
            project['path'] = project_file
            project['basename'] = p.baseName()

            # Last modified date
            project['last_modified'] = p.lastModified().toString('yyyy-MM-dd hh:mm:ss')

            # Projection
            project['crs'] = p.crs().authid()

            # Layer count
            project['layer_count'] = p.count()

            # Memory usage in MB
            if start_memory and end_memory:
                memory_usage_mb = end_memory - start_memory
                m = round(memory_usage_mb, 2)
            else:
                m = ''
            project['memory_usage_mb'] = m

            # Bad layers
            if dont_resolve_layers:
                project['invalid_layer_count'] = ''
            else:
                project['invalid_layer_count'] = p.count() - p.validCount()

            # Composer count
            layout_manager = p.layoutManager()
            layouts = layout_manager.layouts()
            layout_number = len(layouts)
            project['print_layout_count'] = layout_number

            # Todo composer names in a list

            # Count pictures in composer and sum up size
            picture_paths = []
            picture_sizes = []
            pictures_total_size = 0
            image_re = re.compile('(bmp|gif|png|jpg|jpeg|tif)$', re.IGNORECASE)
            for lay in layouts:
                layout = layout_manager.layoutByName(lay.name())
                # avoid reports
                if not hasattr(layout, 'items'):
                    continue
                for item in layout.items():
                    if isinstance(item, QgsLayoutItemPicture):
                        picture_path = item.evaluatedPath()
                        if not os.path.isfile(picture_path):
                            picture_path = item.picturePath()
                        if not os.path.isfile(picture_path):
                            continue
                        # Keep only interesting images
                        if not image_re.search(picture_path):
                            continue

                        # Add to the list
                        # picture_paths.append(picture_path)
                        picture_added = False
                        if picture_path not in picture_paths:
                            picture_paths.append(picture_path)
                            picture_added = True

                        # Get size
                        picture_size = os.path.getsize(picture_path)
                        if not picture_size:
                            picture_size = '0'
                        # picture_sizes.append(str(picture_size))
                        if picture_added:
                            picture_sizes.append(str(picture_size))
                        pictures_total_size += int(picture_size)

            project['print_layout_pictures_paths'] = '|'.join(picture_paths)
            project['print_layout_pictures_sizes'] = '|'.join(picture_sizes)
            project['print_layout_pictures_total_size'] = pictures_total_size
            pictures_total_size_mb = float(pictures_total_size / 1024 / 1024)
            project['print_layout_pictures_total_size_mb'] = round(pictures_total_size_mb, 2)

            # Trust option
            project['trust_option_active'] = p.trustLayerMetadata()

            # Project version
            p_version = p.lastSaveVersion()
            project['last_save_version'] = '{}{}{}'.format(
                p_version.majorVersion(),
                str(p_version.minorVersion()).zfill(2),
                str(p_version.subVersion()).zfill(2)
            )

            # Lizmap plugin and Lizmap Web Client related properties
            if get_lizmap_config_properties:
                cfg_path = project_file + '.cfg'
                has_lizmap_config = os.path.isfile(cfg_path)
                project['has_lizmap_config'] = str(has_lizmap_config)
                qgis_desktop_version = ''
                lizmap_plugin_version = ''
                lizmap_web_client_target_version = ''
                project_valid = ''
                if has_lizmap_config:
                    with open(cfg_path) as cfg:
                        data = json.load(cfg)
                        if 'metadata' in data:
                            if 'qgis_desktop_version' in data['metadata']:
                                qgis_desktop_version = data['metadata']['qgis_desktop_version']
                            if 'lizmap_plugin_version' in data['metadata']:
                                lizmap_plugin_version = data['metadata']['lizmap_plugin_version']
                            if 'lizmap_web_client_target_version' in data['metadata']:
                                lizmap_web_client_target_version = data['metadata']['lizmap_web_client_target_version']
                            if 'project_valid' in data['metadata']:
                                project_valid = data['metadata']['project_valid']
                project['qgis_desktop_version'] = qgis_desktop_version
                project['lizmap_plugin_version'] = lizmap_plugin_version
                project['lizmap_web_client_target_version'] = lizmap_web_client_target_version
                project['project_valid'] = project_valid

            # Add project to the list
            projects.append(project)

        # Feedback
        feedback.pushInfo('')
        feedback.pushInfo(self.tr('-> The project files have been parsed !'))
        if total != filtered_project_number:
            feedback.pushInfo(
                self.tr('{} filtered projects among the {} listed projects !').format(
                    filtered_project_number,
                    total
                )
            )

        # Write CSV output files

        # projects CSV
        feedback.pushInfo('')
        feedback.pushInfo(self.tr('Writing the result to the CSV output file for projects...'))
        fieldnames = [
            'path', 'basename', 'last_modified', 'crs',
            'layer_count', 'invalid_layer_count', 'memory_usage_mb',
            'print_layout_count', 'print_layout_pictures_paths', 'print_layout_pictures_sizes',
            'print_layout_pictures_total_size', 'print_layout_pictures_total_size_mb',
            'trust_option_active', 'last_save_version'
        ]
        if get_lizmap_config_properties:
            fieldnames += [
                'has_lizmap_config', 'qgis_desktop_version', 'lizmap_plugin_version',
                'lizmap_web_client_target_version', 'project_valid',
            ]
        with open(output_csv_projects_path, mode='w') as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames,
                delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            writer.writerows(projects)

        feedback.pushInfo(
            self.tr(
                '-> The results have been written to the output CSV file "{}" !'.format(output_csv_projects_path)
            )
        )

        # Optional layers CSV
        if output_csv_layers_path != 'TEMPORARY_OUTPUT':
            feedback.pushInfo('')
            feedback.pushInfo(self.tr('Writing the result to the CSV output file for layers...'))
            layers = []
            for datasource in sorted(exported_datasources.keys()):
                item = exported_datasources[datasource]
                layer_item = {
                    'datasource': datasource,
                    'layer_names': '|'.join(item['names']),
                    'projects': '|'.join(item['projects']),
                }
                layers.append(layer_item)

            fieldnames = [
                'datasource', 'layer_names', 'projects'
            ]
            with open(output_csv_layers_path, mode='w') as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=fieldnames,
                    delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL
                )
                writer.writeheader()
                writer.writerows(layers)

            feedback.pushInfo(
                self.tr(
                    '-> The results have been written to the output CSV file "{}" !'.format(output_csv_layers_path)
                )
            )

        # Print unique_postgresql_tables
        if output_csv_tables_path != 'TEMPORARY_OUTPUT':
            feedback.pushInfo('')
            feedback.pushInfo(self.tr('Writing the PostgreSQL tables listed in the projects...'))
            feedback.pushInfo('')
            tables = []
            for table in sorted(unique_postgresql_tables.keys()):
                table_projects = unique_postgresql_tables[table]
                table_item = {
                    'table': table,
                    'projects': '|'.join(table_projects),
                }
                tables.append(table_item)

            fieldnames = [
                'table', 'projects'
            ]
            with open(output_csv_tables_path, mode='w') as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=fieldnames,
                    delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL
                )
                writer.writeheader()
                writer.writerows(tables)

            feedback.pushInfo(
                self.tr(
                    '-> The results have been written to the output CSV file "{}" !'.format(output_csv_tables_path)
                )
            )

        return {}
