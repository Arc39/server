"""
    Script to parse the output file produced by cufflinks.
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
import sqlite3
import argparse


class RNASqliteStore(object):
    """
    Defines a sqlite store for RNA data as well as methods for loading the
    tables.
    """
    def __init__(self, sqliteFileName):
        # TODO: check to see if the rnaQuantId is in the db and exit if it is
        # since this is a generator and not an updater
        sqlFilePath = sqliteFileName
        print(sqlFilePath)
        self._dbConn = sqlite3.connect(sqlFilePath)
        self._cursor = self._dbConn.cursor()
        self.createTables(self._cursor)
        self._dbConn.commit()

        self._batchSize = 100
        self._rnaValueList = []
        self._expressionValueList = []

    def createTables(self, cursor):
        # annotationIds is a comma separated list
        cursor.execute('''CREATE TABLE RNAQUANTIFICATION (
                       id text,
                       annotation_ids text,
                       description text,
                       name text,
                       read_group_id text)''')
        cursor.execute('''CREATE TABLE EXPRESSION (
                       id text,
                       name text,
                       rna_quantification_id text,
                       annotation_id text,
                       expression real,
                       quantification_group_id text,
                       is_normalized boolean,
                       raw_read_count real,
                       score real,
                       units text,
                       conf_low real,
                       conf_hi real)''')

    def addRNAQuantification(self, datafields):
        """
        Adds an RNAQuantification to the db.  Datafields is a tuple in the
        order:
        id, annotation_ids, description, name, read_group_id
        """
        self._rnaValueList.append(datafields)
        if len(self._rnaValueList) >= self._batchSize:
            self.batchAddRNAQuantification()

    def batchAddRNAQuantification(self):
        if len(self._rnaValueList) > 0:
            sql = "INSERT INTO RNAQUANTIFICATION VALUES (?,?,?,?,?)"
            self._cursor.executemany(sql, self._rnaValueList)
            self._dbConn.commit()
            self._rnaValueList = []

    def addExpression(self, datafields):
        """
        Adds an Expression to the db.  Datafields is a tuple in the order:
        id, name, rna_quantification_id, annotation_id, expression,
        quantification_group_id, is_normalized, raw_read_count, score, units
        """
        self._expressionValueList.append(datafields)
        if len(self._expressionValueList) >= self._batchSize:
            self.batchAddExpression()

    def batchAddExpression(self):
        if len(self._expressionValueList) > 0:
            sql = "INSERT INTO EXPRESSION VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            self._cursor.executemany(sql, self._expressionValueList)
            self._dbConn.commit()
            self._expressionValueList = []


class AbstractWriter(object):
    """
    Base class to use for the rna quantification writers
    """
    def __init__(self, annotationId, rnaDB):
        self._annotationId = annotationId
        self._db = rnaDB
        self._isNormalized = None
        self._units = ""
        self._expressionLevelCol = None
        self._idCol = None
        self._nameCol = None
        self._featureCol = None
        self._countCol = None
        self._confColLow = None
        self._confColHi = None

    def writeExpression(self, analysisId, quantfile):
        """
        Reads the quantification results file and adds entries to the
        specified database.
        """
        isNormalized = self._isNormalized
        units = self._units
        # strip header and print - log it instead?
        print(quantfile.readline())
        for expression in quantfile:
            fields = expression.strip().split("\t")
            expressionLevel = fields[self._expressionLevelCol]
            expressionId = fields[self._idCol]
            name = fields[self._nameCol]
            quantificationGroupId = fields[self._featureCol]
            rawCount = 0.0
            if self._countCol is not None:
                rawCount = fields[self._countCol]
            confidenceLow = 0.0
            confidenceHi = 0.0
            score = 0.0
            if (self._confColLow is not None and self._confColHi is not None):
                confidenceLow = float(fields[self._confColLow])
                confidenceHi = float(fields[self._confColHi])
                score = (confidenceLow + confidenceHi)/2

            datafields = (expressionId, name, analysisId,
                          self._annotationId, expressionLevel,
                          quantificationGroupId, isNormalized, rawCount,
                          str(score), units, confidenceLow, confidenceHi)
            self._db.addExpression(datafields)
        self._db.batchAddExpression()


class CufflinksWriter(AbstractWriter):
    """
    Class to parse and write expression data from an input file generated by
    Cufflinks.

    cufflinks header:
        tracking_id    class_code    nearest_ref_id    gene_id
        gene_short_name    tss_id    locus    length    coverage    FPKM
        FPKM_conf_lo    FPKM_conf_hi    FPKM_status
    """
    def __init__(self, annotationId, rnaDB):
        super(CufflinksWriter, self).__init__(annotationId, rnaDB)
        self._isNormalized = True
        self._units = "FPKM"
        self._expressionLevelCol = 9
        self._idCol = 0
        self._nameCol = 4
        self._featureCol = 3
        self._confColLow = 10
        self._confColHi = 11


class RsemWriter(AbstractWriter):
    """
    Class to parse and write expression data from an input file generated by
    RSEM.

    RSEM header:
    gene_id transcript_id(s)    length  effective_length    expected_count
    TPM FPKM    pme_expected_count  pme_TPM pme_FPKM    TPM_ci_lower_bound
    TPM_ci_upper_bound  FPKM_ci_lower_bound FPKM_ci_upper_bound
    """
    def __init__(self, annotationId, rnaDB, featureType="gene"):
        super(RsemWriter, self).__init__(annotationId, rnaDB)
        self._isNormalized = True
        self._units = "TPM"
        self._expressionLevelCol = 5
        if featureType is "transcript":
            self._idCol = 1
        else:
            self._idCol = 0
        self._nameCol = self._idCol
        self._featureCol = 0
        self._countCol = 4
        self._confColLow = 10
        self._confColHi = 11


class KallistoWriter(AbstractWriter):
    """
    Class to parse and write expression data from an input file generated by
    RSEM.

    kallisto header:
        target_id    length    eff_length    est_counts    tpm
    """
    def __init__(self, annotationId, rnaDB):
        super(KallistoWriter, self).__init__(annotationId, rnaDB)
        self._isNormalized = True
        self._units = "TPM"
        self._expressionLevelCol = 4
        self._idCol = 0
        self._nameCol = 0
        self._featureCol = 0
        self._countCol = 3


def writeRnaseqTable(rnaDB, analysisIds, description, annotationId,
                     readGroupId=None):
    if readGroupId is None:
        readGroupId = ""
    for analysisId in analysisIds:
        datafields = (analysisId, annotationId, description, analysisId,
                      readGroupId)
        rnaDB.addRNAQuantification(datafields)
    rnaDB.batchAddRNAQuantification()


def writeExpressionTable(writer, data):
    for analysisId, quantfile in data:
        print("processing {}".format(analysisId))
        writer.writeExpression(analysisId, quantfile)


def rnaseq2ga(dataFolder, controlFile, sqlFilename):
    """
    Reads RNA Quantification data in one of several formats and stores the data
    in a sqlite database for use by the GA4GH reference server.

    Quantifications are specified in a tab delimited control file with columns:
    rna_quant_id    filename        type    annotation_id   read_group_id
    description

    Supports the following quantification output type:
    Cufflinks, kallisto, RSEM
    """

    rnaDB = RNASqliteStore(sqlFilename)
    with open(controlFile, "r") as rnaDatasetsFile:
        print(rnaDatasetsFile.readline())
        for line in rnaDatasetsFile:
            fields = line.split("\t")
            rnaType = fields[2]
            annotationId = fields[3].strip()
            if rnaType == "cufflinks":
                writer = CufflinksWriter(annotationId, rnaDB)
            elif rnaType == "kallisto":
                writer = KallistoWriter(annotationId, rnaDB)
            elif rnaType == "rsem":
                writer = RsemWriter(annotationId, rnaDB)
            else:
                print("Unknown RNA file type: {}".format(rnaType))
                sys.exit(1)
            rnaQuantId = fields[0].strip()
            quantFilename = os.path.join(dataFolder, fields[1].strip())
            readGroupId = fields[4].strip()
            description = fields[5].strip()
            writeRnaseqTable(rnaDB, [rnaQuantId], description,
                             annotationId,
                             readGroupId=readGroupId)
            quantFile = open(quantFilename, "r")
            writeExpressionTable(writer, [(rnaQuantId, quantFile)])

    print("DONE")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Script to generate SQLite database corresponding to "
        "input RNA Quantification experiment files.")
    parser.add_argument(
        "--outputFile", "-o", default="rnaseq.db",
        help="The file to output the server-ready database to.")
    parser.add_argument(
        "--inputDir", "-i",
        help="Path to input directory containing RNA quant files.",
        default='.')
    parser.add_argument(
        "--controlFile", "-c",
        help="Name of control file (.tsv format) in the inputDir",
        default="rna_control_file.tsv")
    parser.add_argument('--verbose', '-v', action='count', default=0)
    args = parser.parse_args()
    controlFilePath = os.path.join(args.inputDir, args.controlFile)

    rnaseq2ga(args.inputDir, controlFilePath, args.outputFile)
