# (c) 2012-2019, Ansible by Red Hat
#
# This file is part of Ansible Galaxy
#
# Ansible Galaxy is free software: you can redistribute it and/or modify
# it under the terms of the Apache License as published by
# the Apache Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Ansible Galaxy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# Apache License for more details.
#
# You should have received a copy of the Apache License
# along with Galaxy.  If not, see <http://www.apache.org/licenses/>.

from collections import namedtuple
import logging
import os
from pkg_resources import iter_entry_points
import subprocess
import tempfile

import attr
import requests

from galaxy_importer import config
from galaxy_importer.constants import ContentArtifactType
from galaxy_importer import exceptions as exc
from galaxy_importer.finder import ContentFinder, RoleContentFinder
from galaxy_importer import loaders
from galaxy_importer import schema
from galaxy_importer.ansible_test import runners
from galaxy_importer.utils import markup as markup_utils
from galaxy_importer import __version__


default_logger = logging.getLogger(__name__)
log = logging.getLogger(__name__)

DOCUMENTATION_DIR = 'docs'

CollectionFilename = \
    namedtuple("CollectionFilename", ["namespace", "name", "version"])

#TODO: extract the artifact opening/extracting bits to artifacts.py?

def import_collection(file, filename=None, logger=None, cfg=None, artifact_type=None):
    """Process import on collection artifact file object.

    :raises exc.ImporterError: On errors that fail the import process.
    """
    logger.info(f'Importing with galaxy-importer {__version__}')
    if not cfg:
        config_data = config.ConfigFile.load()
        cfg = config.Config(config_data=config_data)
    logger = logger or default_logger
    return _import_collection(file, filename, logger, cfg, artifact_type)


def _import_collection(file, filename, logger, cfg, artifact_type):
    log.debug('filename: %s', filename)
    log.debug('type(filename): %s', type(filename))

    # tmp_dir_obj = tempfile.TemporaryDirectory(dir=cfg.tmp_root_dir)
    tmp_dir = tempfile.mkdtemp(dir=cfg.tmp_root_dir)
    log.debug('tmp_dir: %s', tmp_dir)

    # with tempfile.TemporaryDirectory(dir=cfg.tmp_root_dir) as tmp_dir:
    if True:
        # TODO: collection specific
        if artifact_type == ContentArtifactType.COLLECTION:
            sub_path = 'ansible_collections/placeholder_namespace/placeholder_name'
            extract_dir = os.path.join(tmp_dir, sub_path)

        if artifact_type == ContentArtifactType.ROLE:
            extract_dir = tmp_dir

        log.debug('extract_dir: %s', extract_dir)

        os.makedirs(extract_dir, exist_ok=True)

        # import pprint
        # log.debug(pprint.pformat(locals()))

        filepath = file.name
        if hasattr(file, 'file'):
            # handle a wrapped file object to get absolute filepath
            filepath = str(file.file.file.name)

        log.debug('filepath: %s', filepath)

        if not os.path.exists(filepath):
            parameters = {'ResponseContentDisposition': 'attachment;filename=archive.tar.gz'}
            storage_archive_url = file.storage.url(file.name, parameters=parameters)
            filepath = _download_archive(storage_archive_url, tmp_dir)

        _extract_archive(tarfile_path=filepath, extract_dir=extract_dir)

        log.debug('artifact %s extracted to %s', filepath, extract_dir)

        if artifact_type == ContentArtifactType.COLLECTION:
            data = CollectionArtifactLoader(extract_dir, filename,
                                            cfg=cfg, logger=logger).load()
            logger.info('Collection Artifact loading complete')

        if artifact_type == ContentArtifactType.ROLE:
            data = RoleArtifactLoader(extract_dir, filename,
                                      cfg=cfg, logger=logger).load()
            logger.info('Role Artifact loading complete')

        ansible_test_runner = runners.get_runner(cfg=cfg)
        if ansible_test_runner:
            ansible_test_runner(dir=tmp_dir, metadata=data.metadata,
                                file=file, filepath=filepath, logger=logger).run()

    _run_post_load_plugins(
        artifact_file=file,
        metadata=data.metadata,
        content_objs=None,
        logger=logger,
    )

    return attr.asdict(data)


def _download_archive(file_url, download_dir):
    filepath = os.path.join(download_dir, 'archive.tar.gz')
    r = requests.get(file_url)
    with open(filepath, 'wb') as fh:
        fh.write(r.content)
        fh.seek(0)
    return filepath


def _extract_archive(tarfile_path, extract_dir):
    try:
        _extract_tar_shell(tarfile_path=tarfile_path, extract_dir=extract_dir)
    except subprocess.SubprocessError as e:
        raise exc.ImporterError('Error in tar extract subprocess: '
                                f'{str(e)}, filepath={tarfile_path}, stderr={e.stderr}')
    except FileNotFoundError as e:
        raise exc.ImporterError('File not found in tar extract subprocess: '
                                f'{str(e)}, filepath={tarfile_path}')


def _extract_tar_shell(tarfile_path, extract_dir):
    cwd = os.path.dirname(os.path.abspath(tarfile_path))
    file_name = os.path.basename(tarfile_path)
    args = [
        'tar',
        f'--directory={extract_dir}',
        '-xf',
        file_name,
    ]
    log.debug('tar extract shell command: %s', args)
    log.debug('tar extract cwd: %s', cwd)
    subprocess.run(args, cwd=cwd, stderr=subprocess.PIPE, check=True)


class ArtifactLoader(object):
    content_finder_cls = ContentFinder

    def __init__(self, path, filename, cfg=None, logger=None):
        # self.log = logger or default_logger
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.path = path
        self.filename = filename
        self.cfg = cfg

        self.content_objs = None
        self.metadata = None
        self.docs_blob = None
        self.doc_strings = {}
        self.contents = None
        self.requires_ansible = None
        self.content_finder = self.content_finder_cls()
        log.debug('init path=%s filename=%s', path, filename)

    def _load_contents(self, path):
        """Find and load data for each content inside the collection."""
        # found_contents = ContentFinder().find_contents(self.path, self.log)
        found_contents = self.content_finder.find_contents(path, self.log)
        log.debug('found_contents from %s: %s', path, found_contents)

        for content_type, rel_path in found_contents:
            log.debug('content_type: %s rel_path: %s', content_type, rel_path)

            loader_cls = loaders.get_loader_cls(content_type)
            loader = loader_cls(
                content_type, rel_path, path, self.doc_strings, self.cfg, self.log)
            content_obj = loader.load()

            log.debug('content_obj: %s', content_obj)

            yield content_obj

    def _rename_extract_path(self):
        log.debug('self.filename: %s', self.filename)
        namespace = self.filename.namespace
        name = self.filename.name
        old_ns_dir = os.path.dirname(self.path)
        ansible_collections_dir = os.path.dirname(old_ns_dir)
        new_ns_dir = os.path.join(ansible_collections_dir, namespace)
        os.rename(old_ns_dir, new_ns_dir)

        old_name_dir = os.path.join(new_ns_dir, os.path.basename(self.path))
        new_name_dir = os.path.join(new_ns_dir, name)
        os.rename(old_name_dir, new_name_dir)
        self.path = new_name_dir
        self.log.debug(f'Renamed extract dir to: {self.path}')

    def _build_contents_blob(self):
        """Build importer result contents from Content objects."""
        return [
            schema.ResultContentItem(
                name=c.name,
                content_type=c.content_type.value,
                description=c.description,
            )
            for c in self.content_objs
        ]


class RoleArtifactLoader(ArtifactLoader):
    content_finder_cls = RoleContentFinder

    def load(self):
        # self._rename_extract_path()
        log.debug('self.filename: %s', self.filename)
        log.debug('type self.filename: %s', type(self.filename))
        self._load_role_metadata()
        full_path = os.path.join(self.path, self.sub_path)
        self.content_objs = list(self._load_contents(full_path))
        self.contents = self._build_contents_blob()
        self.requires_ansible = self.metadata['min_ansible_version']

        return schema.ImportResult(
            metadata=self.metadata,
            docs_blob=self.docs_blob,
            contents=self.contents,
            requires_ansible=self.requires_ansible,
            artifact_type=ContentArtifactType.ROLE,
        )

    @property
    def sub_path(self):
        return f'{self.filename.namespace}.{self.filename.name}-{self.filename.version}'

    def _load_role_metadata(self):
        # FIXME: handle main.yml/main.yaml
        metadata_file_path = loaders.RoleLoader._find_metadata_file_path(self.path, self.sub_path)
        # metadata_file = os.path.join(self.path, 'meta', 'main.yml')
        if not os.path.exists(metadata_file_path):
            raise exc.RoleMetadataError('No meta/main.yml found in role at %s' % self.path)

        with open(metadata_file_path, 'r') as f:
            try:
                data = schema.RoleArtifactMetaMain.parse(f.read())
            except ValueError as e:
                raise exc.RoleMetadataError(str(e))
            self.metadata = data.role_metadata_info


class CollectionArtifactLoader(ArtifactLoader):
    """Loads collection and content info."""
    content_finder_cls = ContentFinder

    def load(self):
        log.debug('self.path: %s, self.filename=%s', self.path, self.filename)
        self._load_collection_manifest()
        self._rename_extract_path()
        self._check_filename_matches_manifest()
        self._check_metadata_filepaths()

        # if self.cfg.run_ansible_doc:
        #     self.doc_strings = loaders.DocStringLoader(
        #         path=self.path,
        #         fq_collection_name='{}.{}'.format(self.metadata.namespace, self.metadata.name),
        #         logger=self.log,
        #         cfg=self.cfg,
        #     ).load()

        self.content_objs = list(self._load_contents(self.path))

        self.contents = self._build_contents_blob()
        self.docs_blob = self._build_docs_blob()
        self.requires_ansible = loaders.RuntimeFileLoader(self.path).get_requires_ansible()

        return schema.ImportResult(
            metadata=self.metadata,
            docs_blob=self.docs_blob,
            contents=self.contents,
            requires_ansible=self.requires_ansible,
            artifact_type=ContentArtifactType.COLLECTION,
        )

    def _load_collection_manifest(self):
        manifest_file = os.path.join(self.path, 'MANIFEST.json')
        if not os.path.exists(manifest_file):
            raise exc.ManifestNotFound('No manifest found in collection')

        with open(manifest_file, 'r') as f:
            try:
                data = schema.CollectionArtifactManifest.parse(f.read())
            except ValueError as e:
                raise exc.ManifestValidationError(str(e))
            self.metadata = data.collection_info


    def _check_filename_matches_manifest(self):
        if not self.filename:
            return
        for item in ['namespace', 'name', 'version']:
            filename_item = getattr(self.filename, item, None)
            metadata_item = getattr(self.metadata, item, None)
            if not filename_item:
                continue
            if filename_item != metadata_item:
                raise exc.ManifestValidationError(
                    f'Filename {item} "{filename_item}" did not match metadata "{metadata_item}"')


    def _build_docs_blob(self):
        """Build importer result docs_blob from collection documentation."""

        # return an empty DocsBlob if run_ansible_doc=False
        rendered_readme = schema.RenderedDocFile()
        docs_blob = schema.DocsBlob(
            collection_readme=rendered_readme,
            documentation_files=[],
            contents=[],
        )

        if not self.cfg.run_ansible_doc:
            return docs_blob

        contents = [
            schema.DocsBlobContentItem(
                content_name=c.name,
                content_type=c.content_type.value,
                doc_strings=c.doc_strings,
                readme_file=c.readme_file,
                readme_html=c.readme_html,
            )
            for c in self.content_objs
        ]

        rendered_readme = ""
        try:
            readme = markup_utils.get_readme_doc_file(self.path)
            if not readme:
                raise exc.ImporterError('No collection readme found')
            rendered_readme = schema.RenderedDocFile(
                name=readme.name, html=markup_utils.get_html(readme))
        except exc.ImporterError as e:
            log.error(e)

        rendered_doc_files = []
        doc_files = markup_utils.get_doc_files(
            os.path.join(self.path, DOCUMENTATION_DIR))
        if doc_files:
            rendered_doc_files = [
                schema.RenderedDocFile(
                    name=f.name, html=markup_utils.get_html(f))
                for f in doc_files
            ]

        return schema.DocsBlob(
            collection_readme=rendered_readme,
            documentation_files=rendered_doc_files,
            contents=contents,
        )

    def _check_metadata_filepaths(self):
        paths = []
        paths.append(os.path.join(self.path, self.metadata.readme))
        if self.metadata.license_file:
            paths.append(os.path.join(self.path, self.metadata.license_file))
        for path in paths:
            if not os.path.exists(path):
                raise exc.ManifestValidationError(
                    f'Could not find file {os.path.basename(path)}')


def _run_post_load_plugins(artifact_file, metadata, content_objs, logger=None):
    for ep in iter_entry_points(group='galaxy_importer.post_load_plugin'):
        logger.debug(f'Running plugin: {ep.module_name}')
        found_plugin = ep.load()
        found_plugin(
            artifact_file=artifact_file,
            metadata=metadata,
            content_objs=None,
            logger=logger,
        )
