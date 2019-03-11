#!/usr/bin/env bash
#SBATCH --time=01:00:00   # walltime
#SBATCH --nodes=1   # number of nodes
##SBATCH --account=w19_icesheetfreshwater   # account name
##SBATCH --qos=standard
#SBATCH --qos=interactive
#SBATCH --job-name=MALI-GIA   # job name

# Script to alternately run MALI and GIA in a data-coupled fashion.
# There are assumptions of a one year coupling interval.
#
# Workflow is like:
#
# 0       1       2
# | MALI  |
# |------>|
# |       |
# |  GIA  |
# |------>|
#         |
#         | MALI  |
#         |------>|
#         |       |
#         |  GIA  |
#         |------>|


# ===================
# Set these locations and vars
GIAPATH=~/giabisicles/MALI
MALI=./landice_model

MALI_INPUT=thwaites.4km.cleaned.nc
MALI_OUTPUT=output.nc
MALI_NL=namelist.landice
end_yr=300

RESTART_RUN=0 # should be 0 or 1
# ==================

# Other things you could change
GIAGRID=gia_grid.nc
MALILOAD=mali_load
GIAOUTPUT=uplift_out


source /users/mhoffman/setup_badger_mods.20181206.sh
meshvars="latCell,lonCell,xCell,yCell,zCell,indexToCellID,latEdge,lonEdge,xEdge,yEdge,zEdge,indexToEdgeID,latVertex,lonVertex,xVertex,yVertex,zVertex,indexToVertexID,cellsOnEdge,nEdgesOnCell,nEdgesOnEdge,edgesOnCell,edgesOnEdge,weightsOnEdge,dvEdge,dcEdge,angleEdge,areaCell,areaTriangle,cellsOnCell,verticesOnCell,verticesOnEdge,edgesOnVertex,cellsOnVertex,kiteAreasOnVertex"


if [ $RESTART_RUN -eq 1 ]; then
  RSTTIME=`head -c 20 restart_timestamp | tail -c 19`
  RSTYR=`echo $RSTTIME|head -c 4`
  echo RSTYR=$RSTYR
  startyear=`python -c "newyr=int('$RSTYR'); print '{0:04d}'.format(newyr-1)"`
  echo startyear=$startyear
  echo " $startyear-01-01_00:00:00" > restart_timestamp
else
  startyear=0
fi


for i in $(seq $startyear $end_yr); do

   echo ""; echo ""
   echo "=================================================="
   echo "Starting iteration $i"; echo ""; echo ""

   # Check if initial run or restart
   if [ $i -eq 1 ] && [ $RESTART_RUN -eq 0 ]; then
      echo "This is the first iteration of a new simulation: Preparing new run."

      # Set up GIA mesh
      $GIAPATH/create_GIA_domain.py -m $MALI_INPUT -g $GIAGRID

      # Set restart flag to false, to be safe
      sed -i.SEDBACKUP "s/config_do_restart.*/config_do_restart = .false./" $MALI_NL
      sed -i.SEDBACKUP "s/config_start_time.*/config_start_time = '0000-01-01_00:00:00'/" $MALI_NL

      # Set GIA model args for a cold run
      GIAARGS=""
   else # this is a restart
      echo "This iteration is a restart.  Preparing restart run."
      # Set restart flag to restart (will be done every time, but that's ok)
      sed -i.SEDBACKUP "s/config_do_restart.*/config_do_restart = .true./" $MALI_NL
      sed -i.SEDBACKUP "s/config_start_time.*/config_start_time = 'file'/" $MALI_NL

      # Set GIA model args for a restart
      GIAARGS="-r"
   fi


   # First run MALI
   echo "Starting MALI at time:"
   date
   srun -n 36 $MALI
   echo "Finished MALI at time:"
   date

   # interpolate ice load to GIA grid
   # copy second to last time of the needed fields.  This represents the prior year.
   ncks -A -d Time,-2 -v thickness,bedTopography,$meshvars $MALI_OUTPUT $MALILOAD.nc
   cp $MALILOAD.nc ${MALILOAD}.iter${i}.nc
   $GIAPATH/interp_MALI-GIA.py -d g -m $MALILOAD.nc -g $GIAGRID
   cp iceload.nc iceload.iter${i}.nc

   # Run GIA model
   echo "Starting GIA model"
   $GIAPATH/mali-gia-driver.py $GIAARGS
   cp $GIAOUTPUT.nc ${GIAOUTPUT}.iter${i}.nc
   echo "Finished GIA model"

   # interpolate bed topo to MALI grid
   $GIAPATH/interp_MALI-GIA.py -d m -m $MALI_INPUT -g $GIAOUTPUT.nc
   cp bedtopo_update_mpas.nc bedtopo_update_mpas.iter${i}.nc

   # Stick new bed topo into restart file
   # (could also input it as a forcing file... not sure which is better)
   RSTTIME=`head -c 20 restart_timestamp | tail -c 19 | tr : .`
   RSTFILE=restart.$RSTTIME.nc
   echo restart time=$RSTTIME
   echo restart filename=$RSTFILE

   if [ $RESTART_RUN -eq 1 ]; then
     let jj=${i}+1
     cp $RSTFILE $RSTFILE.iter${jj}.bak  # back up first (maybe remove later)
   else
     cp $RSTFILE $RSTFILE.iter${i}.bak  # back up first (maybe remove later)
   fi

   ncks -A -v bedTopography bedtopo_update_mpas.nc $RSTFILE

   echo "Finished iteration $i"

done;
