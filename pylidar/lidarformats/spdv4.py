
"""
SPD V4 format driver and support functions
"""
# This file is part of PyLidar
# Copyright (C) 2015 John Armston, Pete Bunting, Neil Flood, Sam Gillingham
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import print_function, division

import sys
import copy
import numpy
import h5py
from numba import jit
from rios import pixelgrid
from . import generic
from . import gridindexutils
from . import h5space

# Header fields have defined type in SPDV4
HEADER_FIELDS = {'AZIMUTH_MAX' : numpy.float64, 'AZIMUTH_MIN' : numpy.float64,
'BANDWIDTHS' : numpy.float32, 'BIN_SIZE' : numpy.float32,
'BLOCK_SIZE_POINT' : numpy.uint16, 'BLOCK_SIZE_PULSE' : numpy.uint16,
'BLOCK_SIZE_WAVEFORM' : numpy.uint16,
'BLOCK_SIZE_RECEIVED' : numpy.uint16, 'BLOCK_SIZE_TRANSMITTED' : numpy.uint16,
'CAPTURE_DATETIME' : bytes, 'CREATION_DATETIME' : bytes,
'FIELD_OF_VIEW' : numpy.float32,
'GENERATING_SOFTWARE' : bytes, 'INDEX_TYPE' : numpy.uint16,
'INDEX_TLX' : numpy.float64, 'INDEX_TLY' : numpy.float64,
'NUMBER_BINS_X' : numpy.uint32, 'NUMBER_BINS_Y' : numpy.uint32,
'NUMBER_OF_POINTS' : numpy.uint64, 'NUMBER_OF_PULSES' : numpy.uint64,
'NUMBER_OF_WAVEFORMS' : numpy.uint16,
'NUM_OF_WAVELENGTHS' : numpy.uint16, 'POINT_DENSITY' : numpy.float32,
'PULSE_ALONG_TRACK_SPACING' : numpy.float32, 
'PULSE_ANGULAR_SPACING_SCANLINE' : numpy.float32,
'PULSE_ANGULAR_SPACING_SCANLINE_IDX' : numpy.float32,
'PULSE_CROSS_TRACK_SPACING' : numpy.float32, 'PULSE_DENSITY' : numpy.float32,
'PULSE_ENERGY' : numpy.float32, 'PULSE_FOOTPRINT' : numpy.float32,
'PULSE_INDEX_METHOD' : numpy.uint16, 'RANGE_MAX' : numpy.float32,
'RANGE_MIN' : numpy.float32, 
'SCANLINE_IDX_MAX' : numpy.uint32, 'SCANLINE_IDX_MIN' : numpy.uint32,
'SCANLINE_MAX' : numpy.uint16, 'SCANLINE_MIN' : numpy.uint16,
'SENSOR_APERTURE_SIZE' : numpy.float32, 'SENSOR_BEAM_DIVERGENCE' : numpy.float32,
'SENSOR_HEIGHT' : numpy.float32, 'SENSOR_MAX_SCAN_ANGLE' : numpy.float32,
'SENSOR_PULSE_REPETITION_FREQ' : numpy.float32,
'SENSOR_SCAN_RATE' : numpy.float32, 'SENSOR_SPEED' : numpy.float32,
'SENSOR_TEMPORAL_BIN_SPACING' : numpy.float64, 
'SENSOR_BEAM_EXIT_DIAMETER' : numpy.float32,
'SPATIAL_REFERENCE' : bytes,
'SYSTEM_IDENTIFIER' : bytes, 'USER_META_DATA' : bytes,
'VERSION_SPD' : numpy.uint8, 'VERSION_DATA' : numpy.uint8, 
'WAVEFORM_BIT_RES' : numpy.uint16, 'WAVELENGTHS' : numpy.float32,
'X_MAX' : numpy.float64, 'X_MIN' : numpy.float64, 'Y_MAX' : numpy.float64,
'Y_MIN' : numpy.float64, 'Z_MAX' : numpy.float64, 'Z_MIN' : numpy.float64,
'HEIGHT_MIN' : numpy.float32, 'HEIGHT_MAX' : numpy.float32, 
'ZENITH_MAX' : numpy.float64, 'ZENITH_MIN' : numpy.float64,
'RGB_FIELD' : bytes}

HEADER_ARRAY_FIELDS = ('BANDWIDTHS', 'WAVELENGTHS', 'VERSION_SPD', 'VERSION_DATA', 'RGB_FIELD')

# Note: PULSE_ID, NUMBER_OF_RETURNS and PTS_START_IDX always created by pylidar
PULSES_ESSENTIAL_FIELDS = ('X_IDX', 'Y_IDX')
# RETURN_NUMBER always created by pylidar
POINTS_ESSENTIAL_FIELDS = ('X', 'Y', 'Z', 'CLASSIFICATION')
# VERSION_SPD always created by pylidar
HEADER_ESSENTIAL_FIELDS = ('SPATIAL_REFERENCE', 'VERSION_DATA')

# The following fields have defined type
PULSE_FIELDS = {'PULSE_ID' : numpy.uint64, 'TIMESTAMP' : numpy.uint64,
'NUMBER_OF_RETURNS' : numpy.uint8, 'AZIMUTH' : numpy.uint32, 
'ZENITH' : numpy.uint32, 'SOURCE_ID' : numpy.uint16, 
'PULSE_WAVELENGTH_IDX' : numpy.uint8, 'NUMBER_OF_WAVEFORM_SAMPLES' : numpy.uint8,
'WFM_START_IDX' : numpy.uint64, 'PTS_START_IDX' : numpy.uint64, 
'SCANLINE' : numpy.uint32, 'SCANLINE_IDX' : numpy.uint16, 'X_IDX' : numpy.uint32,
'Y_IDX' : numpy.uint32, 'X_ORIGIN' : numpy.uint32, 'Y_ORIGIN' : numpy.uint32,
'Z_ORIGIN' : numpy.uint32, 'H_ORIGIN' : numpy.uint32, 'PULSE_FLAGS' : numpy.uint8,
'AMPLITUDE_PULSE' : numpy.uint16, 'WIDTH_PULSE' : numpy.uint16, 
'SCAN_ANGLE_RANK' : numpy.int16, 'PRISM_FACET' : numpy.uint8}

# The following fields have defined type
POINT_FIELDS = {'RANGE' : numpy.uint32, 'RETURN_NUMBER' : numpy.uint8,
'X' : numpy.uint32, 'Y' : numpy.uint32, 'Z' : numpy.uint32, 
'HEIGHT' : numpy.uint16, 'CLASSIFICATION' : numpy.uint8, 
'POINT_FLAGS' : numpy.uint8, 'INTENSITY' : numpy.uint16, 
'AMPLITUDE_RETURN' : numpy.uint16, 'WIDTH_RETURN' : numpy.uint16, 
'RED' : numpy.uint16, 'GREEN' : numpy.uint16, 'BLUE' : numpy.uint16, 
'NIR' : numpy.uint16, 'RHO_APP' : numpy.uint16, 'DEVIATION' : numpy.uint16,
'ECHO_TYPE' : numpy.uint16, 'POINT_WAVELENGTH_IDX' : numpy.uint8}

# The following fields have defined type
WAVEFORM_FIELDS = {'NUMBER_OF_WAVEFORM_RECEIVED_BINS' : numpy.uint16,
'NUMBER_OF_WAVEFORM_TRANSMITTED_BINS' : numpy.uint16, 
'RANGE_TO_WAVEFORM_START' : numpy.uint16, 'RECEIVED_START_IDX' : numpy.uint64,
'TRANSMITTED_START_IDX' : numpy.uint64, 'CHANNEL' : numpy.uint8,
'WAVEFORM_FLAGS' : numpy.uint8, 'WFM_WAVELENGTH_IDX' : numpy.uint8, 
'RECEIVE_WAVE_GAIN' : numpy.float32, 'RECEIVE_WAVE_OFFSET' :  numpy.float32,
'TRANS_WAVE_GAIN' : numpy.float32, 'TRANS_WAVE_OFFSET' : numpy.float32}

# need scaling applied 
PULSE_SCALED_FIELDS = ('AZIMUTH', 'ZENITH', 'X_IDX', 'Y_IDX', 
'X_ORIGIN', 'Y_ORIGIN', 'Z_ORIGIN', 'H_ORIGIN')
POINT_SCALED_FIELDS = ('X', 'Y', 'Z', 'HEIGHT', 'RANGE')
WAVEFORM_SCALED_FIELDS = ('RANGE_TO_WAVEFORM_START',)


TRANSMITTED_DTYPE = numpy.uint32
RECEIVED_DTYPE = numpy.uint32

GAIN_NAME = 'GAIN'
OFFSET_NAME = 'OFFSET'

# types of indexing in the file
SPDV4_INDEX_CARTESIAN = 1
SPDV4_INDEX_SPHERICAL = 2
SPDV4_INDEX_CYLINDRICAL = 3
SPDV4_INDEX_POLAR = 4
SPDV4_INDEX_SCAN = 5

# pulse indexing methods
SPDV4_PULSE_INDEX_FIRST_RETURN = 0
SPDV4_PULSE_INDEX_LAST_RETURN = 1
SPDV4_PULSE_INDEX_START_WAVEFORM = 2
SPDV4_PULSE_INDEX_END_WAVEFORM = 3
SPDV4_PULSE_INDEX_ORIGIN = 4
SPDV4_PULSE_INDEX_MAX_INTENSITY = 5
SPDV4_PULSE_INDEX_GROUND = 6 # Reserved
SPDV4_PULSE_INDEX_ZPLANE = 7 # Reserved

# types of spatial indices
SPDV4_INDEXTYPE_SIMPLEGRID = 0
# types for the spatial index
SPDV4_SIMPLEGRID_COUNT_DTYPE = numpy.uint32
SPDV4_SIMPLEGRID_INDEX_DTYPE = numpy.uint64

# flags for POINT_FLAGS
SPDV4_POINT_FLAGS_IGNORE = 1
SPDV4_POINT_FLAGS_OVERLAP = 2
SPDV4_POINT_FLAGS_SYNTHETIC = 4
SPDV4_POINT_FLAGS_KEY_POINT = 8
SPDV4_POINT_FLAGS_WAVEFORM = 16

# flags for PULSE_FLAGS
SPDV4_PULSE_FLAGS_IGNORE = 1
SPDV4_PULSE_FLAGS_OVERLAP = 2
SPDV4_PULSE_FLAGS_SCANLINE_DIRECTION = 4
SPDV4_PULSE_FLAGS_SCANLINE_EDGE = 8

# flags for WAVEFORM_FLAGS
SPDV4_WAVEFORM_FLAGS_IGNORE = 1
SPDV4_WAVEFORM_FLAGS_SATURATION_FIXED = 2
SPDV4_WAVEFORM_FLAGS_BASELINE_FIXED = 4

# version
SPDV4_VERSION_MAJOR = 4
SPDV4_VERSION_MINOR = 0

@jit
def flatten3dWaveformData(wavedata, inmask, nrecv, flattened):
    """
    Helper routine that flattens transmitted or received (from another driver)
    into something that can be written. 
    wavedata is either the (3d) transmitted or received
    inmask is the .mask for wavedata
    nrecv is the output array for waveformInfo's NUMBER_OF_WAVEFORM_RECEIVED_BINS etc
    flattened is the flattened version of wavedata
    """
    nbins = wavedata.shape[0]
    nwaves = wavedata.shape[1]
    npulses = wavedata.shape[2]
    nrecv_idx = 0
    flat_idx = 0
    for p in range(npulses):
        for w in range(nwaves):
            c = 0
            for b in range(nbins):
                if not inmask[b, w, p]:
                    c += 1
                    flattened[flat_idx] = wavedata[b, w, p]
                    flat_idx += 1
            if c > 0:
                nrecv[nrecv_idx] = c
                nrecv_idx += 1
    

class SPDV4SpatialIndex(object):
    """
    Class that hides the details of different Spatial Indices
    that can be contained in the SPDV4 file.
    """
    def __init__(self, fileHandle, mode):
        self.fileHandle = fileHandle
        self.mode = mode
        
        # read the pixelgrid info out of the header
        # this is same for all spatial indices on SPD V4
        fileAttrs = fileHandle.attrs
        binSize = fileAttrs['BIN_SIZE']
        shape = fileAttrs['NUMBER_BINS_Y'], fileAttrs['NUMBER_BINS_X']
        xMin = fileAttrs['INDEX_TLX']
        yMax = fileAttrs['INDEX_TLY']
        xMax = xMin + (shape[1] * binSize)
        yMin = yMax - (shape[0] * binSize)
        wkt = fileAttrs['SPATIAL_REFERENCE']
        if sys.version_info[0] == 3 and isinstance(wkt, bytes):
            wkt = wkt.decode()

        if shape[0] != 0 or shape[1] != 0:        
            self.pixelGrid = pixelgrid.PixelGridDefn(projection=wkt, xMin=xMin,
                xMax=xMax, yMin=yMin, yMax=yMax, xRes=binSize, yRes=binSize)
        else:
            self.pixelGrid = None
                
    def close(self):
        """
        Call to write data, close files etc
        """
        # update the header
        if self.mode == generic.CREATE and self.pixelGrid is not None:
            fileAttrs = self.fileHandle.attrs
            fileAttrs['BIN_SIZE'] = self.pixelGrid.xRes
            nrows, ncols = self.pixelGrid.getDimensions()
            fileAttrs['NUMBER_BINS_Y'] = nrows
            fileAttrs['NUMBER_BINS_X'] = ncols
            fileAttrs['INDEX_TLX'] = self.pixelGrid.xMin
            fileAttrs['INDEX_TLY'] = self.pixelGrid.yMax
            fileAttrs['SPATIAL_REFERENCE'] = self.pixelGrid.projection
        
        self.fileHandle = None
        
    def getPulsesSpaceForExtent(self, extent, overlap):
        raise NotImplementedError()

    def getPointsSpaceForExtent(self, extent, overlap):
        raise NotImplementedError()
        
    def createNewIndex(self, pixelGrid):
        raise NotImplementedError()
        
    def setPulsesForExtent(self, extent, pulses, lastPulseID):
        raise NotImplementedError()
        
    @staticmethod
    def getHandlerForFile(fileHandle, mode, prefType=SPDV4_INDEXTYPE_SIMPLEGRID):
        """
        Returns the 'most appropriate' spatial
        index handler for the given file.
        
        prefType contains the user's preferred spatial index.
        If it is not defined for a file another type will be chosen
        
        None is returned if no spatial index is available and mode == READ
        
        If mode != READ and the prefType spatial index type not available 
        it will be created.
        """
        handler = None
        if prefType == SPDV4_INDEXTYPE_SIMPLEGRID:
            cls = SPDV4SimpleGridSpatialIndex
            
        # TODO: other types here
        
        # now try and create the instance
        try:
            handler = cls(fileHandle, mode)
        except generic.LiDARSpatialIndexNotAvailable:
            # TODO: code to try other indices if READ
            pass
            
        return handler
        
SPATIALINDEX_GROUP = 'SPATIALINDEX'
SIMPLEPULSEGRID_GROUP = 'SIMPLEPULSEGRID'
        
class SPDV4SimpleGridSpatialIndex(SPDV4SpatialIndex):
    """
    Implementation of a simple grid index, which is currently
    the only type used in SPD V4 files.
    """
    def __init__(self, fileHandle, mode):
        SPDV4SpatialIndex.__init__(self, fileHandle, mode)
        self.si_cnt = None
        self.si_idx = None
        self.si_xPulseColName = 'X_IDX'
        self.si_yPulseColName = 'Y_IDX'
        # for caching
        self.lastExtent = None
        self.lastPulseSpace = None
        self.lastPulseIdx = None
        self.lastPulseIdxMask = None
        
        if mode == generic.READ or mode == generic.UPDATE:
            # read it in if it exists.
            group = None
            if SPATIALINDEX_GROUP in fileHandle:
                group = fileHandle[SPATIALINDEX_GROUP]
            if group is not None and SIMPLEPULSEGRID_GROUP in group:
                group = group[SIMPLEPULSEGRID_GROUP]
            
            if group is None:
                raise generic.LiDARSpatialIndexNotAvailable()
            else:
                self.si_cnt = group['PLS_PER_BIN'][...]
                self.si_idx = group['BIN_OFFSETS'][...]
                    
                # define the pulse data columns to use for the spatial index
                if self.fileHandle.attrs['INDEX_TYPE'] == SPDV4_INDEX_CARTESIAN:
                    self.si_xPulseColName = 'X_IDX'
                    self.si_yPulseColName = 'Y_IDX'
                elif self.fileHandle.attrs['INDEX_TYPE'] == SPDV4_INDEX_SPHERICAL:
                    self.si_xPulseColName = 'AZIMUTH'
                    self.si_yPulseColName = 'ZENITH'
                elif self.fileHandle.attrs['INDEX_TYPE'] == SPDV4_INDEX_SCAN:
                    self.si_xPulseColName = 'SCANLINE_IDX'
                    self.si_yPulseColName = 'SCANLINE'
                else:
                    msg = 'Unsupported index type %d' % self.fileHandle.attrs['INDEX_TYPE']
                    raise generic.LiDARInvalidSetting(msg)                    
                
    def close(self):
        if self.mode == generic.CREATE and self.si_cnt is not None:
            # create it if it does not exist
            if SPATIALINDEX_GROUP not in self.fileHandle:
                group = self.fileHandle.create_group(SPATIALINDEX_GROUP)
            else:
                group = self.fileHandle[SPATIALINDEX_GROUP]
                
            if SIMPLEPULSEGRID_GROUP not in group:
                group = group.create_group(SIMPLEPULSEGRID_GROUP)
            else:
                group = group[SIMPLEPULSEGRID_GROUP]
                
            nrows, ncols = self.pixelGrid.getDimensions()
            # params adapted from SPDLib
            countDataset = group.create_dataset('PLS_PER_BIN', 
                    (nrows, ncols), 
                    chunks=(1, ncols), dtype=SPDV4_SIMPLEGRID_COUNT_DTYPE,
                    shuffle=True, compression="gzip", compression_opts=1)
            if self.si_cnt is not None:
                countDataset[...] = self.si_cnt
                    
            offsetDataset = group.create_dataset('BIN_OFFSETS', 
                    (nrows, ncols), 
                    chunks=(1, ncols), dtype=SPDV4_SIMPLEGRID_INDEX_DTYPE,
                    shuffle=True, compression="gzip", compression_opts=1)
            if self.si_idx is not None:
                offsetDataset[...] = self.si_idx
                    
        SPDV4SpatialIndex.close(self)
        
    def getSISubset(self, extent, overlap):
        """
        Internal method. Reads the required block out of the spatial
        index for the requested extent.
        """
        # snap the extent to the grid of the spatial index
        pixGrid = self.pixelGrid
        xMin = pixGrid.snapToGrid(extent.xMin, pixGrid.xMin, pixGrid.xRes)
        xMax = pixGrid.snapToGrid(extent.xMax, pixGrid.xMax, pixGrid.xRes)
        yMin = pixGrid.snapToGrid(extent.yMin, pixGrid.yMin, pixGrid.yRes)
        yMax = pixGrid.snapToGrid(extent.yMax, pixGrid.yMax, pixGrid.yRes)

        # size of spatial index we need to read
        nrows = int(numpy.ceil((yMax - yMin) / self.pixelGrid.yRes))
        ncols = int(numpy.ceil((xMax - xMin) / self.pixelGrid.xRes))
        # add overlap 
        nrows += (overlap * 2)
        ncols += (overlap * 2)

        # create subset of spatial index to read data into
        cnt_subset = numpy.zeros((nrows, ncols), dtype=SPDV4_SIMPLEGRID_COUNT_DTYPE)
        idx_subset = numpy.zeros((nrows, ncols), dtype=SPDV4_SIMPLEGRID_INDEX_DTYPE)
        
        imageSlice, siSlice = gridindexutils.getSlicesForExtent(pixGrid, 
             self.si_cnt.shape, overlap, xMin, xMax, yMin, yMax)
             
        if imageSlice is not None and siSlice is not None:

            cnt_subset[imageSlice] = self.si_cnt[siSlice]
            idx_subset[imageSlice] = self.si_idx[siSlice]

        return idx_subset, cnt_subset

    def getPulsesSpaceForExtent(self, extent, overlap):
        """
        Get the space and indexed for pulses of the given extent.
        """
        # return cache
        if self.lastExtent is not None and self.lastExtent == extent:
            return self.lastPulseSpace, self.lastPulseIdx, self.lastPulseIdxMask
        
        idx_subset, cnt_subset = self.getSISubset(extent, overlap)
        nOut = self.fileHandle['DATA']['PULSES']['PULSE_ID'].shape[0]
        pulse_space, pulse_idx, pulse_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                idx_subset, cnt_subset, nOut)
                
        self.lastPulseSpace = pulse_space
        self.lastPulseIdx = pulse_idx
        self.lastPulseIdxMask = pulse_idx_mask
        self.lastExtent = copy.copy(extent)
                
        return pulse_space, pulse_idx, pulse_idx_mask

    def getPointsSpaceForExtent(self, extent, overlap):
        """
        Get the space and indexed for points of the given extent.
        """
        # TODO: cache
    
        # should return cached if exists
        pulse_space, pulse_idx, pulse_idx_mask = self.getPulsesSpaceForExtent(
                                    extent, overlap)
        
        pulsesHandle = self.fileHandle['DATA']['PULSES']
        nReturns = pulse_space.read(pulsesHandle['NUMBER_OF_RETURNS'])
        startIdxs = pulse_space.read(pulsesHandle['PTS_START_IDX'])

        nOut = self.fileHandle['DATA']['POINTS']['RETURN_NUMBER'].shape[0]
        point_space, point_idx, point_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                        startIdxs, nReturns, nOut)

        return point_space, point_idx, point_idx_mask

    def createNewIndex(self, pixelGrid):
        """
        Create a new spatial index
        """
        nrows, ncols = pixelGrid.getDimensions()
        self.si_cnt = numpy.zeros((nrows, ncols), 
                        dtype=SPDV4_SIMPLEGRID_COUNT_DTYPE)
        self.si_idx = numpy.zeros((nrows, ncols), 
                        dtype=SPDV4_SIMPLEGRID_INDEX_DTYPE)

        # save the pixelGrid
        self.pixelGrid = pixelGrid

    def setPulsesForExtent(self, extent, pulses, lastPulseID):
        """
        Update the spatial index. Given extent and data works out what
        needs to be written.
        """
        xMin = self.pixelGrid.snapToGrid(extent.xMin, self.pixelGrid.xMin, 
                self.pixelGrid.xRes)
        xMax = self.pixelGrid.snapToGrid(extent.xMax, self.pixelGrid.xMax, 
                self.pixelGrid.xRes)
        yMin = self.pixelGrid.snapToGrid(extent.yMin, self.pixelGrid.yMin, 
                self.pixelGrid.yRes)
        yMax = self.pixelGrid.snapToGrid(extent.yMax, self.pixelGrid.yMax, 
                self.pixelGrid.yRes)
                
        # size of spatial index we need to write
        nrows = int(numpy.ceil((yMax - yMin) / self.pixelGrid.xRes))
        ncols = int(numpy.ceil((xMax - xMin) / self.pixelGrid.xRes))

        mask, sortedBins, idx_subset, cnt_subset = gridindexutils.CreateSpatialIndex(
                pulses[self.si_yPulseColName], pulses[self.si_xPulseColName], self.pixelGrid.xRes, yMax, xMin,
                nrows, ncols, SPDV4_SIMPLEGRID_INDEX_DTYPE, 
                SPDV4_SIMPLEGRID_COUNT_DTYPE)
                
        # so we have unique indexes
        idx_subset = idx_subset + lastPulseID
                   
        # note overlap is zero as we have already removed them by not including 
        # them in the spatial index
        imageSlice, siSlice = gridindexutils.getSlicesForExtent(self.pixelGrid, 
                     self.si_cnt.shape, 0, xMin, xMax, yMin, yMax)

        if imageSlice is not None and siSlice is not None:

            self.si_cnt[siSlice] = cnt_subset[imageSlice]
            self.si_idx[siSlice] = idx_subset[imageSlice]

        # re-sort the pulses to match the new spatial index
        pulses = pulses[mask]
        pulses = pulses[sortedBins]
        
        # return the new ones in the correct order to write
        # and the mask to remove points, waveforms etc
        # and the bin index to sort points, waveforms, etc
        return pulses, mask, sortedBins

class SPDV4File(generic.LiDARFile):
    """
    Class to support reading and writing of SPD Version 4.x files.
    
    Uses h5py to handle access to the underlying HDF5 file.
    """
    def __init__(self, fname, mode, controls, userClass):
        generic.LiDARFile.__init__(self, fname, mode, controls, userClass)
    
        # convert mode into h5py mode string
        if mode == generic.READ:
            h5py_mode = 'r'
        elif mode == generic.UPDATE:
            h5py_mode = 'r+'
        elif mode == generic.CREATE:
            h5py_mode = 'w'
        else:
            raise ValueError('Unknown value for mode parameter')
    
        # attempt to open the file
        try:
            self.fileHandle = h5py.File(fname, h5py_mode)
        except (OSError, IOError) as err:
            # always seems to throw an OSError
            # found another one!
            raise generic.LiDARFormatNotUnderstood(str(err))
            
        # check that it is indeed the right version
        # and get attributes
        fileAttrs = self.fileHandle.attrs
        if mode == generic.READ or mode == generic.UPDATE:
            if not 'VERSION_SPD' in fileAttrs:
                msg = "File appears not to be SPD"
                raise generic.LiDARFormatNotUnderstood(msg)
            elif fileAttrs['VERSION_SPD'][0] != SPDV4_VERSION_MAJOR:
                msg = "File seems to be wrong version for this driver"
                raise generic.LiDARFormatNotUnderstood(msg)
                
        else:
            # make sure the attributes have the right names
            for key in HEADER_FIELDS:
                cls = HEADER_FIELDS[key]
                # blank value - 0 for numbers, '' for strings
                if key in HEADER_ARRAY_FIELDS:
                    fileAttrs[key] = numpy.array([cls()])
                else:
                    fileAttrs[key] = cls() 

            # write the GENERATING_SOFTWARE tag
            fileAttrs['GENERATING_SOFTWARE'] = generic.SOFTWARE_NAME
                    
            # create the POINTS and PULSES groups
            data = self.fileHandle.create_group('DATA')
            data.create_group('POINTS')
            data.create_group('PULSES')
            data.create_group('WAVEFORMS')

        # Spatial Index
        # TODO: prefType
        self.si_handler = SPDV4SpatialIndex.getHandlerForFile(self.fileHandle, mode)
         
        # the following is for caching reads so we don't need to 
        # keep re-reading each time the user asks. Also handy since
        # reading points requires pulses etc
        self.lastExtent = None
        self.lastPulseRange = None
        self.lastPoints = None
        self.lastPointsSpace = None
        self.lastPoints_Idx = None
        self.lastPoints_IdxMask = None
        self.lastPointsColumns = None
        self.lastPulses = None
        self.lastPulsesSpace = None
        self.lastPulses_Idx = None
        self.lastPulses_IdxMask = None
        self.lastPulsesColumns = None
        # h5space.H5Space
        self.lastWaveSpace = None
        self.lastWave_Idx = None
        self.lastWave_IdxMask = None
        # h5space.H5Space
        self.lastTransSpace = None
        # index to turn into 2d transbypulses
        self.lastTrans_Idx = None
        # mask for 2d transbypulses
        self.lastTrans_IdxMask = None
        # h5space.H5Space
        self.lastRecvSpace = None
        # index to turn into 2d recvbypulses
        self.lastRecv_Idx = None
        # mask for 2d recvbypulses
        self.lastRecv_IdxMask = None
        # flushed by close()
        self.pulseScalingValues = {}
        self.pointScalingValues = {}
        self.waveFormScalingValues = {}
        # handle dtypes for optional fields
        self.pulseDtypes = {}
        self.pointDtypes = {}
        self.waveFormDtypes = {}
        
        # the current extent or range for data being read
        self.extent = None
        self.pulseRange = None

        self.pixGrid = None

        self.extentAlignedWithSpatialIndex = True
        self.unalignedWarningGiven = False
        
        # for writing a new file, we generate PULSE_ID uniquely
        self.lastPulseID = numpy.uint64(0)
        
    @staticmethod 
    def getDriverName():
        """
        Name of this driver
        """
        return "SPDV4"

    @staticmethod
    def getTranslationDict(arrayType):
        """
        Translation dictionary between formats
        """
        dict = {}
        if arrayType == generic.ARRAY_TYPE_POINTS:
            dict[generic.FIELD_POINTS_RETURN_NUMBER] = 'RETURN_NUMBER'
        elif arrayType == generic.ARRAY_TYPE_PULSES:
            dict[generic.FIELD_PULSES_TIMESTAMP] = 'TIMESTAMP'
        return dict

    def setExtent(self, extent):
        """
        Set the extent for reading or writing
        """
        if not self.hasSpatialIndex():
            msg = 'Format has no spatial Index. Processing must be done non-spatially'
            raise generic.LiDARInvalidSetting(msg)
        self.extent = extent
        
        # need to check that the given extent is on the same grid as the 
        # spatial index. If not a new spatial index will have to be calculated
        # for each block before we can access the data.
        totalPixGrid = self.getPixelGrid()
        extentPixGrid = pixelgrid.PixelGridDefn(xMin=extent.xMin, 
                xMax=extent.xMax, yMin=extent.yMin, yMax=extent.yMax,
                xRes=extent.binSize, yRes=extent.binSize, projection=totalPixGrid.projection)
        self.extentAlignedWithSpatialIndex = (
                extentPixGrid.alignedWith(totalPixGrid) and 
                extent.binSize == totalPixGrid.xRes)
        
        if (not self.extentAlignedWithSpatialIndex and 
                    not self.unalignedWarningGiven):
            msg = """Extent not on same grid or resolution as file.
spatial index will be recomputed on the fly"""
            self.controls.messageHandler(msg, generic.MESSAGE_INFORMATION)
            self.unalignedWarningGiven = True
        
    def getPixelGrid(self):
        """
        Return the PixelGridDefn for this file
        """
        if self.hasSpatialIndex():
            pixGrid = copy.copy(self.si_handler.pixelGrid)
        else:
            # no spatial index - no pixgrid
            pixGrid = None
        return pixGrid
        
    def setPixelGrid(self, pixGrid):
        """
        Set the PixelGridDefn for the reading or 
        writing
        """
        if self.mode == generic.READ or self.mode == generic.UPDATE:
            msg = 'Can only set new pixel grid when creating'
            raise generic.LiDARInvalidData(msg)
            
        else:
            self.si_handler.createNewIndex(pixGrid)
            
        # cache it
        self.pixGrid = pixGrid
        
    def hasSpatialIndex(self):
        """
        Return True if we have a spatial index.
        """
        return self.si_handler is not None
        
    def close(self):
        """
        Close all open file handles
        """
        if self.si_handler is not None:
            self.si_handler.close()

        # flush the scaling values
        if self.mode != generic.READ:
            pulsesHandle = self.fileHandle['DATA']['PULSES']
            for colName in self.pulseScalingValues.keys():
                gain, offset = self.pulseScalingValues[colName]
                if colName not in pulsesHandle:
                    msg = 'scaling set for column %s but no data written' % colName
                    self.controls.messageHandler(msg, generic.MESSAGE_INFORMATION)
                else:    
                    attrs = pulsesHandle[colName].attrs
                    attrs[GAIN_NAME] = gain
                    attrs[OFFSET_NAME] = offset
            
            pointsHandle = self.fileHandle['DATA']['POINTS']
            for colName in self.pointScalingValues.keys():
                gain, offset = self.pointScalingValues[colName]
                if colName not in pointsHandle:
                    msg = 'scaling set for column %s but no data written' % colName
                    self.controls.messageHandler(msg, generic.MESSAGE_INFORMATION)
                else:
                    attrs = pointsHandle[colName].attrs
                    attrs[GAIN_NAME] = gain
                    attrs[OFFSET_NAME] = offset
                
            waveHandle = self.fileHandle['DATA']['WAVEFORMS']
            for colName in self.waveFormScalingValues.keys():
                gain, offset = self.waveFormScalingValues[colName]
                if colName not in waveHandle:
                    msg = 'scaling set for column %s but no data written' % colName
                    self.controls.messageHandler(msg, generic.MESSAGE_INFORMATION)
                else:                
                    attrs = waveHandle[colName].attrs
                    attrs[GAIN_NAME] = gain
                    attrs[OFFSET_NAME] = offset
        
            # write the version information
            headerArray = numpy.array([SPDV4_VERSION_MAJOR, SPDV4_VERSION_MINOR], 
                                HEADER_FIELDS['VERSION_SPD'])
            self.setHeaderValue('VERSION_SPD', headerArray)
        
        # close
        self.fileHandle.close()
        self.fileHandle = None        
        self.lastExtent = None
        self.lastPoints = None
        self.lastPointsSpace = None
        self.lastPoints_Idx = None
        self.lastPoints_IdxMask = None
        self.lastPointsColumns = None
        self.lastPulses = None
        self.lastPulseRange = None
        self.lastPulsesSpace = None
        self.lastPulses_Idx = None
        self.lastPulses_IdxMask = None
        self.lastPulsesColumns = None
        self.lastWaveSpace = None
        self.lastWave_Idx = None
        self.lastWave_IdxMask = None
        self.lastTransSpace = None
        self.lastTrans_Idx = None
        self.lastTrans_IdxMask = None
        self.lastRecvSpace = None
        self.lastRecv_Idx = None
        self.lastRecv_IdxMask = None
        self.pulseScalingValues = None
        self.pointScalingValues = None
        self.extent = None
        self.pulseRange = None
        self.pixGrid = None
        self.pulseDtypes = None
        self.pointDtypes = None
        self.waveFormDtypes = None

    @staticmethod
    def readFieldAndUnScale(handle, name, selection, unScaled=False):
        """
        Given a h5py handle, field name and selection does
        any unscaling if asked (unScaled=False). 
        """
        attrs = handle[name].attrs
        data = selection.read(handle[name])

        if not unScaled and GAIN_NAME in attrs and OFFSET_NAME in attrs:
            data = (data / attrs[GAIN_NAME]) + attrs[OFFSET_NAME]
        return data
        
    @staticmethod
    def readFieldsAndUnScale(handle, colNames, selection):
        """
        Given a list of column names returns a structured array
        of the data. If colNames is a string, a single un-structred
        array will be returned.
        It will work out of any of the column names end with '_U'
        and deal with them appropriately.
        selection should be a h5space.H5Space.
        """
        if isinstance(colNames, str):
            if colNames not in handle:
                msg = 'column %s not found in file' % colNames
                raise generic.LiDARArrayColumnError(msg)
            unScaled = colNames.endswith('_U')
            if unScaled:
                colNames = colNames[:-2]
            data = SPDV4File.readFieldAndUnScale(handle, colNames, 
                                selection, unScaled)

        else:            
            # create a blank structured array to read the data into
            dtypeList = []
            # names in the HDF5 file ('_U' removed)
            hdfNameList = []
            # Whether they are unscaled fields or not
            unScaledList = []
            for name in colNames:
                if name not in handle:
                    msg = 'column %s not found in file' % name
                    raise generic.LiDARArrayColumnError(msg)
                unScaled = name.endswith('_U')
                hdfName = name
                attrs = handle[name].attrs
                hasScale = GAIN_NAME in attrs and OFFSET_NAME in attrs
                if hasScale and not unScaled:
                    s = 'f8'
                else:
                    if unScaled:
                        hdfName = name[:-2]
                    s = handle[hdfName].dtype.str
                dtypeList.append((str(name), s))
                hdfNameList.append(hdfName)
                unScaledList.append(unScaled)
            
            numRecords = selection.getSelectionSize()
               
            data = numpy.empty(numRecords, dtypeList)
        
            for name, hdfName, unScaled in zip(colNames, hdfNameList, unScaledList):
                field = SPDV4File.readFieldAndUnScale(handle, hdfName, 
                                selection, unScaled)
                data[str(name)] = field
            
        return data
        
    def readPointsForExtent(self, colNames=None):
        """
        Read all the points within the given extent
        as 1d structured array. 

        colNames can be a name or list of column names to return. By default
        all columns are returned.
        """
        pointsHandle = self.fileHandle['DATA']['POINTS']
        if colNames is None:
            # get all names
            colNames = pointsHandle.keys()
            
        # returned cached if possible
        if (self.lastExtent is not None and self.lastExtent == self.extent and 
            self.lastPoints is not None and self.lastPointsColumns is not None
            and self.lastPointsColumns == colNames):
            # TODO: deal with single column request when cached is multi column
            return self.lastPoints
        
        point_space, idx, mask_idx = (
                            self.si_handler.getPointsSpaceForExtent(self.extent, 
                                        self.controls.overlap))
        
        points = self.readFieldsAndUnScale(pointsHandle, colNames, point_space)
            
        self.lastExtent = copy.copy(self.extent)
        self.lastPoints = points
        self.lastPointsSpace = point_space
        self.lastPoints_Idx = idx
        self.lastPoints_IdxMask = mask_idx
        self.lastPointsColumns = colNames
        return points

    def readPulsesForExtent(self, colNames=None):
        """
        Read all the pulses within the given extent
        as 1d structured array. 

        colNames can be a name or list of column names to return. By default
        all columns are returned.
        """
        pulsesHandle = self.fileHandle['DATA']['PULSES']
        if colNames is None:
            # get all names
            colNames = pulsesHandle.keys()
            
        # returned cached if possible
        if (self.lastExtent is not None and self.lastExtent == self.extent and 
            self.lastPulses is not None and self.lastPulsesColumns is not None
            and self.lastPulsesColumns == colNames):
            # TODO: deal with single column request when cached is multi column
            return self.lastPulses
        
        pulse_space, idx, mask_idx = (
                            self.si_handler.getPulsesSpaceForExtent(self.extent, 
                                    self.controls.overlap))

        pulses = self.readFieldsAndUnScale(pulsesHandle, colNames, pulse_space)
        
        if not self.extentAlignedWithSpatialIndex:
            # need to recompute subset of spatial index to bins
            # are aligned with current extent
            nrows = int(numpy.ceil((self.extent.yMax - self.extent.yMin) / 
                        self.extent.binSize))
            ncols = int(numpy.ceil((self.extent.xMax - self.extent.xMin) / 
                        self.extent.binSize))
            nrows += (self.controls.overlap * 2)
            ncols += (self.controls.overlap * 2)
            x_idx = self.readFieldAndUnScale(pulsesHandle, self.si_handler.si_xPulseColName, pulse_space)
            y_idx = self.readFieldAndUnScale(pulsesHandle, self.si_handler.si_yPulseColName, pulse_space)
            mask, sortedbins, new_idx, new_cnt = gridindexutils.CreateSpatialIndex(
                    y_idx, x_idx, 
                    self.extent.binSize, 
                    self.extent.yMax, self.extent.xMin, nrows, ncols, 
                    SPDV4_SIMPLEGRID_INDEX_DTYPE, SPDV4_SIMPLEGRID_COUNT_DTYPE)
            # ok calculate indices on new spatial indexes
            nOut = self.fileHandle['DATA']['PULSES']['PULSE_ID'].shape[0]
            pulse_space, idx, mask_idx = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                            new_idx, new_cnt, nOut)
            # re-sort the pulses to match the new spatial index
            pulses = pulses[mask]
            pulses = pulses[sortedbins]

            
        self.lastExtent = copy.copy(self.extent)
        self.lastPulses = pulses
        self.lastPulsesSpace = pulse_space
        self.lastPulses_Idx = idx
        self.lastPulses_IdxMask = mask_idx
        self.lastPulsesColumns = colNames
        self.lastPoints = None # cache will now be out of date
        return pulses
    
    def readPulsesForExtentByBins(self, extent=None, colNames=None):
        """
        Return the pulses as a 3d structured masked array.
        """
        # if they have given us a new extent then use that
        if extent is not None:
            oldExtent = self.lastExtent
            self.setExtent(extent)
        # go and get the pulses - should returned cached if 
        # already got.
        pulses = self.readPulsesForExtent(colNames)
        # get these 'last' indices which map spatial index to pulses
        idx = self.lastPulses_Idx
        idxMask = self.lastPulses_IdxMask 
        # re-map into 3d
        pulsesByBins = pulses[idx]
        
        # set extent back to the 'normal' one for this block
        # in case they call this again without the extent param
        if extent is not None:
            self.setExtent(oldExtent)
            
        # make masked array
        pulses = numpy.ma.array(pulsesByBins, mask=idxMask)
        return pulses

    def readPointsForExtentByBins(self, extent=None, colNames=None, 
                    indexByPulse=False, returnPulseIndex=False):
        """
        Return the points as a 3d structured masked array.
        
        Note that because the spatial index on a SPDV4 file currently is on pulses
        this may miss points that are attached to pulses outside the current
        extent. If this is a problem then select an overlap large enough.
        
        Pass indexByPulse=True to bin the points by the locations of the pulses
            (using X_IDX and Y_IDX rather than the locations of the points)
        Pass returnPulseIndex=True to also return a masked 3d array of 
            the indices into the 1d pulse array (as returned by 
            readPulsesForExtent())
            
        """
        # if they have given us a new extent then use that
        if extent is not None:
            oldExtent = self.lastExtent
            self.setExtent(extent)
        # have to spatially index the points 
        # since SPDV4 files have only a spatial index on pulses currently.
        points = self.readPointsForExtent(colNames)
        
        nrows = int((self.lastExtent.yMax - self.lastExtent.yMin) / 
                        self.lastExtent.binSize)
        ncols = int((self.lastExtent.xMax - self.lastExtent.xMin) / 
                        self.lastExtent.binSize)
                        
        # add overlap
        nrows += (self.controls.overlap * 2)
        ncols += (self.controls.overlap * 2)
        xMin = self.lastExtent.xMin - (self.controls.overlap * self.lastExtent.binSize)
        yMax = self.lastExtent.yMax + (self.controls.overlap * self.lastExtent.binSize)
        
        # create point spatial index
        if indexByPulse:
            # TODO: check if is there is a better way of going about this
            # in theory spatial index already exists but may be more work 
            # it is worth to use
            # TODO: check these fields aren't actually already read in
            x_idx = self.readPulsesForExtent(self.si_handler.si_xPulseColName)
            y_idx = self.readPulsesForExtent(self.si_handler.si_yPulseColName)
            nreturns = self.readPulsesForExtent('NUMBER_OF_RETURNS')
            x_idx = numpy.repeat(x_idx, nreturns)
            y_idx = numpy.repeat(y_idx, nreturns)
        else:
            # TODO: check these fields aren't actually already read in
            x_idx = self.readPointsForExtent('X')
            y_idx = self.readPointsForExtent('Y')
        
        mask, sortedbins, idx, cnt = gridindexutils.CreateSpatialIndex(
                y_idx, x_idx, self.lastExtent.binSize, 
                yMax, xMin, nrows, ncols, SPDV4_SIMPLEGRID_INDEX_DTYPE, 
                SPDV4_SIMPLEGRID_COUNT_DTYPE)
                
        nOut = len(points)
        pts_space, pts_idx, pts_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                                idx, cnt, nOut)

        points = points[mask]                  
        sortedPoints = points[sortedbins]
        
        pointsByBins = sortedPoints[pts_idx]

        # set extent back to the 'normal' one for this block
        # in case they call this again without the extent param
        if extent is not None:
            self.setExtent(oldExtent)

        self.lastPoints3d_Idx = pts_idx
        self.lastPoints3d_IdxMask = pts_idx_mask
        self.lastPoints3d_InRegionMask = mask
        self.lastPoints3d_InRegionSort = sortedbins
        
        points = numpy.ma.array(pointsByBins, mask=pts_idx_mask)
        
        if returnPulseIndex:
            # have to generate array the same lengths as the 1d points
            # but containing the indexes of the pulses
            pulse_count = numpy.arange(0, self.lastPulses.size)
            # convert this into an array with an element for each point
            pulse_idx_1d = numpy.repeat(pulse_count, 
                            self.lastPulses['NUMBER_OF_RETURNS'])
            # mask the ones that are within the spatial index
            pulse_idx_1d = pulse_idx_1d[mask]
            # sort the right way
            sortedpulse_idx_1d = pulse_idx_1d[sortedbins]
            # turn into a 3d in the same way as the points themselves
            pulse_idx_3d = sortedpulse_idx_1d[pts_idx]
            
            # create a masked array 
            pulse_idx_3dmask = numpy.ma.array(pulse_idx_3d, mask=pts_idx_mask)
            
            # return 2 things
            return points, pulse_idx_3dmask
        else:
            # just return the points
            return points
        
    def readPointsByPulse(self, colNames=None):
        """
        Return a 2d masked structured array of point that matches
        the pulses.
        """
        if self.controls.spatialProcessing:
            points = self.readPointsForExtent(colNames)
        else:
            points = self.readPointsForRange(colNames)
        idx = self.lastPoints_Idx
        idxMask = self.lastPoints_IdxMask

        if points is None:
            return None        
        pointsByPulse = points[idx]
        points = numpy.ma.array(pointsByPulse, mask=idxMask)
        return points

    def readWaveformInfo(self):
        """
        Return 2d masked array of information about
        the waveforms.
        """
        if self.controls.spatialProcessing:
            try:
                # optional fields - fail if they don't exist
                idx = self.readPulsesForExtent('WFM_START_IDX')
                cnt = self.readPulsesForExtent('NUMBER_OF_WAVEFORM_SAMPLES')
            except generic.LiDARArrayColumnError:
                return None
        else:
            try:
                # optional fields - fail if they don't exist
                idx = self.readPulsesForRange('WFM_START_IDX')
                cnt = self.readPulsesForRange('NUMBER_OF_WAVEFORM_SAMPLES')
            except generic.LiDARArrayColumnError:
                return None

        waveHandle = self.fileHandle['DATA']['WAVEFORMS']
        colNames = waveHandle.keys()
        if len(colNames) == 0:
            return None
        nOut = waveHandle['NUMBER_OF_WAVEFORM_RECEIVED_BINS'].shape[0]
        wave_space, wave_idx, wave_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                    idx, cnt, nOut)

        waveformInfo = self.readFieldsAndUnScale(waveHandle, colNames, wave_space)
        waveformInfo = waveformInfo[wave_idx]
        wave_masked = numpy.ma.array(waveformInfo, mask=wave_idx_mask)

        self.lastWaveSpace = wave_space
        self.lastWave_Idx = wave_idx
        self.lastWave_IdxMask = wave_idx_mask
        
        return wave_masked
        
    def readTransmitted(self):
        """
        Return the 3d masked integer array of transmitted for each of the
        current pulses.
        First axis is the waveform bin.
        Second axis is waveform number and last is pulse.
        """
        waveformInfo = self.readWaveformInfo()
        if waveformInfo is None:
            return None

        if 'TRANSMITTED' not in self.fileHandle['DATA']:
            return None
        nOut = self.fileHandle['DATA']['TRANSMITTED'].shape[0]

        # NB: waveformInfo is masked
        idx = waveformInfo['TRANSMITTED_START_IDX'].data
        cnt = waveformInfo['NUMBER_OF_WAVEFORM_TRANSMITTED_BINS']
        cnt = cnt.filled(0)
        
        trans_shape, trans_idx, trans_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                        idx, cnt, nOut)
            
        trans = trans_shape.read(self.fileHandle['DATA']['TRANSMITTED'])
        # so we can apply scaling, below
        trans = trans.astype(numpy.float32)
        trans = trans[trans_idx]

        # apply gain and offset
        for waveform in range(waveformInfo.shape[0]):
            offset = waveformInfo[waveform]['TRANS_WAVE_OFFSET']
            gain = waveformInfo[waveform]['TRANS_WAVE_GAIN']
            trans[...,waveform,...] = (trans[...,waveform,...] / gain) + offset
            
        self.lastTransSpace = trans_shape
        self.lastTrans_Idx = trans_idx
        self.lastTrans_IdxMask = trans_idx_mask
        
        # create masked array
        trans = numpy.ma.array(trans, mask=trans_idx_mask)
        
        return trans
            

    def readReceived(self):
        """
        Return the 3d masked integer array of received for each of the
        current pulses.
        First axis is the waveform bin.
        Second axis is waveform number and last is pulse.
        """
        waveformInfo = self.readWaveformInfo()
        if waveformInfo is None:
            return None

        if 'RECEIVED' not in self.fileHandle['DATA']:
            return None
        nOut = self.fileHandle['DATA']['RECEIVED'].shape[0]
        
        # NB: waveformInfo is masked
        idx = waveformInfo['RECEIVED_START_IDX'].data
        cnt = waveformInfo['NUMBER_OF_WAVEFORM_RECEIVED_BINS']
        cnt = cnt.filled(0)
        
        recv_shape, recv_idx, recv_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                        idx, cnt, nOut)
            
        recv = recv_shape.read(self.fileHandle['DATA']['RECEIVED'])
        # so we can apply scaling, below
        recv = recv.astype(numpy.float32)
        recv = recv[recv_idx]

        # apply gain and offset
        for waveform in range(waveformInfo.shape[0]):
            offset = waveformInfo[waveform]['RECEIVE_WAVE_OFFSET']
            gain = waveformInfo[waveform]['RECEIVE_WAVE_GAIN']
            recv[...,waveform,...] = (recv[...,waveform,...] / gain) + offset

        self.lastRecvSpace = recv_shape
        self.lastRecv_Idx = recv_idx
        self.lastRecv_IdxMask = recv_idx_mask
        
        # create masked array
        recv = numpy.ma.array(recv, mask=recv_idx_mask)
        
        return recv
            
    def preparePulsesForWriting(self, pulses):
        """
        Called from writeData(). Massages what the user has passed into something
        we can write back to the file.
        """
        if pulses.size == 0:
            return None, None, None
            
        mask = None
        binidx = None
            
        if pulses.ndim == 3:
            # must flatten back to be 1d using the indexes
            # used to create the 3d version (pulsesbybin)
            if self.mode == generic.UPDATE:
                flatSize = self.lastPulses_Idx.max() + 1
                flatPulses = numpy.empty((flatSize,), dtype=pulses.data.dtype)
                gridindexutils.flatten3dMaskedArray(flatPulses, pulses,
                            self.lastPulses_IdxMask, self.lastPulses_Idx)
                pulses = flatPulses
            else:
                # TODO: flatten somehow
                raise NotImplementedError()
                
        if pulses.ndim != 1:
            msg = 'Pulse array must be either 1d or 3d'
            raise generic.LiDARInvalidSetting(msg)
                
        # NOTE: on update now we just don't write the X_IDX
        # and Y_IDX fields since they shouldn't be updated.
        # SPDV3 gives you a warning if you change these fields
        # in SPDV4 the updates are silently lost        
        # TODO: surely we can do better than this?

        # essential fields exist?
        if self.mode == generic.CREATE:
            for essential in PULSES_ESSENTIAL_FIELDS:
                if essential not in pulses.dtype.names:
                    msg = ('Essential field %s must exist in pulse data ' +
                             'when writing new file') % essential
                    raise generic.LiDARInvalidData(msg)
        
        if self.extent is not None and self.controls.spatialProcessing:
            if self.mode == generic.UPDATE:
                # while we are at it, grab the X_IDX and Y_IDX fields since
                # they are essential
                x_idx = self.readPulsesForExtent(self.si_handler.si_xPulseColName)
                y_idx = self.readPulsesForExtent(self.si_handler.si_yPulseColName)
                # if we doing spatial processing we need to strip out areas in the overlap
                # self.extent is the size of the block without the overlap
                # so just strip out everything outside of it
                mask = ((x_idx >= self.extent.xMin) & 
                        (x_idx <= self.extent.xMax) & 
                        (y_idx >= self.extent.yMin) &
                        (y_idx <= self.extent.yMax))
                pulses = pulses[mask]
                self.lastPulsesSpace.updateBoolArray(mask)
            else:  # create
                # get the spatial index handling code to sort it.
                pulses, mask, binidx = self.si_handler.setPulsesForExtent(
                                        self.extent, pulses, self.lastPulseID)
          
        return pulses, mask, binidx

    def preparePointsForWriting(self, points, mask):
        """
        Called from writeData(). Massages what the user has passed into something
        we can write back to the file.
        """
        pts_start = None
        nreturns = None
        returnNumber = None
        
        if points.size == 0:
            return None, pts_start, nreturns, returnNumber
            
        origPointsDims = points.ndim

        if points.ndim == 3:
            # must flatten back to be 1d using the indexes
            # used to create the 3d version (pointsbybin)
            if self.mode == generic.UPDATE:
                flatSize = self.lastPoints3d_Idx.max() + 1
                flatPoints = numpy.empty((flatSize,), dtype=points.data.dtype)
                gridindexutils.flatten3dMaskedArray(flatPoints, points, 
                            self.lastPoints3d_IdxMask, self.lastPoints3d_Idx)
                points = flatPoints
            else:
                # TODO: flatten somehow                
                raise NotImplementedError()
                            
        if points.ndim == 2:
            # must flatten back to be 1d using the indexes
            # used to create the 2d version (pointsbypulses)
            if self.mode == generic.UPDATE:
                flatSize = self.lastPoints_Idx.max() + 1
                flatPoints = numpy.empty((flatSize,), dtype=points.data.dtype)
                gridindexutils.flatten2dMaskedArray(flatPoints, points, 
                            self.lastPoints_IdxMask, self.lastPoints_Idx)
                points = flatPoints
            else:
                # get the number of returns for each pulse
                # this doesn't work with structured arrays so need
                # to use one of the fields
                firstField = points.dtype.names[0]
                
                nreturns = points[firstField].count(axis=0)
                pointsHandle = self.fileHandle['DATA']['POINTS']
                currPointsCount = 0
                if firstField in pointsHandle:
                    currPointsCount = pointsHandle[firstField].shape[0]
                    
                # cumsum gives us the end of the points
                # so need roll to move to the start
                # then add the current size of the data written
                pts_start = numpy.cumsum(nreturns)
                pts_start = numpy.roll(pts_start, 1)
                if pts_start.size > 0: 
                    pts_start[0] = 0
                pts_start += currPointsCount
                
                # unfortunately points.compressed() doesn't work
                # for structured arrays. Use our own version instead
                ptsCount = points[firstField].count()
                outPoints = numpy.empty(ptsCount, dtype=points.data.dtype)
                returnNumber = numpy.empty(ptsCount, 
                                    dtype=POINT_FIELDS['RETURN_NUMBER'])
                                    
                gridindexutils.flattenMaskedStructuredArray(points.data, 
                            points[firstField].mask, outPoints, returnNumber)
                
                points = outPoints
                
        if points.ndim != 1:
            msg = 'Point array must be either 1d, 2 or 3d'
            raise generic.LiDARInvalidData(msg)

        if self.mode == generic.UPDATE:
            if self.controls.spatialProcessing:
                nreturns = self.readPulsesForExtent('NUMBER_OF_RETURNS')
                mask = numpy.repeat(mask, nreturns)
                if origPointsDims == 3:
                    # was pointsbybins, now 1d.
                    sortedPointsundo = numpy.empty_like(points)
                    gridindexutils.unsortArray(points, 
                            self.lastPoints3d_InRegionSort, sortedPointsundo)
                    points = sortedPointsundo
                    
                    mask = mask[self.lastPoints3d_InRegionMask]
                    # we didn't do this in writeData, but we can do it now
                    points = points[mask]
                    self.lastPointsSpace.updateBoolArray(self.lastPoints3d_InRegionMask)                        
                else:
                    self.lastPointsSpace.updateBoolArray(mask)

        else:
            # need to check that passed in data has all the required fields
            # TODO: mask?
            for essential in POINTS_ESSENTIAL_FIELDS:
                if essential not in points.dtype.names:
                    msg = ('Essential field %s must exist in point data ' +
                             'when writing new file') % essential
                    raise generic.LiDARInvalidData(msg)
                    
            # transparently convert the IGNORE column (if it exists)
            # into the POINT_FLAGS
            if 'IGNORE' in points.dtype.names:
                ignoreField = points['IGNORE']
                # create a new array without IGNORE
                newDType = []
                for name in points.dtype.names:
                    if name != 'IGNORE':
                        s = points.dtype[name].str
                        newDType.append((name, s))
                        
                # ensure it has POINT_FLAGS
                newFlags = numpy.where(points['IGNORE'] != 0, 
                                SPDV4_POINT_FLAGS_IGNORE, 0)
                if 'POINT_FLAGS' not in points.dtype.names:
                    s = numpy.dtype(POINT_FIELDS['POINT_FLAGS']).str
                    newDType.append(('POINT_FLAGS', s))
                else:
                    # combine
                    newFlags = newFlags | points['POINT_FLAGS']
                    
                # create it
                newpoints = numpy.empty(points.shape, dtype=newDType)
                
                # copy all the old fields accross
                for name in points.dtype.names:
                    if name != 'IGNORE' and name != 'POINT_FLAGS':
                        newpoints[name] = points[name]
                        
                # make sure it has the updated 'POINT_FLAGS'
                newpoints['POINT_FLAGS'] = newFlags
                
                points = newpoints
                
        return points, pts_start, nreturns, returnNumber
        
    def prepareTransmittedForWriting(self, transmitted, waveformInfo, mask):
        """
        Called from writeData(). Massages what the user has passed into something
        we can write back to the file.
        """
        if transmitted.size == 0:
            return None, None, None

        if transmitted.ndim != 3:
            msg = 'transmitted data must be 3d'
            raise generic.LiDARInvalidData(msg)
        
        trans_start = None
        ntrans = None

        # un scale back to DN
        for waveform in range(waveformInfo.shape[0]):
            offset = waveformInfo[waveform]['TRANS_WAVE_OFFSET']
            gain = waveformInfo[waveform]['TRANS_WAVE_GAIN']
            transmitted[waveform] = (transmitted[waveform] - offset) * gain
            
        # cast to type to write to file
        transmitted = transmitted.astype(TRANSMITTED_DTYPE)

        if self.mode == generic.UPDATE:

            origShape = transmitted.shape

            # flatten it back to 1d so it can be written
            flatSize = self.lastTrans_Idx.max() + 1
            flatTrans = numpy.empty((flatSize,), dtype=transmitted.data.dtype)
            gridindexutils.flatten3dMaskedArray(flatTrans, transmitted,
                self.lastTrans_IdxMask, self.lastTrans_Idx)
            transmitted = flatTrans
                
            # mask out those in the overlap using the pulses
            if self.controls.spatialProcessing:

                # Repeat the mask so that it is the same shape as the 
                # original transmitted and then flatten in the same way
                # we can then remove the transmitted outside the extent.         
                # We can't do this earlier since removing from transmitted
                # would mean the above flattening trick won't work.
                mask = numpy.expand_dims(mask, axis=0)
                mask = numpy.expand_dims(mask, axis=0)
                mask = numpy.repeat(mask, origShape[1], axis=2)
                flatMask = numpy.empty((flatSize,), dtype=mask.dtype)
                gridindexutils.flatten3dMaskedArray(flatMask, mask, 
                    self.lastTrans_IdxMask, self.lastTrans_Idx)
            
                self.lastTransSpace.updateBoolArray(flatMask)
                
        else:

            # create arrays for flatten3dWaveformData
            # TODO: mask?
            firstField = waveformInfo.dtype.names[0]
            ntrans = numpy.empty(waveformInfo[firstField].count(), dtype=numpy.uint16)
            flattened =  numpy.empty(transmitted.count(), dtype=transmitted.dtype)
            
            flatten3dWaveformData(received.data, received.mask, nrecv, flattened)
            currTransCount = 0
            if 'TRANSMITTED' in self.fileHandle['DATA']:
                transHandle = self.fileHandle['DATA']['TRANSMITTED']
                currTransCount = transHandle.shape[0]

            trans_start = numpy.cumsum(ntrans)
            trans_start = numpy.roll(trans_start, 1)
            if trans_start.size > 0:
                trans_start[0] = 0
            trans_start += currTransCount            

            transmitted = flattened                
                
        return transmitted, trans_start, ntrans
        
    def prepareReceivedForWriting(self, received, waveformInfo, mask):
        """
        Called from writeData(). Massages what the user has passed into something
        we can write back to the file.
        """
        if received.size == 0:
            return None, None, None

        if received.ndim != 3:
            msg = 'received data must be 3d'
            raise generic.LiDARInvalidData(msg)

        recv_start = None
        nrecv = None

        # un scale back to DN
        for waveform in range(waveformInfo.shape[0]):
            offset = waveformInfo[waveform]['RECEIVE_WAVE_OFFSET']
            gain = waveformInfo[waveform]['RECEIVE_WAVE_GAIN']
            received[waveform] = (received[waveform] - offset) * gain
            
        # cast to type to write to file
        received = received.astype(RECEIVED_DTYPE)

        if self.mode == generic.UPDATE:

            origShape = received.shape
            
            # flatten it back to 1d so it can be written
            flatSize = self.lastRecv_Idx.max() + 1
            flatRecv = numpy.empty((flatSize,), dtype=received.data.dtype)
            gridindexutils.flatten3dMaskedArray(flatRecv, received,
                self.lastRecv_IdxMask, self.lastRecv_Idx)
            received = flatRecv
                
            # mask out those in the overlap using the pulses
            if self.controls.spatialProcessing:

                # Repeat the mask so that it is the same shape as the 
                # original received and then flatten in the same way
                # we can then remove the received outside the extent.         
                # We can't do this earlier since removing from received
                # would mean the above flattening trick won't work.
                mask = numpy.expand_dims(mask, axis=0)
                mask = numpy.expand_dims(mask, axis=0)
                mask = numpy.repeat(mask, origShape[0], axis=0)
                mask = numpy.repeat(mask, origShape[1], axis=2)
                flatMask = numpy.empty((flatSize,), dtype=mask.dtype)
                gridindexutils.flatten3dMaskedArray(flatMask, mask, 
                    self.lastRecv_IdxMask, self.lastRecv_Idx)
                
                received = received[flatMask]
                self.lastRecvSpace.updateBoolArray(flatMask)

        else:
    
            # create arrays for flatten3dWaveformData
            # TODO: mask?
            firstField = waveformInfo.dtype.names[0]
            nrecv = numpy.empty(waveformInfo[firstField].count(), dtype=numpy.uint16)
            flattened =  numpy.empty(received.count(), dtype=received.dtype)
            
            flatten3dWaveformData(received.data, received.mask, nrecv, flattened)
            currRecvCount = 0
            if 'RECEIVED' in self.fileHandle['DATA']:
                recvHandle = self.fileHandle['DATA']['RECEIVED']
                currRecvCount = recvHandle.shape[0]
            
            recv_start = numpy.cumsum(nrecv)
            recv_start = numpy.roll(recv_start, 1)
            if recv_start.size > 0:
                recv_start[0] = 0
            recv_start += currRecvCount            
                
            received = flattened

        return received, recv_start, nrecv

    def prepareWaveformInfoForWriting(self, waveformInfo):
        """
        Flattens the waveformInfo back out so it can be written
        """
    
        firstField = waveformInfo.dtype.names[0]
        
        nwaveforms = waveformInfo[firstField].count(axis=0)
        waveHandle = self.fileHandle['DATA']['WAVEFORMS']
        currWaveformsCount = 0
        if firstField in waveHandle:
            currWaveformsCount = waveHandle[firstField].shape[0]

        # cumsum gives us the end of the points
        # so need roll to move to the start
        # then add the current size of the data written
        wfm_start = numpy.cumsum(nwaveforms)
        wfm_start = numpy.roll(wfm_start, 1)
        if wfm_start.size > 0:
            wfm_start[0] = 0
        wfm_start += currWaveformsCount
        
        # TODO: mask?
        if self.mode == generic.UPDATE:
            # flatten it back to 1d so it can be written
            flatSize = self.lastWave_Idx.max() + 1
            outWave = numpy.empty((flatSize,), dtype=waveformInfo.data.dtype)
            gridindexutils.flatten3dMaskedArray(outWave, waveformInfo,
                self.lastWave_IdxMask, self.lastWave_Idx)

        else:
            # unfortunately points.compressed() doesn't work
            # for structured arrays. Use our own version instead
            waveCount = waveformInfo[firstField].count()
            outWave = numpy.empty(waveCount, dtype=waveformInfo.data.dtype)
            # we don't actually need this, but need to provide it
            returnNumber = numpy.empty(waveCount, 
                            dtype=numpy.uint32)
                                    
            gridindexutils.flattenMaskedStructuredArray(waveformInfo.data, 
                    waveformInfo[firstField].mask, outWave, returnNumber)
                    
        return outWave, wfm_start, nwaveforms
        
    @staticmethod
    def createDataColumn(groupHandle, name, data):
        """
        Creates a new data column under groupHandle with the
        given name with standard HDF5 params.
        
        The type is the same as the numpy array data and data
        is written to the column
        """
        # From SPDLib
        dset = groupHandle.create_dataset(name, data.shape, 
                chunks=(250,), dtype=data.dtype, shuffle=True, 
                compression="gzip", compression_opts=1, maxshape=(None,))
        dset[:] = data
        
    def prepareDataForWriting(self, data, name, arrayType):
        """
        Prepares data for writing to a field. 
        
        arrayType is one of the ARRAY_TYPE values from .generic.
        
        Does unscaling if possible unless name ends with '_U'.
        Raises exception if column needs to have scale and offset
        defined, but aren't.
            
        Returns the data to write, plus the 'hdfname' which
        is the field name the data should be written to. This has the 
        '_U' removed.
        """
        try:
            gain, offset = self.getScaling(name, arrayType)
            hasScaling = True
        except generic.LiDARArrayColumnError:
            hasScaling = False
            
        needsScaling = False
        dataType = None
        
        if arrayType == generic.ARRAY_TYPE_POINTS:
            if name in POINT_SCALED_FIELDS:
                needsScaling = True
            if name in POINT_FIELDS:
                dataType = POINT_FIELDS[name]
            elif name in self.pointDtypes:
                dataType = self.pointDtypes[name]
                
        elif arrayType == generic.ARRAY_TYPE_PULSES:
            if name in PULSE_SCALED_FIELDS:
                needsScaling = True
            if name in PULSE_FIELDS:
                dataType = PULSE_FIELDS[name]
            elif name in self.pointDtypes:
                dataType = self.pointDtypes[name]
                
        elif arrayType == generic.ARRAY_TYPE_WAVEFORMS:
            if name in WAVEFORM_SCALED_FIELDS:
                needsScaling = True
            if name in WAVEFORM_FIELDS:
                dataType = WAVEFORM_FIELDS[name]
            elif name in self.waveFormDtypes:
                dataType = self.waveFormDtypes[name]

        # other array types we don't worry for now
        
        # unless of course, they are passing the unscaled stuff in
        hdfname = name
        if name.endswith('_U'):
            needsScaling = False
            hasScaling = False
            hdfname = name[:-2]
        
        if needsScaling and not hasScaling:
            msg = "field %s requires scaling to be set before writing" % name
            raise generic.LiDARArrayColumnError(msg)
            
        if hasScaling:
            data = (data - offset) * gain
            
        # cast to datatype if it has one
        if dataType is not None:
            data = data.astype(dataType)
            
        return data, hdfname

    def writeStructuredArray(self, hdfHandle, structArray, 
                    generatedColumns, arrayType):
        """
        Writes a structured array as named datasets under hdfHandle. Also writes
        columns in dictionary generatedColumns to the same place.

        Only use for file creation.
        """
        firstField = structArray.dtype.names[0]
        if firstField in hdfHandle:
            oldSize = hdfHandle[firstField].shape[0]
        else:
            oldSize = 0
        newSize = oldSize + len(structArray)
        
        for name in structArray.dtype.names:
            # don't bother writing out the ones we generate ourselves
            if name not in generatedColumns:
                data, hdfname = self.prepareDataForWriting(
                            structArray[name], name, arrayType)
                    
                if hdfname in hdfHandle:
                    hdfHandle[hdfname].resize((newSize,))
                    hdfHandle[hdfname][oldSize:newSize+1] = data
                else:
                    self.createDataColumn(hdfHandle, hdfname, data)
                    
        # now write the generated ones
        for name in generatedColumns.keys():
            data, hdfname = self.prepareDataForWriting(
                generatedColumns[name], name, arrayType)
                        
            if hdfname in hdfHandle:
                hdfHandle[hdfname].resize((newSize,))
                hdfHandle[hdfname][oldSize:newSize+1] = data
            else:
                self.createDataColumn(hdfHandle, hdfname, data)
        
    def writeData(self, pulses=None, points=None, transmitted=None, 
                received=None, waveformInfo=None):
        """
        Write all the updated data. Pass None for data that do not need to be updated.
        It is assumed that each parameter has been read by the reading functions
        """
        if self.mode == generic.READ:
            # the processor always calls this so if a reading driver just ignore
            return
            
        elif self.mode == generic.CREATE:
            # we only accept new data in a particular form so we can attach
            # points to pulses
            if pulses is None and points is None:
                msg = 'Must provide points and pulses when writing new data'
                raise generic.LiDARInvalidData(msg)
                
            if pulses.ndim != 1:
                msg = 'pulses must be 1d as returned from getPulses'
                raise generic.LiDARInvalidData(msg)
            if points is not None and points.ndim != 2:
                msg = 'points must be 2d as returned from getPointsByPulse'
                raise generic.LiDARInvalidData(msg)
        
            if (transmitted is not None or received is not None) and waveformInfo is None:
                msg = 'If transmitted or received is supplied, so must waveformInfo'
                raise generic.LiDARInvalidData(msg)
                
            if transmitted is not None and transmitted.ndim != 3:
                msg = 'transmitted must be 3d as returned by readTransmitted'
                raise generic.LiDARInvalidData(msg)

            if received is not None and received.ndim != 3:
                msg = 'received must be 3d as returned by readReceived'
                raise generic.LiDARInvalidData(msg)
                
            if waveformInfo is not None and waveformInfo.ndim != 2:
                msg = 'waveformInfo must be 2d as returned by readWaveformInfo'
                raise generic.LiDARInvalidData(msg)

        writeWavefromInfo = waveformInfo is not None
        if waveformInfo is None and self.mode == generic.UPDATE:
            # needed so we can process the waveforms
            waveformInfo = self.readWaveformInfo()

        writePulses = pulses is not None
        if pulses is None and self.mode == generic.UPDATE:
            # needed so we can create the mask
            if self.controls.spatialProcessing:
                pulses = self.readPulsesForExtent()
            else:
                pulses = self.readPulsesForRange()
    
        pulses, mask, binidx = self.preparePulsesForWriting(pulses)
        if mask is not None:
            # strip out the ones outside the current extent
            if points is not None:
                # slight problem with this approach is that we have to make
                # points 2d first (as returned by pointsbypulse etc)
                if points.ndim == 1:
                    # readPoints
                    points = points[self.lastPoints_Idx]
                    points = numpy.ma.array(points, 
                                mask=self.lastPoints_IdxMask)
                    # mask out outside block
                    points = points[...,mask]
                    if binidx is not None:
                        points = points[...,binidx]
                elif points.ndim == 3:
                    # readPointsByBins
                    # handled by preparePointsForWriting
                    # as the points need to be re-ordered first
                    pass
                else:
                    # ndim == 2
                    points = points[...,mask]
                    if binidx is not None:
                        points = points[...,binidx]
            if waveformInfo is not None:
                waveformInfo = waveformInfo[...,mask]
                if binidx is not None:
                    waveformInfo = waveformInfo[...,binidx]
            if received is not None:
                received = received[...,...,mask]
                if binidx is not None:
                    received = received[...,...,binidx]
            if transmitted is not None:
                transmitted = transmitted[...,...,mask]
                if binidx is not None:
                    transmitted = transmitted[...,...,binidx]
        
        if points is not None:
            points, pts_start, nreturns, returnNumber = (
                                self.preparePointsForWriting(points, mask))
        
        trans_start = None
        ntrans = None            
        if transmitted is not None:
            transmitted, trans_start, ntrans = (
                self.prepareTransmittedForWriting(transmitted, waveformInfo, mask))
            
        recv_start = None
        nrecv = None
        if received is not None:
            received, recv_start, nrecv = (
                self.prepareReceivedForWriting(received, waveformInfo, mask))
                
        # deal with situation where there is transmitted but not
        # received etc. Assume other wise they will be the same length.
        if points is None and pulses is not None:
            pts_start = numpy.zeros_like(pulses, dtype=numpy.uint64)
            nreturns = numpy.zeros_like(pulses, dtype=numpy.uint8)
        if (recv_start is None and nrecv is None and trans_start is not None 
                    and ntrans is not None):
            recv_start = numpy.zeros_like(trans_start)
            nrecv = numpy.zeros_like(ntrans)
            
        if (trans_start is None and ntrans is None and recv_start is not None
                    and nrecv is not None):
            trans_start = numpy.zeros_like(recv_start)
            ntrans = numpy.zeros_like(nrecv)
            
        if waveformInfo is not None:
            waveformInfo, wfm_start, nwaveforms = (
                        self.prepareWaveformInfoForWriting(waveformInfo))
            
        if self.mode == generic.CREATE:

            if writePulses and pulses is not None and len(pulses) > 0:
                        
                pulsesHandle = self.fileHandle['DATA']['PULSES']
                
                # index into points and pulseid generated fields
                nPulses = len(pulses)
                pulseid = numpy.arange(self.lastPulseID, 
                        self.lastPulseID + nPulses, dtype=PULSE_FIELDS['PULSE_ID'])
                self.lastPulseID = self.lastPulseID + nPulses
                generatedColumns = {'PTS_START_IDX' : pts_start,
                        'NUMBER_OF_RETURNS' : nreturns, 'PULSE_ID' : pulseid}
                        
                if waveformInfo is not None and len(waveformInfo) > 0:
                    # write extra columns
                    generatedColumns['WFM_START_IDX'] = wfm_start
                    generatedColumns['NUMBER_OF_WAVEFORM_SAMPLES'] = nwaveforms

                self.writeStructuredArray(pulsesHandle, pulses, 
                        generatedColumns, generic.ARRAY_TYPE_PULSES)
                
            if points is not None and len(points) > 0:

                pointsHandle = self.fileHandle['DATA']['POINTS']
                generatedColumns = {'RETURN_NUMBER' : returnNumber}
                
                self.writeStructuredArray(pointsHandle, points, 
                        generatedColumns, generic.ARRAY_TYPE_POINTS)
                
            if waveformInfo is not None and len(waveformInfo) > 0 and writeWavefromInfo:
            
                waveHandle = self.fileHandle['DATA']['WAVEFORMS']
                generatedColumns = {'NUMBER_OF_WAVEFORM_RECEIVED_BINS' : nrecv,
                    'NUMBER_OF_WAVEFORM_TRANSMITTED_BINS' : ntrans,
                    'RECEIVED_START_IDX' : recv_start,
                    'TRANSMITTED_START_IDX' : trans_start}

                self.writeStructuredArray(waveHandle, waveformInfo, 
                        generatedColumns, generic.ARRAY_TYPE_WAVEFORMS)
                
            if transmitted is not None and len(transmitted) > 0:
                if 'TRANSMITTED' in self.fileHandle['DATA']:
                    tHandle = self.fileHandle['DATA']['TRANSMITTED']
                    oldSize = tHandle.shape[0]
                    newSize = oldSize + len(transmitted)
                    tHandle.resize((newSize,))
                    tHandle[oldSize:newSize+1] = transmitted
                else:
                    self.createDataColumn(self.fileHandle['DATA'], 
                                'TRANSMITTED', transmitted)

            if received is not None and len(received) > 0:
                if 'RECEIVED' in self.fileHandle['DATA']:
                    rHandle = self.fileHandle['DATA']['RECEIVED']
                    oldSize = rHandle.shape[0]
                    newSize = oldSize + len(received)
                    rHandle.resize((newSize,))
                    rHandle[oldSize:newSize+1] = received
                else:
                    self.createDataColumn(self.fileHandle['DATA'], 
                                'RECEIVED', received)
                
        else:
            # TODO: should we be re-writing the generated columns??
            # Note: we can't use writeStructuredArray since that is for creation
            if points is not None:
                pointsHandle = self.fileHandle['DATA']['POINTS']
                for name in points.dtype.names:
                    data, hdfname = self.prepareDataForWriting(
                                    points[name], name, generic.ARRAY_TYPE_POINTS)

                    if data.size > 0:
                        if hdfname in pointsHandle:
                            # get: Array must be C-contiguous 
                            # without the copy
                            self.lastPointsSpace.write(pointsHandle[hdfname], data.copy())
                        else:
                            self.createDataColumn(pointsHandle, hdfname, data)
                    
            if writePulses and pulses is not None:
                pulsesHandle = self.fileHandle['DATA']['PULSES']
                for name in pulses.dtype.names:
                    if (name != 'X_IDX' and name != 'Y_IDX' and 
                            name != 'X_IDX_U' and name != 'Y_IDX_U'):
                        data, hdfname = self.prepareDataForWriting(
                                    pulses[name], name, generic.ARRAY_TYPE_PULSES)
                        if data.size > 0:
                            if hdfname in pulsesHandle:
                                # get: Array must be C-contiguous 
                                # without the copy
                                self.lastPulsesSpace.write(pulsesHandle[hdfname], data.copy())
                            else:
                                self.createDataColumn(pulsesHandle, hdfname, data)

            if writeWavefromInfo and waveformInfo is not None:
                waveHandle = self.fileHandle['DATA']['WAVEFORMS']
                for name in waveformInfo.dtype.names:
                    data, hdfname = self.prepareDataForWriting(
                                    waveformInfo[name], name, generic.ARRAY_TYPE_WAVEFORMS)
                    if data.size > 0:
                        if hdfname in waveHandle:
                            self.lastWaveSpace.write(waveHandle[hdfname], data.copy())
                        else:
                            self.createDataColumn(waveHandle, hdfname, data)
                                    
            if transmitted is not None:
                self.lastTransSpace.write(self.fileHandle['DATA']['TRANSMITTED'], 
                                transmitted)
            if received is not None:
                self.lastRecvSpace.write(self.fileHandle['DATA']['RECEIVED'], 
                                received)
        
    # The functions below are for when there is no spatial index.
    def setPulseRange(self, pulseRange):
        """
        Set the range of pulses to read
        """
        # copy it so we can change the values if beyond the 
        # range of data
        self.pulseRange = copy.copy(pulseRange)
        nTotalPulses = self.getTotalNumberPulses()
        bMore = True
        if self.pulseRange.startPulse >= nTotalPulses:
            # no data to read
            self.pulseRange.startPulse = 0
            self.pulseRange.endPulse = 0
            bMore = False
            
        elif self.pulseRange.endPulse >= nTotalPulses:
            self.pulseRange.endPulse = nTotalPulses
            
        return bMore

    def readPointsForRange(self, colNames=None):
        """
        Read all the points for the specified range of pulses
        """
        pointsHandle = self.fileHandle['DATA']['POINTS']
        if colNames is None:
            # get all names
            colNames = pointsHandle.keys()
            
        if (self.lastPulseRange is not None and
                self.lastPulseRange == self.pulseRange and
                self.lastPoints is not None and
                self.lastPointsColumns is not None and 
                colNames == self.lastPointsColumns):
            return self.lastPoints
            
        pulses = self.readPulsesForRange()
        
        nReturns = self.readPulsesForRange('NUMBER_OF_RETURNS')
        startIdxs = self.readPulsesForRange('PTS_START_IDX')

        if 'RETURN_NUMBER' not in pointsHandle:
            # not much else we can do...
            # means to points were written to the file, 
            # although there might be pulses
            return None
        
        nOut = pointsHandle['RETURN_NUMBER'].shape[0]
        point_space, point_idx, point_idx_mask = gridindexutils.convertSPDIdxToReadIdxAndMaskInfo(
                        startIdxs, nReturns, nOut)
        
        points = self.readFieldsAndUnScale(pointsHandle, colNames, point_space)
        
        # keep these indices from pulses to points - handy for the indexing 
        # functions.
        self.lastPoints = points
        self.lastPointsSpace = point_space
        self.lastPoints_Idx = point_idx
        self.lastPoints_IdxMask = point_idx_mask
        self.lastPointsColumns = colNames
        # self.lastPulseRange copied in readPulsesForRange()
        return points
    
    def readPulsesForRange(self, colNames=None):
        """
        Read the specified range of pulses
        """
        pulsesHandle = self.fileHandle['DATA']['PULSES']
        if colNames is None:
            # get all names
            colNames = pulsesHandle.keys()
            
        if (self.lastPulseRange is not None and
                self.lastPulseRange == self.pulseRange and 
                self.lastPulses is not None and
                self.lastPulsesColumns is not None and 
                self.lastPulsesColumns == colNames):
            return self.lastPulses
        
        nOut = pulsesHandle['PULSE_ID'].shape[0]
        space = h5space.createSpaceFromRange(self.pulseRange.startPulse, 
                        self.pulseRange.endPulse, nOut)
        pulses = self.readFieldsAndUnScale(pulsesHandle, colNames, space)

        self.lastPulses = pulses
        self.lastPulsesSpace = space
        self.lastPulseRange = copy.copy(self.pulseRange)
        self.lastPoints = None # now invalid
        self.lastPointsColumns = colNames
        return pulses

    def getTotalNumberPulses(self):
        """
        Return the total number of pulses
        """
        # PULSE_ID is always present.
        pulseHandle = self.fileHandle['DATA']['PULSES']
        if 'PULSE_ID' in pulseHandle:
            return pulseHandle['PULSE_ID'].shape[0]
        else:
            return 0
        
    def getHeader(self):
        """
        Return our attributes on the file
        """
        return self.fileHandle.attrs
        
    def setHeader(self, newHeaderDict):
        """
        Update our cached dictionary
        """
        if self.mode == generic.READ:
            msg = 'Can only set header values on update or create'
            raise generic.LiDARInvalidSetting(msg)
        for key in newHeaderDict.keys():
            self.fileHandle.attrs[key] = newHeaderDict[key]
            
    def getHeaderValue(self, name):
        """
        Just extract the one value and return it
        """
        return self.fileHandle.attrs[name]
        
    def setHeaderValue(self, name, value):
        """
        Just update one value in the header
        """
        if self.mode == generic.READ:
            msg = 'Can only set header values on update or create'
            raise generic.LiDARInvalidSetting(msg)
        self.fileHandle.attrs[name] = value
    
    def setScaling(self, colName, arrayType, gain, offset):
        """
        Set the scaling for the given column name
        """
        if self.mode == generic.READ:
            msg = 'Can only set scaling values on update or create'
            raise generic.LiDARInvalidSetting(msg)
            
        if arrayType == generic.ARRAY_TYPE_PULSES:
            self.pulseScalingValues[colName] = (gain, offset)
        elif arrayType == generic.ARRAY_TYPE_POINTS:
            self.pointScalingValues[colName] = (gain, offset)
        elif arrayType == generic.ARRAY_TYPE_WAVEFORMS:
            self.waveFormScalingValues[colName] = (gain, offset)
        else:
            raise generic.LiDARInvalidSetting('Unsupported array type')
            
    def getScaling(self, colName, arrayType):
        """
        Returns the scaling (gain, offset) for the given column name
        reads from our cache since only written to file on close

        Raises generic.LiDARArrayColumnError if no scaling (yet) 
        set for this column.
        """
        if arrayType == generic.ARRAY_TYPE_PULSES:
            if colName in self.pulseScalingValues:
                return self.pulseScalingValues[colName]
                
            handle = self.fileHandle['DATA']['PULSES']
        elif arrayType == generic.ARRAY_TYPE_POINTS:
            if colName in self.pointScalingValues:
                return self.pointScalingValues[colName]
        
            handle = self.fileHandle['DATA']['POINTS']
        elif arrayType == generic.ARRAY_TYPE_WAVEFORMS:
            if colName in self.waveFormScalingValues:
                return self.waveFormScalingValues[colName]
            
            handle = self.fileHandle['DATA']['WAVEFORMS']
        else:
            raise generic.LiDARInvalidSetting('Unsupported array type')
        
        attrs = None
        if colName in handle:
            attrs = handle[colName].attrs
            
        if attrs is not None and GAIN_NAME in attrs and OFFSET_NAME in attrs:
            gain = attrs[GAIN_NAME]
            offset = attrs[OFFSET_NAME]
        else:
            msg = 'gain and offset not found for column %s' % colName
            raise generic.LiDARArrayColumnError(msg)
            
        return gain, offset
        
    def setNativeDataType(self, colName, arrayType, dtype):
        """
        Set the native dtype (numpy.int16 etc)that a column is stored
        as internally after scaling (if any) is applied.
        
        arrayType is one of the lidarprocessor.ARRAY_TYPE_* constants
        
        generic.LiDARArrayColumnError is raised if this cannot be set for the format.
        
        The default behaviour is to create new columns in the correct type for 
        the format, or if they are optional, in the same type as the input array.
        """
        if self.mode == generic.READ:
            msg = 'Can only set scaling values on update or create'
            raise generic.LiDARInvalidSetting(msg)

        if arrayType == generic.ARRAY_TYPE_PULSES:
            if colName in PULSE_FIELDS:
                msg = 'Cannot set type for column %s' % colName
                raise generic.LiDARArrayColumnError(msg)
            self.pulseDtypes[colName] = dtype
            
        elif arrayType == generic.ARRAY_TYPE_POINTS:
            if colName in POINT_FIELDS:
                msg = 'Cannot set type for column %s' % colName
                raise generic.LiDARArrayColumnError(msg)
            self.pointDtypes[colName] = dtype
            
        elif arrayType == generic.ARRAY_TYPE_WAVEFORMS:
            if colName in WAVEFORM_FIELDS:
                msg = 'Cannot set type for column %s' % colName
                raise generic.LiDARArrayColumnError(msg)
            self.waveFormDtypes[colName] = dtype

        else:
            raise generic.LiDARInvalidSetting('Unsupported array type')

    def getNativeDataType(self, colName, arrayType):
        """
        Return the native dtype (numpy.int16 etc)that a column is stored
        as internally after scaling is applied. Provided so scaling
        can be adjusted when translating between formats.
        
        Note that for 'non essential' columns this will depend on the
        data type that the column was to begin with.
        
        arrayType is one of the lidarprocessor.ARRAY_TYPE_* constants
        """
        if arrayType == generic.ARRAY_TYPE_PULSES:
            if colName in PULSE_FIELDS:
                return PULSE_FIELDS[colName]
                
            handle = self.fileHandle['DATA']['PULSES']
        elif arrayType == generic.ARRAY_TYPE_POINTS:
            if colName in POINT_FIELDS:
                return POINT_FIELDS[colName]
                
            handle = self.fileHandle['DATA']['POINTS']
        elif arrayType == generic.ARRAY_TYPE_WAVEFORMS:
            if colName in WAVEFORM_FIELDS:
                return WAVEFORM_FIELDS[colName]
                
            handle = self.fileHandle['DATA']['WAVEFORMS']
        else:
            raise generic.LiDARInvalidSetting('Unsupported array type')
            
        if colName in handle:
            return handle[colName].dtype
        else:
            msg = 'Cannot find column %s' % colName
            raise generic.LiDARArrayColumnError(msg)
            
    def getScalingColumns(self, arrayType):
        """
        arrayType is one of the lidarprocessor.ARRAY_TYPE_* constants
        """
        cols = []
        if arrayType == generic.ARRAY_TYPE_PULSES:
            # first add the compulsory ones
            for col in PULSE_SCALED_FIELDS:
                cols.append(col)
            # then other ones they may have set that aren't compulsory
            for col in self.pulseScalingValues.keys():
                if col not in cols:
                    cols.append(col)
        elif arrayType == generic.ARRAY_TYPE_POINTS:
            # first add the compulsory ones
            for col in POINT_SCALED_FIELDS:
                cols.append(col)
            # then other ones they may have set that aren't compulsory
            for col in self.pointScalingValues.keys():
                if col not in cols:
                    cols.append(col)

        elif arrayType == generic.ARRAY_TYPE_WAVEFORMS:
            # first add the compulsory ones
            for col in WAVEFORM_SCALED_FIELDS:
                cols.append(col)
            # then other ones they may have set that aren't compulsory
            for col in self.waveFormScalingValues.keys():
                if col not in cols:
                    cols.append(col)
        else:
            raise generic.LiDARInvalidSetting('Unsupported array type')

        return cols

class SPDV4FileInfo(generic.LiDARFileInfo):
    """
    Class that gets information about a SPDV4 file
    and makes it available as fields.
    """
    def __init__(self, fname):
        generic.LiDARFileInfo.__init__(self, fname)
    
        # attempt to open the file
        try:
            fileHandle = h5py.File(fname, 'r')
        except (OSError, IOError) as err:
            # always seems to through an OSError
            raise generic.LiDARFormatNotUnderstood(str(err))

        # check that it is indeed the right version
        # and get attributes
        fileAttrs = fileHandle.attrs
        if not 'VERSION_SPD' in fileAttrs:
            msg = "File appears not to be SPD"
            raise generic.LiDARFormatNotUnderstood(msg)
        elif fileAttrs['VERSION_SPD'][0] != SPDV4_VERSION_MAJOR:
            msg = "File seems to be wrong version for this driver"
            raise generic.LiDARFormatNotUnderstood(msg)
            
        # save the header as a dictionary
        self.header = {}
        for key in fileHandle.attrs.keys():
            self.header[key] = fileHandle.attrs[key]

        # pull a few things out to the top level
        self.pulse_fields = [str(k) for k in fileHandle['DATA']['PULSES'].keys()]
        self.point_fields = [str(k) for k in fileHandle['DATA']['POINTS'].keys()]
        if 'WAVEFORMS' in fileHandle['DATA'].keys():
            self.waveform_fields = [str(k) for k in fileHandle['DATA']['WAVEFORMS'].keys()]
        
        si_handler = SPDV4SpatialIndex.getHandlerForFile(fileHandle, generic.READ)
        self.has_Spatial_Index = si_handler is not None
        # probably other things too
        
    @staticmethod 
    def getDriverName():
        """
        Name of this driver
        """
        return "SPDV4"
