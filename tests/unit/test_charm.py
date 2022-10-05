# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops.testing import Harness

from charm import HydraCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(HydraCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
