#!/usr/bin/env python
'''
Automatically create a regular mesh for GIA model from a MALI mesh
'''

import sys
import numpy as np
import netCDF4
from optparse import OptionParser


print "== Gathering information.  (Invoke with --help for more details. All arguments are optional)\n"
parser = OptionParser()
parser.description = __doc__
parser.add_option("-m", "--mpas", dest="mpasFile", help="name of MPAS file", default="landice_grid.nc", metavar="FILENAME")
parser.add_option("-g", "--gia", dest="giaFile", help="name of GIA mesh file to create", default="gia_grid.nc", metavar="FILENAME")
parser.add_option("-r", "--resolution", dest="resolution", help="OPTIONAL: resolution to use for gia file in km.  If not provided, a reasonable choice will be made.", metavar="RES")
for option in parser.option_list:
    if option.default != ("NO", "DEFAULT"):
        option.help += (" " if option.help else "") + "[default: %default]"
options, args = parser.parse_args()

print "* Source file:  " + options.mpasFile
print "* Destination file:  " + options.giaFile
if options.resolution:
   print "* Using resolution of:  " + options.resolution
else:
   print "* Resolution not provided.  An appropriate resolution will be calculated."

# open mpas file and get needed stuff
fin = netCDF4.Dataset(options.mpasFile, 'r')
xCell = fin.variables['xCell'][:]
yCell = fin.variables['yCell'][:]

# Calculate a resolution if needed
if not options.resolution:
    dcEdge = fin.variables['dcEdge'][:]
    minSpacing = dcEdge.min() / 1000.0
    options.resolution = round(minSpacing) * 1000.0
    print "  - Using resolution of {} m".format(options.resolution)

print ""

# Calculate dimensions
#  make gia grid slightly larger than MALI grid, and round to the nearest km
xmin = np.floor(xCell.min()/1000.0)*1000.0
width = (xCell.max() - xmin)
nx = int(np.ceil(width / options.resolution)) + 1
print "nx={}".format(nx)
x = np.linspace(xmin, xmin + (nx-1) * options.resolution, nx)
#print x
#print len(x)

ymin = np.floor(yCell.min()/1000.0)*1000.0
height = yCell.max() - ymin
ny = int(np.ceil(height / options.resolution)) + 1
print "ny={}".format(ny)
y = np.linspace(ymin, ymin + (ny-1) * options.resolution, ny)

# Create grid file
fout = netCDF4.Dataset(options.giaFile, "w")
fout.createDimension('x', nx)
fout.createDimension('y', ny)
xout = fout.createVariable('x', 'f', ('x',))
xout[:] = x
yout = fout.createVariable('y', 'f', ('y',))
yout[:] = y
thk = fout.createVariable('thk', 'f', ('y','x')) # not needed for grid definition, but useful for opening with ncview
thk[:] = 0.0
fout.close()
print "Wrote GIA grid to " + options.giaFile
