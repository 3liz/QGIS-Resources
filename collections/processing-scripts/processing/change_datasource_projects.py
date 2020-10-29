"""
  Bulk update of datasources URI in QGIS projects
"""

import re
import shutil
import traceback
import zipfile

from datetime import datetime
from itertools import chain
from pathlib import Path

from qgis.core import QgsProcessingException, QgsProcessingParameterFile
from qgis.processing import alg
from qgis.PyQt.QtXml import QDomDocument


def _read_content( path, feedback ):
    """ Read data source as text
    """
    if path.suffix == '.qgz':
        with zipfile.ZipFile(path) as zin:
            feedback.pushDebugInfo('### Opening qgz %s: %s' % (path, zin.namelist()))
            qgs = next(n for n in zin.namelist() if Path(n).suffix == '.qgs')
            return (zin.read(qgs).decode(),qgs)
    else:
        with path.open() as f:
            return (f.read(),None)


def _write_content( data, source, dest, meta, feedback ):
    """ Write Data
    """
    if meta:
        with zipfile.ZipFile(dest,'w') as zout:
            with zipfile.ZipFile(source) as zin:
                for item in zin.infolist():
                    if item.filename != meta:
                        zout.writestr(item, zin.read(item.filename))
            zout.writestr(meta,data)
    else:
        with dest.open('w') as f:
            f.write(data)


@alg(
    name='updateprojectdatasources',
    label='Update project datasources',
    help=(
            'In a given folder, the script will check in all QGS/QGZ projects for a datasource to update '
            'matching a pattern.\n Some options are possible like "Match case" about the case, "Full word" '
            'to match only if the pattern is a full word.'),
    group='project',
    group_label='QGIS Projects')
@alg.input(type=alg.FILE,   name='INPUT_FOLDER', label='Project folder', behavior=QgsProcessingParameterFile.Folder)
@alg.input(type=alg.STRING, name='INPUT_PATTERN', label='Search text')
@alg.input(type=alg.STRING, name='REPLACE_TEXT', label='Replacement text')
@alg.input(type=alg.BOOL  , name='RECURSE', label='Recurse', default=False)
@alg.input(type=alg.BOOL  , name='IGNORECASE', label='Ignore case', default=True)
@alg.input(type=alg.BOOL  , name='FULLWORD', label='FULLWORD', default=False)
@alg.input(type=alg.BOOL  , name='CREATE_BACKUP', label='Create file backup', default=True)
@alg.input(type=alg.STRING, name='FILEEXTS', label='File extensions', default="*.qgs,*.qgz")
@alg.output(type=alg.INT, name='OUTPUT_MODIFIED_COUNT', label='Number of modified projets')
def updateprojectdatasources(instance, parameters, context, feedback, inputs):
    """ updateprojectdatasources script
    """
    # Ensure that the error message is always reported to user
    def _fatalError(msg):
        feedback.reportError(msg, True)
        raise QgsProcessingException(msg)

    directory  = Path(instance.parameterAsFile(parameters,'INPUT_FOLDER',context))
    if not directory.is_dir():
        _fatalError("Invalid input directory '%s'" % directory)

    ignorecase = instance.parameterAsBool(parameters,'IGNORECASE',context)
    recurse    = instance.parameterAsBool(parameters,'RECURSE', context)
    fileexts   = instance.parameterAsString(parameters,'FILEEXTS',context).split(',')
    fullword   = instance.parameterAsBool(parameters,'FULLWORD',context)
    backups    = instance.parameterAsBool(parameters,'CREATE_BACKUP',context)

    input_pattern = instance.parameterAsString(parameters,'INPUT_PATTERN',context)
    replace_text  = instance.parameterAsString(parameters,'REPLACE_TEXT',context)

    try:
        re_flags = re.IGNORECASE if ignorecase else 0
        # Escape regexp special characters
        input_pattern = re.escape(input_pattern)
        if fullword:
            input_pattern = r"\b%s\b" % input_pattern
        input_pattern = re.compile(input_pattern,flags=re_flags)
        feedback.pushDebugInfo("search pattern: %s" % input_pattern)
    except ValueError as err:
        _fatalError("Invalid regular expression: %s" % err)

    # Collect all project candidates
    glob = directory.rglob if recurse else directory.glob

    feedback.pushDebugInfo("Collecting projects %s in %s %s" % (fileexts,directory,"(recurse on)" if recurse else ""))
    collected = list(chain(*(glob(extpat) for extpat in fileexts)))

    timestamp = int(datetime.now().timestamp())

    def _replace_datasources(path):
        # Read content
        content,meta = _read_content(path,feedback)

        # Search for data source
        dom = QDomDocument()
        dom.setContent(content)

        changed = False
        nodelist = dom.elementsByTagName("datasource")
        for node in (nodelist.at(i) for i in range(nodelist.count())):
            old_source = node.toElement().text()
            new_source = input_pattern.sub(replace_text, old_source, count=1)
            if old_source == new_source:
                # No changes
                continue

            node.firstChild().setNodeValue(new_source)
            changed = True

            if changed:
                content = dom.toString()
                feedback.pushInfo("Modified project %s" % path)
                bak = path.with_suffix('%s.%s.bak' % (path.suffix,timestamp))
                shutil.move(str(path),str(bak))

                # Save modified content
                _write_content(content, bak, path, meta, feedback)

                if not backups:
                    bak.unlink()

        return changed

    progress_step = 99.0 / len(collected) if collected else 0

    def _iterate():
        for current, path in enumerate(collected):
            feedback.setProgressText("Processing %s" % path)
            feedback.setProgress(int(current * progress_step))
            try:
                if _replace_datasources(path):
                    yield path
            except Exception as err:
                feedback.pushDebugInfo(traceback.format_exc())
                feedback.reportError("Error while processing %s: %s" % (path,err))

    modified = list(_iterate())

    return { 'OUTPUT_MODIFIED_COUNT': len(modified) }
