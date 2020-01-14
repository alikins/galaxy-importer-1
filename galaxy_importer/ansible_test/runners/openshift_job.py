# (c) 2012-2020, Ansible by Red Hat
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


# from galaxy_importer.ansible_test import container_build
from galaxy_importer.ansible_test.runners.base import BaseTestRunner


class OpenshiftJobTestRunner(BaseTestRunner):
    """Run image as an openshift job."""
    def run(self):
        # image = container_build.build_image_with_artifact()
        pass
