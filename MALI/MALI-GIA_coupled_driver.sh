#!/usr/bin/env bash
#SBATCH --time=00:10:00   # walltime
#SBATCH --nodes=1   # number of nodes
##SBATCH --account=w19_icesheetfreshwater   # account name
#SBATCH --qos=standard
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
GIAPATH=.
MALI=./landice_model

MALI_INPUT=thwaites.4km.cleaned.nc
MALI_OUTPUT=output-cpl.nc
MALI_NL=namelist.landice
MALI_STREAMS=streams.landice
END_ITER=300
CPL_DT=1.0

RESTART_SCRIPT=0 # should be 0 or 1
# ==================

# Other things you could change
GIAGRID=gia_grid.nc
MALILOAD=mali_load.nc
GIAOUTPUT=uplift_GIA.nc


source /users/mhoffman/setup_badger_mods.20181206.sh
meshvars="latCell,lonCell,xCell,yCell,zCell,indexToCellID,latEdge,lonEdge,xEdge,yEdge,zEdge,indexToEdgeID,latVertex,lonVertex,xVertex,yVertex,zVertex,indexToVertexID,cellsOnEdge,nEdgesOnCell,nEdgesOnEdge,edgesOnCell,edgesOnEdge,weightsOnEdge,dvEdge,dcEdge,angleEdge,areaCell,areaTriangle,cellsOnCell,verticesOnCell,verticesOnEdge,edgesOnVertex,cellsOnVertex,kiteAreasOnVertex"


# Match output interval in MALI namelist to END_ITER & ensure format matches that needed by MALI
output_int=`python -c "output_int=int($CPL_DT); print '{0:04d}'.format(output_int)"`
sed -i.SEDBACKUP -e "/output-cpl.nc/,/<\/streams>/ s/output_interval.*/output_interval=\"$output_int-00-00_00:00:00\">/" $MALI_STREAMS
echo output_int=$output_int

# Match run duration in MALI namelist to coupling interval & ensure format matches that needed by MALI
cpl_dt_formatted=`python -c "cpl_dt_int=int($CPL_DT); print '{0:04d}'.format(cpl_dt_int)"`
sed -i.SEDBACKUP "s/config_run_duration.*/config_run_duration = '$cpl_dt_formatted-00-00_00:00:00'/" $MALI_NL
echo cpl_dt=$cpl_dt_formatted


if [ $RESTART_SCRIPT -eq 1 ]; then
  start_ind=`cat coupler_restart.txt`
  python -c "s=int($CPL_DT*$start_ind); print '{0:04d}-01-01_00:00:00'.format(s)" > restart_timestamp
  echo "new restart_timestamp value: " `cat restart_timestamp`
else
  start_ind=0
fi
echo start_ind=$start_ind

# if [ $RESTART_SCRIPT -eq 1 ]; then
#   # REDO THE FINAL ITERATION
#   RSTTIME=`head -c 20 restart_timestamp | tail -c 19`
#   RSTYR=`echo $RSTTIME|head -c 4`
#   echo RSTYR=$RSTYR
#   startyear=`python -c "newyr=int('$RSTYR'); print '{0:04d}'.format(newyr-$CPL_DT)"`
#   echo startyear=$startyear
#   echo " $startyear-01-01_00:00:00" > restart_timestamp
# else
#   startyear=0
# fi

mkdir iteration_archive

# for i in $(seq $startyear $END_ITER); do
for i in $(seq $start_ind $END_ITER); do

   echo ""; echo ""
   echo "=================================================="
   echo "Starting iteration $i"; echo ""; echo ""

   # Check if initial run or restart
   if [ $i -eq 0 ] && [ $RESTART_SCRIPT -eq 0 ]; then
      echo "This is the first iteration of a new simulation: Preparing new run."

      # Set up GIA mesh
      $GIAPATH/create_GIA_domain.py -m $MALI_INPUT -g $GIAGRID
      rc=$?; if [[ $rc != 0 ]]; then exit $rc; fi

      # Set restart flag to false, to be safe
      sed -i.SEDBACKUP "s/config_do_restart.*/config_do_restart = .false./" $MALI_NL
      sed -i.SEDBACKUP "s/config_start_time.*/config_start_time = '0000-01-01_00:00:00'/" $MALI_NL

      # Set GIA model args for a cold run
      GIAARGS="-d $CPL_DT"
   else # this is a restart
      echo "This iteration is a restart for MALI.  Preparing MALI restart run."
      # Set restart flag to restart (will be done every time, but that's ok)
      sed -i.SEDBACKUP "s/config_do_restart.*/config_do_restart = .true./" $MALI_NL
      sed -i.SEDBACKUP "s/config_start_time.*/config_start_time = 'file'/" $MALI_NL

      # Set GIA model args for a restart
      GIAARGS="-r -d $CPL_DT"
   fi

   mkdir iteration_archive/iter_$i

   # First run MALI
   echo "Starting MALI at time:"
   date
   srun -n 36 $MALI
   echo "Finished MALI at time:"
   date

   mv log.landice* iteration_archive/iter_${i}
   mv log.albany* iteration_archive/iter_${i}

   # interpolate ice load to GIA grid
   # copy second to last time of the needed fields.  This represents the prior year.
   ncks -A -d Time,-2 -v thickness,bedTopography,$meshvars $MALI_OUTPUT $MALILOAD
   rc=$?; if [[ $rc != 0 ]]; then exit $rc; fi
   cp $MALILOAD iteration_archive/iter_${i}

   $GIAPATH/interp_MALI-GIA.py -d g -m $MALILOAD -g $GIAGRID
   rc=$?; if [[ $rc != 0 ]]; then exit $rc; fi
   cp iceload.nc iteration_archive/iter_${i}

   # Run GIA model
   echo "Starting GIA model"
   $GIAPATH/mali-gia-driver.py $GIAARGS
   rc=$?; if [[ $rc != 0 ]]; then exit $rc; fi
   cp $GIAOUTPUT iteration_archive/iter_${i}
   echo "Finished GIA model"

   # interpolate bed topo to MALI grid
   $GIAPATH/interp_MALI-GIA.py -d m -m $MALI_INPUT -g $GIAOUTPUT
   rc=$?; if [[ $rc != 0 ]]; then exit $rc; fi
   cp bedtopo_update_mpas.nc iteration_archive/iter_${i}

   # Stick new bed topo into restart file
   # (could also input it as a forcing file... not sure which is better)
   RSTTIME=`head -c 20 restart_timestamp | tail -c 19 | tr : .`
   RSTFILE=restart.$RSTTIME.nc
   echo restart time=$RSTTIME
   echo restart filename=$RSTFILE

   if [ $RESTART_SCRIPT -eq 1 ]; then
#     let jj=${i}+1
#     cp $RSTFILE $RSTFILE.iter${jj}.bak  # back up first (maybe remove later)
     cp $RSTFILE iteration_archive/iter_${i}
   else
     cp $RSTFILE iteration_archive/iter_${i}
   fi

   ncks -A -v bedTopography bedtopo_update_mpas.nc $RSTFILE
   rc=$?; if [[ $rc != 0 ]]; then exit $rc; fi

   echo "Finished iteration $i"

   mid_iter=$i
   echo $mid_iter>coupler_restart.txt

done;
