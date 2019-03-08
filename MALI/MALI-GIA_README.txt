README for Iteration Sequence between MALI and Sam’s planar GIA model (giascript.py).

Since the two models utilize different grid geometries, the first step in the iteration process
is to create a rectangular grid from the MALI grid. This is accomplished via the script
 “create_GIA_domain.py” (invoked like: create_GIA_domain.py -m MALI_GRID.nc -g GIA_GRID.nc),
and results in a file called “gia_grid.nc”. Here, the MALI grid can be any appropriate initial
condition file that contains the necessary mesh information (e.g. “thwaites.4km.cleaned.nc” or
“ais20km.150910.nc”), and the GIA grid can be called whatever one wishes.

The next step in the iteration process (after generating a GIA grid from a MALI grid) is
to interpolate the necessary data fields from a MALI control run (i.e. no GIA/bedrock uplift;
onto the GIA grid. This is done by using the “interp_MALI-GIA.py” script
(invoked like: interp_MALI-GIA.py -d g -m MALI_OUTPUT.nc -g GIA_GRID.nc).
Here, “-d g” designates that we are interpolating from MALI to GIA, ”-m” indicates the
MALI control run (w/out uplift; “output.nouplift.nc” in our case), and “-g” designates the
GIA grid onto which one wants to interpolate. This results in a file called “iceload_iter0.nc”.


With these fields now interpolated onto the GIA grid, one can now run the GIA model in order
to compute the resulting change in bedrock topography due to the viscoelastic lithospheric
response to the changing ice sheet thickness. Run the GIA model using “mali-gia-driver.py”,
(invoked like: mali-gia-driver.py), ensuring that the script calls the correct “ice_load.nc” file (line 54).

The resultant uplift field on the GIA grid (called “uplift_GIA_iter0.nc”) from the previous step is
then interpolated back onto the MALI grid
(invoke like: interp_MALI-GIA.py -d m -m MALI_INITIAL_CONDITION.nc -g GIA_OUTPUT.nc).
Here, the -g file should be the GIA model output file containing the 'uplift' field
(e.g. “uplift_GIA_iter0.nc”), and the -m file should be a MALI file that includes the MPAS grid
description as well as the initial bedTopography field (e.g. “thwaites.4km.cleaned.nc”).
This creates a file called “uplift_MPAS_iter0.nc”. This uplift time series is then fed to MALI as a
forcing function (online, in the streams.landice file) in order to calculate the new ice thickness
 time series (among all other MALI outputs). This run of MALI will generate a new output file
(“output.iter0.nc”) that contains the updated ice sheet thickness time series, which should then
 be interpolated onto the GIA grid (creating “iceload_iter1.nc”) and then run through the GIA
 model to generate a new ice load (“uplift_GIA_iter1.nc”) which is then interpolated back onto
 the MALI grid (creating “uplift_MPAS_iter1.nc”) and finally, run online with MALI. The entire
process can be repeated ad infinitum,or until convergence in the uplift field is achieved.
