"""
Module responsible for handling protocol requests and returning
responses.
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import json

import ga4gh.datamodel as datamodel
import ga4gh.datamodel.datasets as datasets
import ga4gh.datamodel.references as references
import ga4gh.exceptions as exceptions
import ga4gh.protocol as protocol


def _parseIntegerArgument(args, key, defaultValue):
    """
    Attempts to parse the specified key in the specified argument
    dictionary into an integer. If the argument cannot be parsed,
    raises a BadRequestIntegerException. If the key is not present,
    return the specified default value.
    """
    ret = defaultValue
    if key in args:
        try:
            ret = int(args[key])
        except ValueError:
            raise exceptions.BadRequestIntegerException(key, args[key])
    return ret


def _parsePageToken(pageToken, numValues):
    """
    Parses the specified pageToken and returns a list of the specified
    number of values. Page tokens are assumed to consist of a fixed
    number of integers seperated by colons. If the page token does
    not conform to this specification, raise a InvalidPageToken
    exception.
    """
    tokens = pageToken.split(":")
    if len(tokens) != numValues:
        msg = "Invalid number of values in page token"
        raise exceptions.BadPageTokenException(msg)
    try:
        values = map(int, tokens)
    except ValueError:
        msg = "Malformed integers in page token"
        raise exceptions.BadPageTokenException(msg)
    return values


def _getVariantSet(request, variantSetIdMap):
    variantSetId = request.variantSetId
    variantSet = _safeMapQuery(
        variantSetIdMap, variantSetId,
        exceptionClass=exceptions.VariantSetNotFoundException)
    return variantSet


def _safeMapQuery(idMap, id_, exceptionClass=None, idErrorString=None):
    """
    Attempt to retrieve a value from a map, throw an appropriate error
    if the key is not present
    """
    try:
        obj = idMap[id_]
    except KeyError:
        if idErrorString is None:
            idErrorString = id_
        if exceptionClass is None:
            exceptionClass = exceptions.ObjectWithIdNotFoundException
        raise exceptionClass(idErrorString)
    return obj


class IntervalIterator(object):
    """
    Implements generator logic for types which accept a start/end
    range to search for the object. Returns an iterator over
    (object, pageToken) pairs. The pageToken is a string which allows
    us to pick up the iteration at any point, and is None for the last
    value in the iterator.
    """
    def __init__(self, request, containerIdMap):
        self._request = request
        self._containerIdMap = containerIdMap
        self._container = self._getContainer()
        self._searchIterator = None
        self._currentObject = None
        self._nextObject = None
        self._searchAnchor = None
        self._distanceFromAnchor = None
        if request.pageToken is None:
            self._initialiseIteration()
        else:
            # Set the search start point and the number of records to skip from
            # the page token.
            searchAnchor, objectsToSkip = _parsePageToken(request.pageToken, 2)
            self._pickUpIteration(searchAnchor, objectsToSkip)

    def _initialiseIteration(self):
        """
        Starts a new iteration.
        """
        self._searchIterator = self._search(
            self._request.start, self._request.end)
        self._currentObject = next(self._searchIterator, None)
        if self._currentObject is not None:
            self._nextObject = next(self._searchIterator, None)
            self._searchAnchor = self._request.start
            self._distanceFromAnchor = 0
            firstObjectStart = self._getStart(self._currentObject)
            if firstObjectStart > self._request.start:
                self._searchAnchor = firstObjectStart

    def _pickUpIteration(self, searchAnchor, objectsToSkip):
        """
        Picks up iteration from a previously provided page token. There are two
        different phases here:
        1) We are iterating over the initial set of intervals in which start
        is < the search start coorindate.
        2) We are iterating over the remaining intervals in which start >= to
        the search start coordinate.
        """
        self._searchAnchor = searchAnchor
        self._distanceFromAnchor = objectsToSkip
        self._searchIterator = self._search(searchAnchor, self._request.end)
        obj = next(self._searchIterator)
        if searchAnchor == self._request.start:
            # This is the initial set of intervals, we just skip forward
            # objectsToSkip positions
            for _ in range(objectsToSkip):
                obj = next(self._searchIterator)
        else:
            # Now, we are past this initial set of intervals.
            # First, we need to skip forward over the intervals where
            # start < searchAnchor, as we've seen these already.
            while self._getStart(obj) < searchAnchor:
                obj = next(self._searchIterator)
            # Now, we skip over objectsToSkip objects such that
            # start == searchAnchor
            for _ in range(objectsToSkip):
                assert self._getStart(obj) == searchAnchor
                obj = next(self._searchIterator)
        self._currentObject = obj
        self._nextObject = next(self._searchIterator, None)

    def next(self):
        """
        Returns the next (object, nextPageToken) pair.
        """
        if self._currentObject is None:
            raise StopIteration()
        nextPageToken = None
        if self._nextObject is not None:
            start = self._getStart(self._nextObject)
            # If start > the search anchor, move the search anchor. Otherwise,
            # increment the distance from the anchor.
            if start > self._searchAnchor:
                self._searchAnchor = start
                self._distanceFromAnchor = 0
            else:
                self._distanceFromAnchor += 1
            nextPageToken = "{}:{}".format(
                self._searchAnchor, self._distanceFromAnchor)
        ret = self._currentObject, nextPageToken
        self._currentObject = self._nextObject
        self._nextObject = next(self._searchIterator, None)
        return ret

    def __iter__(self):
        return self


class ReadsIntervalIterator(IntervalIterator):
    """
    An interval iterator for reads
    """
    def _getContainer(self):
        if len(self._request.readGroupIds) != 1:
            if len(self._request.readGroupIds) == 0:
                msg = "Read search requires a readGroup to be specified"
            else:
                msg = "Read search over multiple readGroups not supported"
            raise exceptions.NotImplementedException(msg)
        readGroupId = self._request.readGroupIds[0]
        readGroup = _safeMapQuery(
            self._containerIdMap, readGroupId,
            exceptions.ReadGroupNotFoundException)
        return readGroup

    def _search(self, start, end):
        return self._container.getReadAlignments(
            self._request.referenceId, start, end)

    @classmethod
    def _getStart(cls, readAlignment):
        return readAlignment.alignment.position.position

    @classmethod
    def _getEnd(cls, readAlignment):
        return cls._getStart(readAlignment) + \
            len(readAlignment.alignedSequence)


class VariantsIntervalIterator(IntervalIterator):
    """
    An interval iterator for variants
    """
    def _getContainer(self):
        return _getVariantSet(self._request, self._containerIdMap)

    def _search(self, start, end):
        return self._container.getVariants(
            self._request.referenceName, start, end, self._request.variantName,
            self._request.callSetIds)

    @classmethod
    def _getStart(cls, variant):
        return variant.start

    @classmethod
    def _getEnd(cls, variant):
        return variant.end


class AbstractBackend(object):
    """
    An abstract GA4GH backend.
    This class provides methods for all of the GA4GH protocol end points.
    """
    def __init__(self):
        self._requestValidation = False
        self._responseValidation = False
        self._defaultPageSize = 100
        self._maxResponseLength = 2**20  # 1 MiB
        self._datasetIdMap = {}
        self._datasetIds = []
        self._referenceSetIdMap = {}
        self._referenceSetIds = []

    def addDataset(self, dataset):
        """
        Adds the specified dataset to this backend.
        """
        id_ = dataset.getId()
        self._datasetIdMap[id_] = dataset
        self._datasetIds.append(id_)

    def addReferenceSet(self, referenceSet):
        """
        Adds the specified reference set to this backend.
        """
        id_ = referenceSet.getId()
        self._referenceSetIdMap[id_] = referenceSet
        self._referenceSetIds.append(id_)

    def setRequestValidation(self, requestValidation):
        """
        Set enabling request validation
        """
        self._requestValidation = requestValidation

    def setResponseValidation(self, responseValidation):
        """
        Set enabling response validation
        """
        self._responseValidation = responseValidation

    def setDefaultPageSize(self, defaultPageSize):
        """
        Sets the default page size for request to the specified value.
        """
        self._defaultPageSize = defaultPageSize

    def setMaxResponseLength(self, maxResponseLength):
        """
        Sets the approximate maximum response length to the specified
        value.
        """
        self._maxResponseLength = maxResponseLength

    def getDatasets(self):
        """
        Returns a list of datasets in this backend
        """
        return [self._datasetIdMap[id_] for id_ in self._datasetIds]

    def getDataset(self, datasetId):
        """
        Returns a dataset with id datasetId
        """
        return _safeMapQuery(
            self._datasetIdMap, datasetId,
            exceptions.DatasetNotFoundException)

    def getReferenceSets(self):
        """
        Returns the list of ReferenceSets in this backend
        """
        return [self._referenceSetIdMap[id_] for id_ in self._referenceSetIds]

    def getReferenceSet(self, referenceSetId):
        """
        Retuns the reference set with the speficied ID.
        """
        return _safeMapQuery(
            self._referenceSetIdMap, referenceSetId,
            exceptions.ReferenceSetNotFoundException)

    def startProfile(self):
        """
        Profiling hook. Called at the start of the runSearchRequest method
        and allows for detailed profiling of search performance.
        """
        pass

    def endProfile(self):
        """
        Profiling hook. Called at the end of the runSearchRequest method.
        """
        pass

    def validateRequest(self, jsonDict, requestClass):
        """
        Ensures the jsonDict corresponds to a valid instance of requestClass
        Throws an error if the data is invalid
        """
        if self._requestValidation:
            if not requestClass.validate(jsonDict):
                raise exceptions.RequestValidationFailureException(
                    jsonDict, requestClass)

    def validateResponse(self, jsonString, responseClass):
        """
        Ensures the jsonDict corresponds to a valid instance of responseClass
        Throws an error if the data is invalid
        """
        if self._responseValidation:
            jsonDict = json.loads(jsonString)
            if not responseClass.validate(jsonDict):
                raise exceptions.ResponseValidationFailureException(
                    jsonDict, responseClass)

    ###########################################################
    #
    # Iterators over the data hierarchy. These methods help to
    # implement the search endpoints by providing iterators
    # over the objects to be returned to the client.
    #
    ###########################################################

    def _topLevelObjectGenerator(self, request, idMap, idList):
        """
        Generalisation of the code to iterate over the objects at the top
        of the data hierarchy.
        """
        currentIndex = 0
        if request.pageToken is not None:
            currentIndex, = _parsePageToken(request.pageToken, 1)
        while currentIndex < len(idList):
            objectId = idList[currentIndex]
            object_ = idMap[objectId]
            currentIndex += 1
            nextPageToken = None
            if currentIndex < len(idList):
                nextPageToken = str(currentIndex)
            yield object_.toProtocolElement(), nextPageToken

    def _singleObjectGenerator(self, datamodelObject):
        """
        Returns a generator suitable for a search method in which the
        result set is a single object.
        """
        yield (datamodelObject.toProtocolElement(), None)

    def datasetsGenerator(self, request):
        """
        Returns a generator over the (dataset, nextPageToken) pairs
        defined by the specified request
        """
        return self._topLevelObjectGenerator(
            request, self._datasetIdMap, self._datasetIds)

    def readGroupSetsGenerator(self, request):
        """
        Returns a generator over the (readGroupSet, nextPageToken) pairs
        defined by the specified request.
        """
        dataset = self.getDataset(request.datasetId)
        if request.name is None:
            return self._topLevelObjectGenerator(
                request, dataset.getReadGroupSetIdMap(),
                dataset.getReadGroupSetIds())
        else:
            readGroupSet = dataset.getReadGroupSetByName(request.name)
            return self._singleObjectGenerator(readGroupSet)

    def referenceSetsGenerator(self, request):
        """
        Returns a generator over the (referenceSet, nextPageToken) pairs
        defined by the specified request.
        """
        return self._topLevelObjectGenerator(
            request, self._referenceSetIdMap, self._referenceSetIds)

    def referencesGenerator(self, request):
        """
        Returns a generator over the (reference, nextPageToken) pairs
        defined by the specified request.
        """
        referenceSet = self.getReferenceSet(request.referenceSetId)
        return self._topLevelObjectGenerator(
            request, referenceSet.getReferenceIdMap(),
            referenceSet.getReferenceIds())

    def variantSetsGenerator(self, request):
        """
        Returns a generator over the (variantSet, nextPageToken) pairs defined
        by the specified request.
        """
        dataset = self.getDataset(request.datasetId)
        return self._topLevelObjectGenerator(
            request, dataset.getVariantSetIdMap(),
            dataset.getVariantSetIds())

    def readsGenerator(self, request):
        """
        Returns a generator over the (read, nextPageToken) pairs defined
        by the specified request
        """
        if request.referenceId is None:
            raise exceptions.UnmappedReadsNotSupported()
        if len(request.readGroupIds) != 1:
            raise exceptions.NotImplementedException(
                "Exactly one read group id must be specified")
        compoundId = datamodel.ReadGroupCompoundId.parse(
            request.readGroupIds[0])
        dataset = self.getDataset(compoundId.datasetId)
        readGroupSet = dataset.getReadGroupSet(compoundId.readGroupSetId)
        intervalIterator = ReadsIntervalIterator(
            request, readGroupSet.getReadGroupIdMap())
        return intervalIterator

    def variantsGenerator(self, request):
        """
        Returns a generator over the (variant, nextPageToken) pairs defined
        by the specified request.
        """
        compoundId = datamodel.VariantSetCompoundId.parse(request.variantSetId)
        dataset = self.getDataset(compoundId.datasetId)
        intervalIterator = VariantsIntervalIterator(
            request, dataset.getVariantSetIdMap())
        return intervalIterator

    def callSetsGenerator(self, request):
        """
        Returns a generator over the (callSet, nextPageToken) pairs defined
        by the specified request.
        """
        compoundId = datamodel.VariantSetCompoundId.parse(request.variantSetId)
        dataset = self.getDataset(compoundId.datasetId)
        variantSet = _getVariantSet(
            compoundId, dataset.getVariantSetIdMap())
        if request.name is None:
            return self._topLevelObjectGenerator(
                request, variantSet.getCallSetIdMap(),
                variantSet.getCallSetIds())
        else:
            # Since names are unique within a callSet, we either have one
            # result or we 404.
            callSet = variantSet.getCallSetByName(request.name)
            return self._singleObjectGenerator(callSet)

    ###########################################################
    #
    # Public API methods. Each of these methods implements the
    # corresponding API end point, and return data ready to be
    # written to the wire.
    #
    ###########################################################

    def runGetRequest(self, idMap, id_):
        """
        Runs a get request by indexing into the provided idMap and
        returning a json string of that object
        """
        obj = _safeMapQuery(idMap, id_)
        protocolElement = obj.toProtocolElement()
        jsonString = protocolElement.toJsonString()
        return jsonString

    def runSearchRequest(
            self, requestStr, requestClass, responseClass, objectGenerator):
        """
        Runs the specified request. The request is a string containing
        a JSON representation of an instance of the specified requestClass.
        We return a string representation of an instance of the specified
        responseClass in JSON format. Objects are filled into the page list
        using the specified object generator, which must return
        (object, nextPageToken) pairs, and be able to resume iteration from
        any point using the nextPageToken attribute of the request object.
        """
        self.startProfile()
        try:
            requestDict = json.loads(requestStr)
        except ValueError:
            raise exceptions.InvalidJsonException(requestStr)
        self.validateRequest(requestDict, requestClass)
        request = requestClass.fromJsonDict(requestDict)
        if request.pageSize is None:
            request.pageSize = self._defaultPageSize
        if request.pageSize <= 0:
            raise exceptions.BadPageSizeException(request.pageSize)
        responseBuilder = protocol.SearchResponseBuilder(
            responseClass, request.pageSize, self._maxResponseLength)
        nextPageToken = None
        for obj, nextPageToken in objectGenerator(request):
            responseBuilder.addValue(obj)
            if responseBuilder.isFull():
                break
        responseBuilder.setNextPageToken(nextPageToken)
        responseString = responseBuilder.getJsonString()
        self.validateResponse(responseString, responseClass)
        self.endProfile()
        return responseString

    def runGetCallset(self, id_):
        """
        Returns a callset with the given id
        """
        compoundId = datamodel.CallSetCompoundId.parse(id_)
        dataset = self.getDataset(compoundId.datasetId)
        variantSet = _getVariantSet(
            compoundId, dataset.getVariantSetIdMap())
        return self.runGetRequest(variantSet.getCallSetIdMap(), id_)

    def runListReferenceBases(self, id_, requestArgs):
        """
        Runs a listReferenceBases request for the specified ID and
        request arguments.
        """
        # parse arguments
        compoundId = datamodel.ReferenceCompoundId.parse(id_)
        referenceSet = self.getReferenceSet(compoundId.referenceSetId)
        reference = referenceSet.getReference(id_)
        start = _parseIntegerArgument(requestArgs, 'start', 0)
        end = _parseIntegerArgument(requestArgs, 'end', reference.getLength())
        if 'pageToken' in requestArgs:
            pageTokenStr = requestArgs['pageToken']
            start = _parsePageToken(pageTokenStr, 1)[0]

        chunkSize = self._maxResponseLength
        nextPageToken = None
        if start + chunkSize < end:
            end = start + chunkSize
            nextPageToken = str(start + chunkSize)
        sequence = reference.getBases(start, end)

        # build response
        response = protocol.ListReferenceBasesResponse()
        response.offset = start
        response.sequence = sequence
        response.nextPageToken = nextPageToken
        return response.toJsonString()

    # Get requests.

    def runGetVariant(self, id_):
        """
        Returns a variant with the given id
        """
        compoundId = datamodel.VariantCompoundId.parse(id_)
        dataset = self.getDataset(compoundId.datasetId)
        variantSet = _safeMapQuery(
            dataset.getVariantSetIdMap(), compoundId.variantSetId)
        variant = variantSet.getVariant(compoundId)
        jsonString = variant.toJsonString()
        return jsonString

    def runGetReadGroupSet(self, id_):
        """
        Returns a readGroupSet with the given id_
        """
        compoundId = datamodel.ReadGroupSetCompoundId.parse(id_)
        dataset = self.getDataset(compoundId.datasetId)
        return self.runGetRequest(dataset.getReadGroupSetIdMap(), id_)

    def runGetReadGroup(self, id_):
        """
        Returns a read group with the given id_
        """
        compoundId = datamodel.ReadGroupCompoundId.parse(id_)
        dataset = self.getDataset(compoundId.datasetId)
        readGroupSet = dataset.getReadGroupSet(compoundId.readGroupSetId)
        return self.runGetRequest(readGroupSet.getReadGroupIdMap(), id_)

    def runGetReference(self, id_):
        """
        Runs a getReference request for the specified ID.
        """
        compoundId = datamodel.ReferenceCompoundId.parse(id_)
        referenceSet = self.getReferenceSet(compoundId.referenceSetId)
        return self.runGetRequest(referenceSet.getReferenceIdMap(), id_)

    def runGetReferenceSet(self, id_):
        """
        Runs a getReferenceSet request for the specified ID.
        """
        return self.runGetRequest(self._referenceSetIdMap, id_)

    def runGetVariantSet(self, id_):
        """
        Runs a getVariantSet request for the specified ID.
        """
        compoundId = datamodel.VariantSetCompoundId.parse(id_)
        dataset = self.getDataset(compoundId.datasetId)
        return self.runGetRequest(dataset.getVariantSetIdMap(), id_)

    # Search requests.

    def runSearchReadGroupSets(self, request):
        """
        Runs the specified SearchReadGroupSetsRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchReadGroupSetsRequest,
            protocol.SearchReadGroupSetsResponse,
            self.readGroupSetsGenerator)

    def runSearchReads(self, request):
        """
        Runs the specified SearchReadsRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchReadsRequest,
            protocol.SearchReadsResponse,
            self.readsGenerator)

    def runSearchReferenceSets(self, request):
        """
        Runs the specified SearchReferenceSetsRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchReferenceSetsRequest,
            protocol.SearchReferenceSetsResponse,
            self.referenceSetsGenerator)

    def runSearchReferences(self, request):
        """
        Runs the specified SearchReferenceRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchReferencesRequest,
            protocol.SearchReferencesResponse,
            self.referencesGenerator)

    def runSearchVariantSets(self, request):
        """
        Runs the specified SearchVariantSetsRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchVariantSetsRequest,
            protocol.SearchVariantSetsResponse,
            self.variantSetsGenerator)

    def runSearchVariants(self, request):
        """
        Runs the specified SearchVariantRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchVariantsRequest,
            protocol.SearchVariantsResponse,
            self.variantsGenerator)

    def runSearchCallSets(self, request):
        """
        Runs the specified SearchCallSetsRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchCallSetsRequest,
            protocol.SearchCallSetsResponse,
            self.callSetsGenerator)

    def runSearchDatasets(self, request):
        """
        Runs the specified SearchDatasetsRequest.
        """
        return self.runSearchRequest(
            request, protocol.SearchDatasetsRequest,
            protocol.SearchDatasetsResponse,
            self.datasetsGenerator)


class EmptyBackend(AbstractBackend):
    """
    A GA4GH backend that contains no data.
    """


class SimulatedBackend(AbstractBackend):
    """
    A GA4GH backend backed by no data; used mostly for testing
    """
    def __init__(
            self, randomSeed=0, numDatasets=2,
            numVariantSets=1, numCalls=1, variantDensity=0.5,
            numReferenceSets=1, numReferencesPerReferenceSet=1,
            numReadGroupSets=1, numReadGroupsPerReadGroupSet=1,
            numAlignments=2):
        super(SimulatedBackend, self).__init__()

        # Datasets
        for i in range(numDatasets):
            seed = randomSeed + i
            localId = "simulatedDataset{}".format(i)
            dataset = datasets.SimulatedDataset(
                localId, randomSeed=seed, numCalls=numCalls,
                variantDensity=variantDensity, numVariantSets=numVariantSets,
                numReadGroupSets=numReadGroupSets,
                numReadGroupsPerReadGroupSet=numReadGroupsPerReadGroupSet,
                numAlignments=numAlignments)
            self.addDataset(dataset)
        # References
        for i in range(numReferenceSets):
            localId = "referenceSet{}".format(i)
            seed = randomSeed + i
            referenceSet = references.SimulatedReferenceSet(
                localId, seed, numReferencesPerReferenceSet)
            self.addReferenceSet(referenceSet)


class FileSystemBackend(AbstractBackend):
    """
    A GA4GH backend backed by data on the file system
    """
    def __init__(self, dataDir):
        super(FileSystemBackend, self).__init__()
        self._dataDir = dataDir
        # TODO this code is very ugly and should be regarded as a temporary
        # stop-gap until we deal with iterating over the data tree properly.

        # References
        referencesDirName = "references"
        referenceSetDir = os.path.join(self._dataDir, referencesDirName)
        for referenceSetName in os.listdir(referenceSetDir):
            relativePath = os.path.join(referenceSetDir, referenceSetName)
            if os.path.isdir(relativePath):
                referenceSet = references.HtslibReferenceSet(
                    referenceSetName, relativePath)
                self.addReferenceSet(referenceSet)
        # Datasets
        datasetDirs = [
            os.path.join(self._dataDir, directory)
            for directory in os.listdir(self._dataDir)
            if os.path.isdir(os.path.join(self._dataDir, directory)) and
            directory != referencesDirName]
        for datasetDir in datasetDirs:
            dataset = datasets.FileSystemDataset(datasetDir)
            self.addDataset(dataset)
