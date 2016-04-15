"""
Tests for the repo manager tool
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import shutil
import tempfile
import unittest

import ga4gh.exceptions as exceptions
import ga4gh.datarepo as datarepo
import ga4gh.cli as cli
import tests.paths as paths


class TestGetNameFromPath(unittest.TestCase):
    """
    Tests the method for deriving the default name of objects from file
    paths.
    """
    def testError(self):
        self.assertRaises(ValueError, cli.getNameFromPath, "")

    def testLocalDirectory(self):
        self.assertEqual(cli.getNameFromPath("no_extension"), "no_extension")
        self.assertEqual(cli.getNameFromPath("x.y"), "x")
        self.assertEqual(cli.getNameFromPath("x.y.z"), "x")

    def testFullPaths(self):
        self.assertEqual(cli.getNameFromPath("/no_ext"), "no_ext")
        self.assertEqual(cli.getNameFromPath("/x.y"), "x")
        self.assertEqual(cli.getNameFromPath("/x.y.z"), "x")
        self.assertEqual(cli.getNameFromPath("/a/no_ext"), "no_ext")
        self.assertEqual(cli.getNameFromPath("/a/x.y"), "x")
        self.assertEqual(cli.getNameFromPath("/a/x.y.z"), "x")

    def testUrls(self):
        self.assertEqual(cli.getNameFromPath("file:///no_ext"), "no_ext")
        self.assertEqual(cli.getNameFromPath("http://example.com/x.y"), "x")
        self.assertEqual(cli.getNameFromPath("ftp://x.y.z"), "x")


class AbstractRepoManagerTest(unittest.TestCase):
    """
    Base class for repo manager tests
    """
    def setUp(self):
        fd, self._repoPath = tempfile.mkstemp(prefix="ga4gh_repoman_test")
        os.unlink(self._repoPath)

    def runCommand(self, cmd):
        cli.RepoManager.runCommand(cmd.split())

    def tearDown(self):
        os.unlink(self._repoPath)

    def readRepo(self):
        repo = datarepo.SqlDataRepository(self._repoPath)
        repo.open("r")
        return repo


class TestAddDataset(AbstractRepoManagerTest):

    def setUp(self):
        super(TestAddDataset, self).setUp()
        self.runCommand("init {}".format(self._repoPath))

    def testAddDataset(self):
        name = "test_dataset"
        self.runCommand("add-dataset {} {}".format(self._repoPath, name))
        repo = self.readRepo()
        dataset = repo.getDatasetByName(name)
        self.assertEqual(dataset.getLocalId(), name)

    def testAddDatasetWithSameName(self):
        name = "test_dataset"
        cmd = "add-dataset {} {}".format(self._repoPath, name)
        self.runCommand(cmd)
        self.assertRaises(
            exceptions.DuplicateNameException, self.runCommand, cmd)


class TestRemoveDataset(AbstractRepoManagerTest):

    def setUp(self):
        super(TestRemoveDataset, self).setUp()
        self.runCommand("init {}".format(self._repoPath))
        self._datasetName = "test_dataset"
        cmd = "add-dataset {} {}".format(self._repoPath, self._datasetName)
        self.runCommand(cmd)

    def testRemoveEmptyDatasetForce(self):
        self.runCommand("remove-dataset {} {} -f".format(
            self._repoPath, self._datasetName))
        repo = self.readRepo()
        self.assertRaises(
            exceptions.DatasetNameNotFoundException,
            repo.getDatasetByName, self._datasetName)


class TestAddReferenceSet(AbstractRepoManagerTest):

    def setUp(self):
        super(TestAddReferenceSet, self).setUp()
        self.runCommand("init {}".format(self._repoPath))

    def testAddReferenceSetDefaults(self):
        fastaFile = paths.ncbi37FaPath
        name = os.path.split(fastaFile)[1].split(".")[0]
        self.runCommand("add-referenceset {} {}".format(
            self._repoPath, fastaFile))
        repo = self.readRepo()
        referenceSet = repo.getReferenceSetByName(name)
        self.assertEqual(referenceSet.getLocalId(), name)
        self.assertEqual(referenceSet.getDataUrl(), fastaFile)
        # TODO check that the default values for all fields are set correctly.

    def testAddReferenceSetWithName(self):
        name = "test_reference_set"
        fastaFile = paths.ncbi37FaPath
        cmd = "add-referenceset {} {} --name={}".format(
            self._repoPath, fastaFile, name)
        self.runCommand(cmd)
        repo = self.readRepo()
        referenceSet = repo.getReferenceSetByName(name)
        self.assertEqual(referenceSet.getLocalId(), name)
        self.assertEqual(referenceSet.getDataUrl(), fastaFile)

    def testAddReferenceSetWithSameName(self):
        fastaFile = paths.ncbi37FaPath
        # Default name
        cmd = "add-referenceset {} {}".format(self._repoPath, fastaFile)
        self.runCommand(cmd)
        self.assertRaises(
            exceptions.RepoManagerException, self.runCommand, cmd)
        # Specified name
        cmd = "add-referenceset {} {} --name=testname".format(
            self._repoPath, fastaFile)
        self.runCommand(cmd)
        self.assertRaises(
            exceptions.DuplicateNameException, self.runCommand, cmd)


class TestAddReadGroupSet(AbstractRepoManagerTest):

    def setUp(self):
        super(TestAddReadGroupSet, self).setUp()
        self._datasetName = "test_ds"
        self._referenceSetName = "test_rs"
        self.runCommand("init {}".format(self._repoPath))
        self.runCommand("add-dataset {} {}".format(
            self._repoPath, self._datasetName))
        fastaFile = paths.ncbi37FaPath
        self.runCommand("add-referenceset {} {} --name={}".format(
            self._repoPath, fastaFile, self._referenceSetName))

    def verifyReadGroupSet(self, name, dataUrl, indexFile):
        repo = self.readRepo()
        dataset = repo.getDatasetByName(self._datasetName)
        referenceSet = repo.getReferenceSetByName(self._referenceSetName)
        readGroupSet = dataset.getReadGroupSetByName(name)
        self.assertEqual(readGroupSet.getLocalId(), name)
        self.assertEqual(readGroupSet.getReferenceSet(), referenceSet)
        self.assertEqual(readGroupSet.getDataUrl(), dataUrl)
        self.assertEqual(readGroupSet.getIndexFile(), indexFile)

    def testAddReadGroupSetDefaultsLocalFile(self):
        bamFile = paths.bamPath
        name = os.path.split(bamFile)[1].split(".")[0]
        cmd = "add-readgroupset {} {} {} --referenceSetName={}".format(
                self._repoPath, self._datasetName, bamFile,
                self._referenceSetName)
        self.runCommand(cmd)
        self.verifyReadGroupSet(name, bamFile, bamFile + ".bai")

    def testAddReadGroupSetLocalFileWithIndex(self):
        bamFile = paths.bamPath
        name = os.path.split(bamFile)[1].split(".")[0]
        with tempfile.NamedTemporaryFile() as temp:
            indexFile = temp.name
            shutil.copyfile(bamFile + ".bai", indexFile)
            cmd = "add-readgroupset {} {} {} {} --referenceSetName={}".format(
                    self._repoPath, self._datasetName, bamFile,
                    indexFile, self._referenceSetName)
            self.runCommand(cmd)
            self.verifyReadGroupSet(name, bamFile, indexFile)

    def testAddReadGroupSetWithNameLocalFile(self):
        bamFile = paths.bamPath
        name = "test_rgs"
        cmd = (
            "add-readgroupset {} {} {} --referenceSetName={} "
            "--name={}").format(
            self._repoPath, self._datasetName, bamFile,
            self._referenceSetName, name)
        self.runCommand(cmd)
        self.verifyReadGroupSet(name, bamFile, bamFile + ".bai")

    def testAddReadGroupSetWithSameName(self):
        # Default name
        bamFile = paths.bamPath
        name = os.path.split(bamFile)[1].split(".")[0]
        cmd = "add-readgroupset {} {} {} --referenceSetName={}".format(
                self._repoPath, self._datasetName, bamFile,
                self._referenceSetName)
        self.runCommand(cmd)
        self.assertRaises(
            exceptions.DuplicateNameException, self.runCommand, cmd)
        # Specified name
        name = "test_rgs"
        cmd = (
            "add-readgroupset {} {} {} --referenceSetName={} "
            "--name={}").format(
            self._repoPath, self._datasetName, bamFile,
            self._referenceSetName, name)
        self.runCommand(cmd)
        self.assertRaises(
            exceptions.DuplicateNameException, self.runCommand, cmd)

    def testAddReadGroupSetFromUrlMissingIndexFile(self):
        bamFile = "http://example.com/example.bam"
        cmd = "add-readgroupset {} {} {} --referenceSetName={}".format(
                self._repoPath, self._datasetName, bamFile,
                self._referenceSetName)
        self.assertRaises(
            exceptions.MissingIndexException, self.runCommand, cmd)

    def testAddReadGroupSetMissingDataset(self):
        bamFile = paths.bamPath
        cmd = "add-readgroupset {} {} {} --referenceSetName={}".format(
                self._repoPath, "not_a_dataset_name", bamFile,
                self._referenceSetName)
        self.assertRaises(
            exceptions.DatasetNameNotFoundException, self.runCommand, cmd)

    def testAddReadGroupSetMissingReferenceSet(self):
        bamFile = paths.bamPath
        cmd = "add-readgroupset {} {} {} --referenceSetName={}".format(
                self._repoPath, self._datasetName, bamFile,
                "not_a_referenceset_name")
        self.assertRaises(
            exceptions.ReferenceSetNameNotFoundException, self.runCommand, cmd)
