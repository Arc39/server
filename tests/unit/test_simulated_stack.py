"""
End-to-end tests for the simulator configuration. Sets up a server with
the backend, sends some basic queries to that server and verifies results
are as expected.
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import unittest
import hashlib
import logging

import ga4gh.datamodel.variants as variants
import ga4gh.frontend as frontend
import ga4gh.protocol as protocol
import tests.utils as utils


class TestSimulatedStack(unittest.TestCase):
    """
    Tests the full stack for the Simulated backend by using the Flask
    testing client.
    """
    @classmethod
    def setUpClass(cls):
        # silence usually unhelpful CORS log
        logging.getLogger('ga4gh.frontend.cors').setLevel(logging.CRITICAL)

        config = {
            "DATA_SOURCE": "__SIMULATED__",
            "SIMULATED_BACKEND_RANDOM_SEED": 1111,
            "SIMULATED_BACKEND_NUM_CALLS": 0,
            "SIMULATED_BACKEND_VARIANT_DENSITY": 1.0,
            "SIMULATED_BACKEND_NUM_VARIANT_SETS": 10,
            "SIMULATED_BACKEND_NUM_REFERENCE_SETS": 3,
            "SIMULATED_BACKEND_NUM_REFERENCES_PER_REFERENCE_SET": 4,
            "SIMULATED_BACKEND_NUM_ALIGNMENTS_PER_READ_GROUP": 5
        }
        frontend.reset()
        frontend.configure(
            baseConfig="TestConfig", extraConfig=config)
        cls.app = frontend.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.app = None

    def setUp(self):
        self.backend = frontend.app.backend

    def sendJsonPostRequest(self, path, data):
        """
        Sends a JSON request to the specified path with the specified data
        and returns the response.
        """
        return self.app.post(
            path, headers={'Content-type': 'application/json'},
            data=data)

    def sendObjectGetRequest(self, path, id_):
        """
        Sends a GET request to the specified path for an object with the
        specified ID and returns the response.
        """
        return self.app.get("{}/{}".format(path, id_))

    def verifyVariantSetsEqual(self, gaVariantSet, variantSet):
        dataset = variantSet.getParentContainer()
        self.assertEqual(gaVariantSet.id, variantSet.getId())
        self.assertEqual(gaVariantSet.datasetId, dataset.getId())
        # TODO verify the metadata and other attributes.

    def verifyReadGroupSetsEqual(self, gaReadGroupSet, readGroupSet):
        dataset = readGroupSet.getParentContainer()
        self.assertEqual(gaReadGroupSet.id, readGroupSet.getId())
        self.assertEqual(gaReadGroupSet.datasetId, dataset.getId())
        self.assertEqual(gaReadGroupSet.name, readGroupSet.getLocalId())
        self.assertEqual(
            len(gaReadGroupSet.readGroups), len(readGroupSet.getReadGroups()))
        for gaReadGroup, readGroup in zip(
                gaReadGroupSet.readGroups, readGroupSet.getReadGroups()):
            self.verifyReadGroupsEqual(gaReadGroup, readGroup)

    def verifyReadGroupsEqual(self, gaReadGroup, readGroup):
        self.assertEqual(gaReadGroup.id, readGroup.getId())

    def verifyDatasetsEqual(self, gaDataset, dataset):
        self.assertEqual(gaDataset.id, dataset.getId())
        # TODO fill out the remaining fields and test

    def verifyReferenceSetsEqual(self, gaReferenceSet, referenceSet):
        self.assertEqual(gaReferenceSet.id, referenceSet.getId())
        referenceIds = [ref.getId() for ref in referenceSet.getReferences()]
        self.assertEqual(gaReferenceSet.referenceIds, referenceIds)
        # TODO fill out the remaining fields and test

    def verifyReferencesEqual(self, gaReference, reference):
        self.assertEqual(gaReference.id, reference.getId())
        # TODO fill out the remaining fields and test

    def verifySearchMethod(
            self, request, path, responseClass, objects, objectVerifier):
        """
        Verifies that the specified search request operates correctly
        and returns all the speficied objects. The specified verifier
        function checks that all the returned objects are equivalent
        to their datamodel counterparts.
        """
        request.pageSize = len(objects)
        response = self.sendJsonPostRequest(path, request.toJsonString())
        self.assertEqual(200, response.status_code)
        responseData = responseClass.fromJsonString(response.data)

        self.assertTrue(responseData.validate(responseData.toJsonDict()))
        self.assertIsNone(responseData.nextPageToken)

        responseList = getattr(responseData, responseClass.getValueListName())
        self.assertEqual(len(objects), len(responseList))
        for gaObject, datamodelObject in zip(responseList, objects):
            objectVerifier(gaObject, datamodelObject)

    def testDatasetsSearch(self):
        request = protocol.SearchDatasetsRequest()
        datasets = self.backend.getDatasets()
        path = utils.applyVersion('/datasets/search')
        self.verifySearchMethod(
            request, path, protocol.SearchDatasetsResponse, datasets,
            self.verifyDatasetsEqual)

    def testVariantSetsSearch(self):
        path = utils.applyVersion('/variantsets/search')
        for dataset in self.backend.getDatasets():
            variantSets = dataset.getVariantSets()
            request = protocol.SearchVariantSetsRequest()
            request.datasetId = dataset.getId()
            self.verifySearchMethod(
                request, path, protocol.SearchVariantSetsResponse, variantSets,
                self.verifyVariantSetsEqual)

    def testReadGroupSetsSearch(self):
        path = utils.applyVersion('/readgroupsets/search')
        for dataset in self.backend.getDatasets():
            readGroupSets = dataset.getReadGroupSets()
            request = protocol.SearchReadGroupSetsRequest()
            request.datasetId = dataset.getId()
            self.verifySearchMethod(
                request, path, protocol.SearchReadGroupSetsResponse,
                readGroupSets, self.verifyReadGroupSetsEqual)

    def testReferenceSetsSearch(self):
        request = protocol.SearchReferenceSetsRequest()
        referenceSets = self.backend.getReferenceSets()
        path = utils.applyVersion('/referencesets/search')
        self.verifySearchMethod(
            request, path, protocol.SearchReferenceSetsResponse, referenceSets,
            self.verifyReferenceSetsEqual)

    def testReferencesSearch(self):
        path = utils.applyVersion('/references/search')
        for referenceSet in self.backend.getReferenceSets():
            references = referenceSet.getReferences()
            request = protocol.SearchReferencesRequest()
            request.referenceSetId = referenceSet.getId()
            self.verifySearchMethod(
                request, path, protocol.SearchReferencesResponse, references,
                self.verifyReferencesEqual)

    def testGetVariantSet(self):
        path = utils.applyVersion("/variantsets")
        for dataset in self.backend.getDatasets():
            for variantSet in dataset.getVariantSets():
                response = self.sendObjectGetRequest(path, variantSet.getId())
                self.assertEqual(200, response.status_code)
                responseObject = protocol.VariantSet.fromJsonString(
                    response.data)
                self.verifyVariantSetsEqual(responseObject, variantSet)
            for badId in ["", "terribly bad ID value", "x" * 1000]:
                variantSet = variants.AbstractVariantSet(dataset, badId)
                response = self.sendObjectGetRequest(path, variantSet.getId())
                self.assertEqual(404, response.status_code)

    def testGetReadGroup(self):
        path = utils.applyVersion("/readgroups")
        for dataset in self.backend.getDatasets():
            for readGroupSet in dataset.getReadGroupSets():
                for readGroup in readGroupSet.getReadGroups():
                    response = self.sendObjectGetRequest(
                        path, readGroup.getId())
                    self.assertEqual(200, response.status_code)
                    responseObject = protocol.ReadGroupSet.fromJsonString(
                        response.data)
                    self.verifyReadGroupsEqual(responseObject, readGroup)

    def testVariantsSearch(self):
        dataset = self.backend.getDatasets()[0]
        variantSet = dataset.getVariantSets()[0]
        referenceName = '1'

        request = protocol.SearchVariantsRequest()
        request.referenceName = referenceName
        request.start = 0
        request.end = 0
        request.variantSetId = variantSet.getId()

        # Request windows is too small, no results
        path = utils.applyVersion('/variants/search')
        response = self.sendJsonPostRequest(
            path, request.toJsonString())
        self.assertEqual(200, response.status_code)
        responseData = protocol.SearchVariantsResponse.fromJsonString(
            response.data)
        self.assertIsNone(responseData.nextPageToken)
        self.assertEqual([], responseData.variants)

        # Larger request window, expect results
        request.end = 2 ** 16
        path = utils.applyVersion('/variants/search')
        response = self.sendJsonPostRequest(
            path, request.toJsonString())
        self.assertEqual(200, response.status_code)
        responseData = protocol.SearchVariantsResponse.fromJsonString(
            response.data)
        self.assertTrue(protocol.SearchVariantsResponse.validate(
            responseData.toJsonDict()))
        self.assertGreater(len(responseData.variants), 0)

        # Verify all results are in the correct range, set and reference
        for variant in responseData.variants:
            self.assertGreaterEqual(variant.start, 0)
            self.assertLessEqual(variant.end, 2 ** 16)
            self.assertEqual(variant.variantSetId, variantSet.getId())
            self.assertEqual(variant.referenceName, referenceName)

        # TODO: Add more useful test scenarios, including some covering
        # pagination behavior.

        # TODO: Add test cases for other methods when they are implemented.

    @unittest.skipIf(True, "")
    def testCallSetsSearch(self):
        # TODO remove the @skipIf decorator here once calls have been
        # properly implemented in the simulator.
        request = protocol.SearchCallSetsRequest()
        request.name = None
        path = utils.applyVersion('/callsets/search')

        # when variantSetIds are wrong, no results
        request.variantSetIds = ["xxxx"]
        response = self.sendJsonPostRequest(
            path, request.toJsonString())
        self.assertEqual(200, response.status_code)
        responseData = protocol.SearchCallSetsResponse.fromJsonString(
            response.data)
        self.assertIsNone(responseData.nextPageToken)
        self.assertEqual([], responseData.callSets)

        # if no callset name is given return all callsets
        request.variantSetIds = self.variantSetIds[:1]
        response = self.sendJsonPostRequest(
            path, request.toJsonString())
        self.assertEqual(200, response.status_code)
        responseData = protocol.SearchCallSetsResponse.fromJsonString(
            response.data)
        self.assertTrue(protocol.SearchCallSetsResponse.validate(
            responseData.toJsonDict()))
        self.assertNotEqual([], responseData.callSets)
        # TODO test the length of responseData.callSets equal to all callsets

        # Verify all results are of the correct type and range
        for callSet in responseData.callSets:
            self.assertIs(type(callSet.info), dict)
            self.assertIs(type(callSet.variantSetIds), list)
            splits = callSet.id.split(".")
            variantSetId = '.'.join(splits[:2])
            callSetName = splits[-1]
            self.assertIn(variantSetId, callSet.variantSetIds)
            self.assertEqual(callSetName, callSet.name)
            self.assertEqual(callSetName, callSet.sampleId)

        # TODO add tests after name string search schemas is implemented

    def testGetReferences(self):
        for referenceSet in self.backend.getReferenceSets():
            # fetch the reference set
            path = utils.applyVersion(
                '/referencesets/{}'.format(referenceSet.getId()))
            response = self.app.get(path)
            self.assertEqual(response.status_code, 200)
            gaReferenceSet = protocol.ReferenceSet.fromJsonString(
                response.data)
            self.verifyReferenceSetsEqual(gaReferenceSet, referenceSet)

            for reference in referenceSet.getReferences():
                # fetch the reference
                path = utils.applyVersion(
                    '/references/{}'.format(reference.getId()))
                response = self.app.get(path)
                self.assertEqual(response.status_code, 200)
                fetchedReference = protocol.Reference.fromJsonString(
                    response.data)
                self.verifyReferencesEqual(fetchedReference, reference)

                # fetch the bases
                path = utils.applyVersion(
                    '/references/{}/bases'.format(reference.getId()))
                args = protocol.ListReferenceBasesRequest().toJsonDict()
                response = self.app.get(path, data=args)
                self.assertEqual(response.status_code, 200)
                bases = protocol.ListReferenceBasesResponse.fromJsonString(
                    response.data)
                self.assertEqual(len(bases.sequence), 200)
                self.assertEqual(
                    set(bases.sequence),
                    set(['A', 'C', 'T', 'G']))
                calculatedDigest = hashlib.md5(bases.sequence).hexdigest()
                self.assertEqual(
                    calculatedDigest, fetchedReference.md5checksum)

    def testReads(self):
        path = utils.applyVersion('/reads/search')
        for dataset in self.backend.getDatasets():
            for readGroupSet in dataset.getReadGroupSets():
                for readGroup in readGroupSet.getReadGroups():
                    # search reads
                    request = protocol.SearchReadsRequest()
                    request.readGroupIds = [readGroup.getId()]
                    request.referenceId = "chr1"
                    response = self.sendJsonPostRequest(
                        path, request.toJsonString())
                    self.assertEqual(response.status_code, 200)
                    responseData = protocol.SearchReadsResponse.fromJsonString(
                        response.data)
                    alignments = responseData.alignments
                    self.assertGreater(len(alignments), 0)
                    for alignment in alignments:
                        self.assertEqual(
                            alignment.readGroupId, readGroup.getId())
