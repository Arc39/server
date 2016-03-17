"""
Tests the biodata module
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import unittest
import json
import os

import ga4gh.datamodel as datamodel
import ga4gh.datamodel.datasets as datasets
import ga4gh.exceptions as exceptions
import ga4gh.datamodel.biodata as biodata
import ga4gh.protocol as protocol
import ga4gh.avrotools as avrotools

import tests.paths as paths


class TestBioSamples(unittest.TestCase):
    """
    Tests the datasets class
    """
    def testToProtocolElement(self):
        self.dataset = datasets.AbstractDataset('dataset1')
        for localId in os.listdir(paths.testBioSamplesDataDir):
            jsonFilename = os.path.join(paths.bioSamplesDir, localId)
            jsonDict = {}
            try:
                with open(jsonFilename) as data:
                    jsonDict = json.load(data)
            except ValueError:
                # Poorly formed JSON throws expected exception
                self.assertRaises(
                    exceptions.FileOpenFailedException,
                    biodata.JsonBioSample, self.dataset, localId, jsonFilename)
            except IOError:
                self.assertRaises(
                    exceptions.FileOpenFailedException,
                    biodata.JsonBioSample, self.dataset, localId, jsonFilename)
            if jsonDict != {}:
                jsonDict['id'] = str(
                    datamodel.BioSampleCompoundId(
                        self.dataset._compoundId, localId))
                validator = avrotools.Validator(protocol.BioSample)
                if validator.getInvalidFields(jsonDict) != {}:
                    self.assertRaises(
                        exceptions.FileOpenFailedException,
                        biodata.JsonBioSample,
                        self.dataset,
                        localId, jsonFilename)
                else:
                    self.assertTrue(protocol.BioSample.validate(jsonDict))
