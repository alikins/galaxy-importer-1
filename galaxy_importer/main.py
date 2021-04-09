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

import argparse
import json
import logging
import os
import re
import sys

from galaxy_importer import collection
from galaxy_importer import config
from galaxy_importer.exceptions import ImporterError

FILENAME_REGEXP = re.compile(
    r"^(?P<namespace>\w+)-(?P<name>\w+)-"
    r"(?P<version>[0-9a-zA-Z.+-]+)\.tar\.gz$"
)
logger = logging.getLogger(__name__)
logger.error('foooo')

def main(args=None):
    config_data = config.ConfigFile.load()
    cfg = config.Config(config_data=config_data)
    setup_logger(cfg)
    args = parse_args(args)

    artifact_type = CO
    data = call_importer(filepath=args.file, cfg=cfg)
    if not data:
        return 1

    if args.print_result:
        print(json.dumps(data, indent=4))

    write_output_file(data)


def setup_logger(cfg):
    """Sets up logger with custom formatter."""
    logger.setLevel(getattr(logging, cfg.log_level_main, 'INFO'))

    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setFormatter(logging.Formatter('%(levelname)s: %(name)s %(module)s:%(funcName)s:%(lineno)d - %(message)s'))
    # logger.addHandler(ch)
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger().addHandler(ch)


class CustomFormatter(logging.Formatter):
    """Formatter that does not display INFO loglevel."""
    def formatMessage(self, record):
        if record.levelno == logging.INFO:
            return '%(message)s' % vars(record)
        else:
            return '%(levelname)s: %(name)s %(module)s:%(func)s:%(lineno)d - %(message)s' % vars(record)


def parse_args(args):
    # TODO: add arg or sub mode to indicate if importing collection or role
    parser = argparse.ArgumentParser(
        description='Run importer on collection and save result to disk.')
    parser.add_argument(
        'file',
        help='artifact to import')
    parser.add_argument(
        '--print-result',
        dest='print_result',
        action='store_true',
        help='print importer result to console')
    parser.add_argument(
        '--role',
        dest='import_role',
        action='store_true',
        help='import role instead of collection')
    return parser.parse_args(args=args)

# TODO: pass in arg for the archive type (role or container)
def call_importer(filepath, cfg):
    """Returns result of galaxy_importer import process.

    :param file: Artifact file to import.
    """
    # TODO: handle role archives and collection archives
    #       either by splitting this up or abstracting it (or both)

    # FIXME: need role archive filename regex
    match = FILENAME_REGEXP.match(os.path.basename(filepath))
    namespace, name, version = match.groups()
    filename = collection.CollectionFilename(namespace, name, version)

    with open(filepath, 'rb') as f:
        try:
            data = collection.import_collection(f, filename, logger=logger, cfg=cfg)
        except ImporterError as e:
            logger.error(f'The import failed for the following reason: {str(e)}')
            return None
        except Exception:
            logger.exception('Unexpected error occurred:')
            return None

    logger.info('Importer processing completed successfully')
    return data


def write_output_file(data):
    with open('importer_result.json', 'w') as output_file:
        output_file.write(json.dumps(data, indent=4))


if __name__ == '__main__':
    exit(main())
