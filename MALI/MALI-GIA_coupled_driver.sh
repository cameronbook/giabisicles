#!/usr/bin/env bash
#SBATCH --time=0:30:00   # walltime
#SBATCH --nodes=1   # number of nodes
##SBATCH --account=w19_icesheetfreshwater   # account name
#SBATCH --qos=interactive
#SBATCH --job-name=MALI-GIA   # job name

'''
Script to alternately run MALI and GIA in a data-coupled fashion.
'''


# ===================
# Set these locations and vars
GIAPATH=/Users/mhoffman/Documents/mpas-git/gia/giabisicles/
MALI=./landice_model

MALI_INPUT=landice_grid.nc
MALI_NL=landice.namelist
niter=10 # number of iterations
# ==================

# Other things you could change
GIAGRID=gia_grid.nc
MALILOAD=mali_load.nc
GIAOUTPUT=uplift_out.nc


source /users/mhoffman/setup_badger_mods.20181206.sh

for i in $(seq 1 $niter); do;

   echo "Starting iteration $i"

   # Check if initial run or restart
   #   TODO: Need to also check if this script is a restart itself
   if [ $i -eq 1 ]; then;
      INITIAL=true
   fi

   if [ $INITIAL = true ]; then;
      echo "This is the first iteration of a new simulation: Preparing new run."

      # Set up GIA mesh
      $GIAPATH/MALI/create_GIA_domain.py -m $MALI_INPUT -g $GIAGRID

      # Set restart flag to false, to be safe
      sed -i.SEDBACKUP "s/^config_do_restart.*/config_do_restart = .false./" $MALI_NL
      sed -i.SEDBACKUP "s/^config_start_time.*/config_start_time = '0000-01-01_00:00:00'/" $MALI_NL

      # Set GIA model args for a cold run
      GIAARGS="mali"
   else # not a restart
      # Set restart flag to restart (will be done every time, but that's ok)
      sed -i.SEDBACKUP "s/^config_do_restart.*/config_do_restart = .true./" $MALI_NL
      sed -i.SEDBACKUP "s/^config_start_time.*/config_start_time = 'file'/" $MALI_NL

      # Set GIA model args for a restart
      GIAARGS="mali r"
   fi


   # First run MALI
   echo "Starting MALI at time:"
   date
   srun -n 36 $MALI
   echo "Finisihed MALI at time:"
   date

   # interpolate ice load to GIA grid
   $GIAPATH/MALI/interp_MALI-GIA.py -d g -m $MALILOAD -g $GIAGRID

   # Run GIA model
   echo "Starting GIA model"
   $GIAPATH/giascript.py $GIAARGS
   echo "Finished GIA model"

   # interpolate bed topo to MALI grid
   $GIAPATH/MALI/interp_MALI-GIA.py -d m -m $MALI_INPUT -g $GIAOUTPUT

   # Stick new bed topo into restart file
   # (could also input it as a forcing file... not sure which is better)
   RSTTIME=`head -c 17 restart_timestamp | tail -c 16`
   RSTFILE=restart.$RSTTIME.nc
   cp $RSTFILE $RSTFILE.bak  # back up first (maybe remove later)
   ncks -A -v bedTopography uplift_mpas.nc $RSTFILE

   echo "Finished iteration $i"
done;




