# Copyright 2016, FBPIC contributors
# Authors: Remi Lehe, Manuel Kirchen
# License: 3-Clause-BSD-LBNL
"""
This file is part of the Fourier-Bessel Particle-In-Cell code (FB-PIC)
It defines the structure and methods associated with particle tracking.
"""
import numpy as np
from numba import cuda

class ParticleTracker(object):
    """
    Class that stores particles ids and attributes new ids when necessary

    The ids are integers that are used in order to *uniquely* identify
    individual macroparticles (for the purpose of tracking, in postprocessing)

    Therefore, ids should be unique across all MPI processors. This is
    implemented here be having each MPI rank attribute ids of the form:
    mpi_rank + n * mpi_size
    """
    def __init__( self, comm_size, comm_rank, N ):
        """
        Initialize the ParticleTracker class

        Parameters
        ----------
        comm_size: int
            The number MPI ranks in the MPI communicator
        comm_rank: int
            The rank of the local MPI process
        N: int
            The total number of particles to which id should be attributed
        """
        # Prepare how to attribute new ids
        self.next_attributed_id = comm_rank
        self.id_step = comm_size
        # Everytime a new id is attributed, next_attributed_id is incremented
        # by id_step ; this way, all the particles (even across different
        # MPI proc) have unique id.

        # Initialize the array of ids
        new_next_attributed_id = self.next_attributed_id + N*self.id_step
        self.id = np.arange(
            start=self.next_attributed_id, stop=new_next_attributed_id,
            step=self.id_step, dtype=np.uint64 )
        self.next_attributed_id = new_next_attributed_id

        # Create a sorting buffer
        self.sorting_buffer = np.empty( N, dtype=np.uint64 )

    def send_to_gpu(self):
        """
        Transfer the tracking data from the CPU to the GPU
        """
        self.id = cuda.to_device( self.id )
        self.sorting_buffer = cuda.to_device( self.sorting_buffer )

    def receive_from_gpu(self):
        """
        Transfer the tracking data from the GPU to the CPU
        """
        self.id = self.id.copy_to_host()
        self.sorting_buffer = self.sorting_buffer.copy_to_host()

    def generate_new_ids( self, N ):
        """
        Generate `N` new unique ids (which are unique across all MPI ranks)
        Update the corresponding next attributed id

        Parameters
        ----------
        N: int
            The number of ids to generate
        """
        new_next_attributed_id = self.next_attributed_id + N*self.id_step
        new_ids = np.arange(
            start=self.next_attributed_id, stop=new_next_attributed_id,
            step=self.id_step, dtype=np.uint64 )
        self.next_attributed_id = new_next_attributed_id
        return( new_ids )

    def overwrite_ids( self, pid, comm ):
        """
        Overwrite the particle ids and update the corresponding next
        attributed id (so that it is still unique across all MPI ranks)

        Parameters
        ----------
        pid: 1darray of uint64
            The new array of particle id (has the same length as self.id)
        comm: an fbpic.BoundaryCommunicator object
            This is used in order to communicate global information on the
            ids across all MPI ranks
        """
        # Get the new ids
        self.id[:] = pid

        # Set self.next_attributed_id, so that attributed ids are still unique
        # In order to do this, find the maximum of all pid across processors
        if len(pid) > 0:
            local_id_max = pid.max()
        else:
            local_id_max = 0
        if comm.mpi_comm is None:
            global_id_max = local_id_max
        else:
            local_id_max_list = comm.mpi_comm.allgather( local_id_max )
            global_id_max = max( local_id_max_list )
        # Find the next_attibuted_id: has to be of the form
        # comm.rank + n*self.id_step
        n = int( (global_id_max - comm.rank)/self.id_step ) + 1
        self.next_attibuted_id = comm.rank + n*self.id_step
