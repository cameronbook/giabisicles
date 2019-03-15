README for Coupling Methods

1. Iterative Method

Since the two models utilize different grid geometries, the first step in the iteration process
is to create a rectangular grid from the MALI grid. This is accomplished via the script
 “create_GIA_domain.py” (invoked like: create_GIA_domain.py -m MALI_GRID.nc -g GIA_GRID.nc),
and results in a file called “gia_grid.nc”. Here, the MALI grid can be any appropriate initial
condition file that contains the necessary mesh information (e.g. “thwaites.4km.cleaned.nc” or
“ais20km.150910.nc”), and the GIA grid can be called whatever one wishes. The generation of a particular grid need only happen once (i.e. there is no need to regenerate the GIA grid with each iteration).

The next step in the iteration process (after generating a GIA grid from a MALI grid) is
to interpolate the necessary data fields from a 300-year MALI control run (i.e. no GIA/bedrock uplift;
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
 the MALI grid (creating “uplift_MPAS_iter1.nc”) and finally, run online with MALI. The entire process can be repeated ad infinitum, or until a convergence criterion is met (e.g. convergence of the uplift field between successive iterations, or in the total mass loss at the end of the simulation). 

2. Alternating Method

The alternating method is a fully-coupled, interactive method that allows the two models to exchange ice loading history and bedrock topography updates at annual intervals. The outline of the method is as follows: (i) MALI is run from an initial condition for one year to generate a one year ice loading history, (ii) this ice loading history is passed to the GIA model, which is then run for one year to generate a transient (one year) bedrock uplift field, (iii) the bedrock uplift field is passed back to MALI, which is run from year one to year two, and (iv) the new ice loading history is passed to the GIA model, which is again run from the year zero to year one to produce a new uplift field. This process can be repeated an arbitrary number of times. One advantage of this method is that each model year is run only once, which significantly reduces the computational expense as compared to the iterative method, in which the same model years are run multiple times. A potential source of error in this method, though, is that the initial MALI run (from the initial condition to year one) does not contain information about the evolving bed topography, which could affect the resultant ice loading history (note that this error is also present in the iterative method). 

There are several scripts necessary to execute the alternating method. Two crucial script are (i) MALI-GIA_coupled_driver.sh: a bash script that calls the appropriate Python scripts needed for model interpolation, as well as contains information pertinent to the run (e.g. wall clock time, model duration, restart information), and (ii) mali-gia-driver.py: a Python script which loads the appropriate ice loading history (e.g. for year 10-11) that has been interpolated onto the GIA grid and calculates the so called `"Bueler Flux" by calling giascript.py, and ultimately generates the new uplift GIA uplft field that will then be interpolated back onto the MALI grid and used in the subsequent MALI run. Also vital to the method is giascript.py, which actually takes the MALI-generated ice loading history and calculates the appropriate viscoelastic uplift field. It should be noted that mali-gia-driver.py and giascript.py are used in both methods, but require manual operation in the iterative method.
