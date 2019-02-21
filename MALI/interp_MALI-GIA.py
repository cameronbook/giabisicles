#!/usr/bin/env python
'''
Interpolate fields between a MALI grid and a regular grid for GIA calculations

'''

import sys
import numpy as np
import netCDF4
from optparse import OptionParser
import math
from collections import OrderedDict
import scipy.spatial
import time
from datetime import datetime


print "== Gathering information.  (Invoke with --help for more details. All arguments are optional)\n"
parser = OptionParser()
parser.description = __doc__
parser.add_option("-m", "--mpas", dest="mpasFile", help="name of MPAS file", default="landice_grid.nc", metavar="FILENAME")
parser.add_option("-g", "--gia", dest="giaFile", help="name of GIA file", default="gia_grid.nc", metavar="FILENAME")
parser.add_option("-d", "--destination", dest="destination", type="choice", choices=('m','g'), help="flag to indicate if the MALI grid or the GIA grid is the destination: 'g' or 'm'.  Required.", metavar="DESTINATION")
for option in parser.option_list:
    if option.default != ("NO", "DEFAULT"):
        option.help += (" " if option.help else "") + "[default: %default]"
options, args = parser.parse_args()

print "  MPAS file:  " + options.mpasFile
print "  GIA file:  " + options.giaFile
if options.destination == 'g':
    print "Interpolating ice sheet data from MALI file to a new file on the GIA grid."
elif options.destination == 'm':
    print "Interpolating uplift data from GIA file to a new file on the MALI grid."

print '' # make a space in stdout before further output


#----------------------------
#----------------------------
# Define needed functions
#----------------------------
#----------------------------

def delaunay_interp_weights(xy, uv, d=2):
    '''
    xy = input x,y coords
    uv = output x,y coords
    '''

    if xy.shape[0] > 2**24-1:
       print "WARNING: The source file contains more than 2^24-1 (16,777,215) points due to a limitation in older versions of Qhull (see: https://mail.scipy.org/pipermail/scipy-user/2015-June/036598.html).  Delaunay creation may fail if Qhull being linked by scipy.spatial is older than v2015.0.1 2015/8/31."
       print "scipy version=", scipy.version.full_version

    tri = scipy.spatial.Delaunay(xy)
    print "    Delaunay triangulation complete."
    simplex = tri.find_simplex(uv)
    print "    find_simplex complete."
    vertices = np.take(tri.simplices, simplex, axis=0)
    print "    identified vertices."
    temp = np.take(tri.transform, simplex, axis=0)
    print "    np.take complete."
    delta = uv - temp[:, d]
    bary = np.einsum('njk,nk->nj', temp[:, :d, :], delta)
    print "    calculating bary complete."
    wts = np.hstack((bary, 1 - bary.sum(axis=1, keepdims=True)))

    # Now figure out if there is any extrapolation.
    # Find indices to points of output file that are outside of convex hull of input points
    outsideInd = np.nonzero(tri.find_simplex(uv)<0)
    outsideCoords = uv[outsideInd]
    #print outsideInd
    nExtrap = len(outsideInd[0])
    if nExtrap > 0:
       print "    Found {} points outside of union of domains.".format(nExtrap)

    # Now find nearest neighbor for each outside point
    # Use KDTree of input points
    #tree = scipy.spatial.cKDTree(xy)

    return vertices, wts, outsideInd

#----------------------------

def delaunay_interpolate(values):
    # apply the interpolator
    outfield = np.einsum('nj,nj->n', np.take(values, vtx), wts)

    outfield[outsideIndx] = 0.0

    return outfield

#----------------------------

print "=================="
print 'Gathering coordinate information from input and output files.'


if options.destination== 'g':
    # get needed info from MPAS file
    MPASfile = netCDF4.Dataset(options.mpasFile,'r')
    MPASfile.set_auto_mask(False) # this obscure command prevents the netCDF4 module from returning variables as a numpy Masked Array type and ensures they are always plain old ndarrays, which is expected by the interpolation code
    nt = len(MPASfile.dimensions['Time'])
#    years = MPASfile.variables['daysSinceStart'][:]/365.0

    xCell = MPASfile.variables['xCell'][:]
    #print 'xCell min/max:', xCell.min(), xCell.max()
    yCell = MPASfile.variables['yCell'][:]
    #print 'yCell min/max:', yCell.min(), yCell.max()
    nCells = len(MPASfile.dimensions['nCells'])

    # Open the gia input file, get needed dimensions
    giaFile = netCDF4.Dataset(options.giaFile,'r')
    nx = len(giaFile.dimensions['x'])
    ny = len(giaFile.dimensions['y'])
    x = giaFile.variables['x'][:]
    y = giaFile.variables['y'][:]

    # create a new GIA output file
    fout = netCDF4.Dataset("GIAFILE.nc", "w")
    fout.createDimension('x', nx)
    fout.createDimension('y', ny)
    fout.createDimension('Time', size=None) # make unlimited dimension
    xout = fout.createVariable('x', 'f', ('x',))
    xout[:] = x
    yout = fout.createVariable('y', 'f', ('y',))
    yout[:] = y
    tout = fout.createVariable('Time', 'f', ('Time',))
    tout.units='year'
    thk = fout.createVariable('thk', 'f', ('Time', 'y','x'))
    bas = fout.createVariable('bas', 'f', ('Time', 'y','x'))
    giaFile.close() # done with this already

    print "Creating interpolation object"
    # build array form of GIA grid x, y
    [Yi,Xi] = np.meshgrid(x[:], y[:])
    giaXY = np.zeros([Xi.shape[0]*Xi.shape[1],2])
    giaXY[:,0] = Yi.flatten()
    giaXY[:,1] = Xi.flatten()
    # build array form of MPAS x, y
    mpasXY = np.vstack((xCell[:], yCell[:])).transpose()
    vtx, wts, outsideIndx = delaunay_interp_weights(mpasXY, giaXY)

    print "Begin interpolation"
    for t in range(nt):
        #print "Time {} = year {}".format(t, years[t])
        thk[t,:,:] = np.reshape(delaunay_interpolate(MPASfile.variables['thickness'][t,:]), (ny,nx))
        bas[t,:,:] = np.reshape(delaunay_interpolate(MPASfile.variables['bedTopography'][t,:]), (ny,nx))
        tout[t] = t



    MPASfile.close() # done with this

    # Update history attribute of netCDF file
    thiscommand = datetime.now().strftime("%a %b %d %H:%M:%S %Y") + ": " + " ".join(sys.argv[:])
    setattr(fout, 'history', thiscommand )

    fout.close()

print '\nInterpolation completed.'
