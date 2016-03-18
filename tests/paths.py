"""
Centralizes hardcoded paths, names, etc. used in tests
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os


testDir = 'tests'
testDataDir = os.path.join(testDir, 'data')

testBioSamplesDataDir = os.path.join(testDir, 'faultydata/biodata/biosamples')

# references
referenceSetName = 'chr17'
faPath = os.path.join(testDataDir, 'referenceSets/Default/chr17.fa.gz')
faPath2 = os.path.join(testDataDir, 'referenceSets/example_1/simple.fa.gz')
faPath3 = os.path.join(testDataDir, 'referenceSets/example_2/random1.fa.gz')

# variants
variantSetName = '1kgPhase1'
vcfDirPath = os.path.join(
    testDataDir, 'datasets/dataset1/variants/1kgPhase1')
vcfDirPath2 = os.path.join(
    testDataDir, 'datasets/dataset1/variants/1kgPhase3')
bioSamplesDir = os.path.join(
    testDataDir, 'datasets/dataset1/biodata/biosamples')
bioSamplePath = os.path.join(bioSamplesDir, 'HG00096.json')
malformedBioSamplePath = os.path.join(testBioSamplesDataDir, 'malformed.json')
bioSampleName = "HG00096"

# reads
readGroupSetName = 'chr17.1-250'
bamPath = os.path.join(
    testDataDir, 'datasets/dataset1/reads/chr17.1-250.bam')
bamPath2 = os.path.join(
    testDataDir,
    'datasets/dataset1/reads/'
    'wgEncodeUwRepliSeqBg02esG1bAlnRep1_sample.bam')
