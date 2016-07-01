from multiprocessing import Process,Condition,Lock,Pipe,Connection
import memoryInitializer
import numpy as np

import pycuda.driver as cuda
import pycuda.autoinit
from pycuda.compiler import SourceModule
class GPUCalculator(Process):
  
    def __init__(self, header, _inputPipe, _outputPipe):
        self.inputPipe = _inputPipe
        self.outputPipe = _outputPipe 

        #unpack header info
        self.totalCols = header[0]
        self.totalRows = header[1]
        self.cellsize = header[2]
        self.NODATA = header[3]

        #Get GPU information
        self.freeMem = cuda.mem_get_info()[0] * .5 * .8
        self.maxPossRows = np.int(np.floor(self.freeMem / (8 * self.totalCols)))
        # set max rows to smaller number to save memory usage
        if self.totalRows < self.maxPossRows:
            print "reducing max rows to fit on GPU"
            self.maxPossRows = self.totalRows

        #Allocate space for data in main memory and GPU memory
        self.to_gpu_buffer = cuda.pagelocked_empty((self.maxPossRows , self.totalCols), np.float64)
        self.from_gpu_buffer = cuda.pagelocked_empty((self.maxPossRows , self.totalCols), np.float64)
        self.data_gpu = cuda.mem_alloc(self.to_gpu_buffer.nbytes)
        self.result_gpu = cuda.mem_alloc(self.from_gpu_buffer.nbytes)

    def run(self, kernelType='simple slope'):
        while True:
            try self.recv_data():
                self.process_data(self.get_kernel(kernelType))
                self.write_data()
            except EOFError:
                break

    def recv_data(self):
        #num_bytes = self.to_gpu_buffer.nbytes
        #while num_bytes > 0:
        #    num_bytes -=
        pass

    def process_data(self, mod):
        pass

    def write_data(self):
        pass

    def stop(self):
        print "Stopping..."
        exit(1)

    def get_kernel(self, kernelType):
        if kernelType = 'simple slope':
            return SourceModule("""
                    #include <math.h>
                    #include <stdio.h>

                    typedef struct{
                            double pixels_per_thread;
                            double NODATA;
                            unsigned long long ncols;
                            unsigned long long nrows;
                            unsigned long long npixels;
                    } passed_in;

                    /************************************************************************************************
                            GPU only function that gets the neighbors of the pixel at curr_offset
                            stores them in the passed-by-reference array 'store'
                    ************************************************************************************************/
                    __device__ int getKernel(double *store, double *data, unsigned long offset, passed_in *file_info){
                            //NOTE: This is more or less appropriated from Liam's code. Treats edge rows and columns
                            // as buffers, they will be dropped.
                            if (offset < file_info->ncols || offset >= (file_info->npixels - file_info->ncols)){
                                    return 1;
                            }
                            unsigned long y = offset % file_info->ncols; //FIXME: I'm not sure why this works...
                            if (y == (file_info->ncols - 1) || y == 0){
                                    return 1;
                            }
                            // Grab neighbors above and below.
                            store[1] = data[offset - file_info->ncols];
                            store[7] = data[offset + file_info->ncols];
                            // Grab right side neighbors.
                            store[2] = data[offset - file_info->ncols + 1];
                            store[5] = data[offset + 1];
                            store[8] = data[offset + file_info->ncols + 1];
                            // Grab left side neighbors.
                            store[0] = data[offset - file_info->ncols - 1];
                            store[3] = data[offset - 1];
                            store[6] = data[offset + file_info->ncols - 1];
                            /* return a value otherwise it throws a warning expression not having effect */
                            return 0;
                    }

                    /************************************************************************************************
                            CUDA Kernel function to calculate the slope of pixels in 'data' and stores them in 'result'
                            handles a variable number of calculations based on its thread/block location 
                            and the size of pixels_per_thread in file_info
                    ************************************************************************************************/
                    __global__ void simple_slope(double *data, double *result, passed_in *file_info){
                            /* get individual thread x,y values */
                            unsigned long long x = blockIdx.x * blockDim.x + threadIdx.x;
                            unsigned long long y = blockIdx.y * blockDim.y + threadIdx.y; 
                            unsigned long long offset = (gridDim.x*blockDim.x) * y + x; 
                            //gridDim.x * blockDim.x is the width of the grid in threads. This moves us to the correct
                            //block and thread.
                            unsigned long long i;
                            /* list to store 3x3 kernel each pixel needs to calc slope */
                            double nbhd[9];
                            /* iterate over assigned pixels and calculate slope for all of them */
                            /* do npixels + 1 to make last row(s) get done */
                            for(i=0; i < file_info -> pixels_per_thread + 1 && offset < file_info -> npixels; ++i){	    
                                    if(data[offset] == file_info -> NODATA){
                                            result[offset] = file_info -> NODATA;
                                    } else {
                                            int q = getKernel(nbhd, data, offset, file_info);
                                            if (q) {
                                                    result[offset] = file_info->NODATA;
                                            }
                                            else{
                                                    for(q = 0; q < 9; ++q){
                                                            if(nbhd[q] == file_info -> NODATA){
                                                                    nbhd[q] = data[offset];
                                                            }
                                                    }
                                                    double dz_dx = (nbhd[2] + (2*nbhd[5]) + nbhd[8] - (nbhd[0] + (2*nbhd[3]) + nbhd[6])) / (8*10);
                                                    double dz_dy = (nbhd[6] + (2*nbhd[7]) + nbhd[8] - (nbhd[0] + (2*nbhd[1]) + nbhd[2])) / (8*10);
                                                    result[offset] = atan(sqrt(pow(dz_dx, 2) + pow(dz_dy, 2)));
                                            }
                                    }
                                    offset += (gridDim.x*blockDim.x) * (gridDim.y*blockDim.y);
                                    //Jump to next row

                            }
                    }
                    """)
            else:
                print "CUDA kernel not implemented"
                self.stop()
