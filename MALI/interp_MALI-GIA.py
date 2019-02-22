#!/usr/bin/env python
'''
Interpolate fields between a MALI grid and a regular grid for GIA calculations

There are two modes of usage, controlled by the -d option:

1. Interpolate ice load history in a MALI output file to the GIA grid to be used
as input for the GIA model.  In this case, the -m file should be the MALI output file
containing the 'thickness' and 'bedTopography' fields, and the -g file need only contain
a description of the GIA grid (but it can also contain other data).
Invoke like:
./interp_MALI-GIA.py -d g -m MALI_OUTPUT.nc -g GIA_GRID_DESCRIPTION.nc
A new file will be generated that contains the time-series of ice thickness and
bed topography data interpolated onto the GIA grid.

2. Interpolate uplift from a GIA model output file to the MPAS grid and convert to
a bedrock elevation time-series.  In this case, the -g file should be the GIA model
output file containing the 'uplift' field, and the -m file should be a MALI file
that includes the MPAS grid description as well as the initial bedTopography field
(it's ok if other fields are also present).
Invoke like:
./interp_MALI-GIA.py -d m -m MALI_INITIAL_CONDITION.nc -g GIA_OUTPUT.nc
A new file will be generated that contains the time-series of bed topography
on the MPAS grid.

'''

import sys
import numpy as np
import netCDF4
from optparse import OptionParser
import argparse
import math
from collections import OrderedDict
import scipy.spatial
import time
from datetime import datetime


print "== Gathering information.  (Invoke with --help for more details. All arguments are optional)\n"
#parser = OptionParser()
#parser.description = __doc__
#parser.add_option("-m", "--mpas", dest="mpasFile", help="name of MPAS file", default="landice_grid.nc", metavar="FILENAME")
#parser.add_option("-g", "--gia", dest="giaFile", help="name of GIA file", default="gia_grid.nc", metavar="FILENAME")
#parser.add_option("-d", "--destination", dest="destination", type="choice", choices=('m','g'), help="flag to indicate if the MALI grid or the GIA grid is the destination: 'g' or 'm'.  Required.", metavar="DESTINATION")
#for option in parser.option_list:
#    if option.default != ("NO", "DEFAULT"):
#        option.help += (" " if option.help else "") + "[default: %default]"
#options, args = parser.parse_args()

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
parser.description = __doc__
parser.add_argument("-d", "--destination", dest="destination", choices=('m','g'), help="flag to indicate if the MALI grid or the GIA grid is the destination: 'g' or 'm'.  Required.", metavar="DESTINATION")
parser.add_argument("-m", "--mpas", dest="mpasFile", help="name of MPAS file", default="landice_grid.nc", metavar="FILENAME")
parser.add_argument("-g", "--gia", dest="giaFile", help="name of GIA file", default="gia_grid.nc", metavar="FILENAME")
#for option in parser.option_list:
#    if option.default != ("NO", "DEFAULT"):
#        option.help += (" " if option.help else "") + "[default: %default]"
options = parser.parse_args()




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

def delaunay_interp_weights(xy, uv, exteriorThreshold=None):
    '''
    xy = input x,y coords
    uv = output x,y coords
    '''

    d = 2 # number of dims

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
    # ---
    print "    Removing points outside of the union of the two meshes."
    # Always exclude points outside of convex hull
    outsideMask = tri.find_simplex(uv) < 0

    # Also optionally add points that are inside the convex hull but greater than a certain distance to any source points
    # (This operation is slow, but I'm not sure how else to do it.
    #  Also, this is not exact - some oustide points will sneak in, but they will be very close to the source mesh boundaries.)
    if exteriorThreshold is not None:
        for i in np.nonzero(outsideMask==0)[0]:
            if (((uv[i,0] - xy[:,0])**2 + (uv[i,1] - xy[:,1])**2)**0.5).min() > exteriorThreshold:
               outsideMask[i] = 1

    outsideInd = np.nonzero(outsideMask)

    nExtrap = len(outsideInd[0])
    if nExtrap > 0:
       print "    Found {} points outside of union of domains.".format(nExtrap)

    return vertices, wts, outsideInd

#----------------------------

def delaunay_interpolate(values):
    # apply the interpolator
    outfield = np.einsum('nj,nj->n', np.take(values, vtx), wts)

    outfield[outsideIndx] = 0.0

    return outfield

#----------------------------

def copy_mpas_mesh_vars(filein, fileout):
# ============================================
# Copy over all of the required dimensions to the new file
# ============================================
   dims2copy = ['nCells', 'nEdges', 'nVertices', 'TWO', 'vertexDegree', 'maxEdges', 'maxEdges2']
   for dimname in dims2copy:
       fileout.createDimension(dimname, len(filein.dimensions[dimname]))
   if not "StrLen" in fileout.dimensions:
       fileout.createDimension("StrLen", 64)

# ============================================
# Copy over all of the required grid variables to the new file
# ============================================
   #print "Beginning to copy mesh variables to output file."
   vars2copy = ['latCell', 'lonCell', 'xCell', 'yCell', 'zCell', 'indexToCellID', 'latEdge', 'lonEdge', 'xEdge', 'yEdge', 'zEdge', 'indexToEdgeID', 'latVertex', 'lonVertex', 'xVertex', 'yVertex', 'zVertex', 'indexToVertexID', 'cellsOnEdge', 'nEdgesOnCell', 'nEdgesOnEdge', 'edgesOnCell', 'edgesOnEdge', 'weightsOnEdge', 'dvEdge', 'dcEdge', 'angleEdge', 'areaCell', 'areaTriangle', 'cellsOnCell', 'verticesOnCell', 'verticesOnEdge', 'edgesOnVertex', 'cellsOnVertex', 'kiteAreasOnVertex']
   # Add these optional fields if they exist in the input file
   #for optionalVar in ['meshDensity', 'gridSpacing', 'cellQuality', 'triangleQuality', 'triangleAngleQuality', 'obtuseTriangle']:
   #   if optionalVar in filein.variables:
   #      vars2copy.append(optionalVar)

   #for varname in vars2copy:
   #   print "-",
   #print "|"
   for varname in vars2copy:
      thevar = filein.variables[varname]
      datatype = thevar.dtype
      newVar = fileout.createVariable(varname, datatype, thevar.dimensions)
      newVar[:] = thevar[:]
      del newVar, thevar
      #sys.stdout.write("* "); sys.stdout.flush()
   # add some needed attributes
   fileout.on_a_sphere = "NO"
   fileout.sphere_radius = 0.0
   fileout.is_periodic = "NO"
   # write out the mesh to file before proceeding
   fileout.sync()
   print "|"
   print "Finished copying mesh variables to output file.\n"
# ------------


print "=================="
print 'Gathering coordinate information from input and output files.'

# get needed info from MPAS file
MPASfile = netCDF4.Dataset(options.mpasFile,'r')
MPASfile.set_auto_mask(False) # this obscure command prevents the netCDF4 module from returning variables as a numpy Masked Array type and ensures they are always plain old ndarrays, which is expected by the interpolation code
xCell = MPASfile.variables['xCell'][:]
#print 'xCell min/max:', xCell.min(), xCell.max()
yCell = MPASfile.variables['yCell'][:]
#print 'yCell min/max:', yCell.min(), yCell.max()
nCells = len(MPASfile.dimensions['nCells'])
# build array form of MPAS x, y
mpasXY = np.vstack((xCell[:], yCell[:])).transpose()

# Open the gia input file, get needed dimensions
giaFile = netCDF4.Dataset(options.giaFile,'r')
nx = len(giaFile.dimensions['x'])
ny = len(giaFile.dimensions['y'])
x = giaFile.variables['x'][:]
y = giaFile.variables['y'][:]
# build array form of GIA grid x, y
[Yi,Xi] = np.meshgrid(x[:], y[:])
giaXY = np.zeros([Xi.shape[0]*Xi.shape[1],2])
giaXY[:,0] = Yi.flatten()
giaXY[:,1] = Xi.flatten()


# ==========================
if options.destination== 'g':
    # create a new GIA output file
    fout = netCDF4.Dataset("iceload.nc", "w")
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

    print "Creating interpolation object"
    maxDist = MPASfile.variables['dcEdge'][:].max() / 2.0
    vtx, wts, outsideIndx = delaunay_interp_weights(mpasXY, giaXY, maxDist)

    print "Begin interpolation"
    nt = len(MPASfile.dimensions['Time'])
    if 'daysSinceStart' in MPASfile.variables:
       years = MPASfile.variables['daysSinceStart'][:]/365.0
    else:
       # could use xtime if available...
       years = np.arange(nt)
       print "NOTE: No 'daysSinceStart' variable found.  Assuming that time levels represent integer years."
    for t in range(nt):
        #print "Time {} = year {}".format(t, years[t])
        thk[t,:,:] = np.reshape(delaunay_interpolate(MPASfile.variables['thickness'][t,:]), (ny,nx))
        bas[t,:,:] = np.reshape(delaunay_interpolate(MPASfile.variables['bedTopography'][t,:]), (ny,nx))
        tout[t] = t

    # Update history attribute of netCDF file
    thiscommand = datetime.now().strftime("%a %b %d %H:%M:%S %Y") + ": " + " ".join(sys.argv[:])
    setattr(fout, 'history', thiscommand )

    fout.close()

# ==========================
if options.destination == 'm':

    # create a new file for uplift/bed topo on the MPAS grid
    fout = netCDF4.Dataset("uplift_mpas.nc", "w")
    copy_mpas_mesh_vars(MPASfile, fout)
    fout.createDimension('Time', size=None) # make unlimited dimension
    tout = fout.createVariable('Time', 'f', ('Time',))
    tout.units='year'
    xtime = fout.createVariable('xtime', 'c', ('Time', 'StrLen'))
    bedTopo = fout.createVariable('bedTopography', 'd', ('Time', 'nCells'))

    print "Creating interpolation object"
    vtx, wts, outsideIndx = delaunay_interp_weights(giaXY, mpasXY)

    nt = len(giaFile.dimensions['Time'])
    years = giaFile.variables['Time'][:]
    bedTopoBase = MPASfile.variables['bedTopography'][0,:]  # Note using the 0 time level from the MPAS file!
    print "Base bedTopography min={}, max={}".format(bedTopoBase.min(), bedTopoBase.max())
    print "Begin interpolation"
    for t in range(nt):
        print "   Time {} = year {}".format(t, years[t])
        bedTopo[t,:] = delaunay_interpolate(giaFile.variables['uplift'][t,:]) + bedTopoBase
        tout[t] = t
        xtime[t,:] = list("{0:04d}-01-01_00:00:00".format(t).ljust(64))

    # Update history attribute of netCDF file
    thiscommand = datetime.now().strftime("%a %b %d %H:%M:%S %Y") + ": " + " ".join(sys.argv[:])
    setattr(fout, 'history', thiscommand )

    fout.close()

MPASfile.close()
giaFile.close()

print '\nInterpolation completed.'

