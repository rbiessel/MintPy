#!/usr/bin/env python3

import os
import glob
import json  # for loads
import shutil
from numpy.core.fromnumeric import compress
from osgeo import gdal
from pyproj import Transformer
import matplotlib.pyplot as plt
import argparse
import sys
from typing import Tuple


def create_parser(iargs=None):
    parser = argparse.ArgumentParser(description='Subset a stack of HyP3 Interferograms. Run this before prep_hyp3.py',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('path', help='Path to interferograms')
    parser.add_argument('-l', '--lat', dest='subset_lat',
                        type=float, nargs=2, help='subset range in latitude', required=True)
    parser.add_argument('-L', '--lon', dest='subset_lon',
                        type=float, nargs=2, help='subset range in column\n\n', required=True)
    parser.add_argument(
        '-o', '--output', dest='output', help='Path to build directory structure', required=True)
    params = parser.parse_args(args=iargs)
    return params


def get_tiff_paths(paths):
    """
        Get a list of paths to the desired geotiffs
    """
    tiff_paths = glob.glob(paths)
    tiff_paths.sort()
    return tiff_paths


def build_template(mintpy_path):

    if os.path.exists(mintpy_path):
        try:
            shutil.rmtree(mintpy_path)
        except OSError as e:
            print("Error: %s - %s." % (e.filename, e.strerror))

    os.mkdir(mintpy_path)

    directory = os.path.join(mintpy_path, '../hyp3')

    template = f"""
mintpy.load.processor        = hyp3
# ---------interferogram datasets:
mintpy.load.unwFile          = {os.path.join(directory, '*/*unw_phase.tif')}
mintpy.load.corFile          = {os.path.join(directory, '*/*corr.tif')}
# ---------geometry datasets:
mintpy.load.demFile          = {os.path.join(directory, '*/*dem.tif')}
mintpy.load.incAngleFile     = {os.path.join(directory, '*/*inc_map.tif')}
    """

    with open(os.path.join(mintpy_path, 'template.txt'), 'w') as f:
        f.write(template)


def get_utm_zone(path: str) -> str:
    """
        Extract the UTM zone from a geotiff given by the path
    """

    info = gdal.Info(path, options=['-json'])
    info = json.dumps(info)
    info = (json.loads(info))['coordinateSystem']['wkt']
    utm = info.split('ID')[-1].split(',')[1][0:-2]
    return utm


def lonLat_to_utm(lon: float, lat: float, utm: str) -> Tuple[float, float]:
    """
        Use pyproj to convert a lat lon pair to an easting northing pair given a utm zone.
    """
    transformer = Transformer.from_crs(
        "epsg:4326", f'epsg:{utm}', always_xy=True)
    easting, northing = transformer.transform(lon, lat)
    return (easting, northing)


def move_and_clip(path: str, destination: str, utm: str, ul_utm, lr_utm):
    """
        Given a hyp3 geotiff or metadata txt file, clip it by a bounding box into the correct bounding box, 
        or simply move the file if it is just a text file.
    """
    if '.txt' in path:
        shutil.copyfile(path, destination)
    elif '.tif' in path:
        options = gdal.TranslateOptions(
            projWin=[ul_utm[0], ul_utm[1], lr_utm[0], lr_utm[1]], projWinSRS=f'EPSG:{utm}', noData=0)
        gdal.Translate(destination, path, options=options)


def main(iargs=None):

    parameters = create_parser(iargs)
    tiff_dir = parameters.path
    cwd = os.getcwd()

    # Find HyP3 Data
    paths_cor = f"{tiff_dir}/**/*_corr.tif"
    paths_unw = f"{tiff_dir}/**/*_unw_phase.tif"
    paths_dem = f"{tiff_dir}/**/*_dem.tif"
    paths_inc = f"{tiff_dir}/**/*_inc_map.tif"
    paths_meta = f"{tiff_dir}/**/*[!.md].txt"

    if os.path.exists(tiff_dir):
        tiff_paths = get_tiff_paths(
            paths_cor) + get_tiff_paths(paths_unw) + get_tiff_paths(paths_meta) + get_tiff_paths(paths_dem) + get_tiff_paths(paths_inc)

        print(f'Found {len(tiff_paths)} files')
        if len(tiff_paths) < 1:
            print(f"{tiff_dir} exists but contains no tifs.")
            print("You will not be able to proceed until tifs are prepared.")
            exit
    else:
        print(f"\n{tiff_dir} does not exist.")
        exit

    # Setup MintPy Directory
    if os.path.exists(parameters.output):
        print('Output directory already exists, overwriting...')
    else:
        os.mkdir(os.path.join(cwd, parameters.output))

    # Create a new folder for each interferogram
    interferograms = set([os.path.basename(
        os.path.dirname(path)) for path in tiff_paths])

    hyp3_path = os.path.join(cwd, parameters.output, 'hyp3')
    if not os.path.exists(hyp3_path):
        os.mkdir(hyp3_path)

    for name in interferograms:
        new_path = os.path.join(hyp3_path, name)
        if os.path.exists(new_path):
            try:
                shutil.rmtree(new_path)
            except OSError as e:
                print("Error: %s - %s." % (e.filename, e.strerror))
        os.mkdir(new_path)

    # Parse bounding Box
    ul_lat = [parameters.subset_lon[0], parameters.subset_lat[1]]
    lr_lat = [parameters.subset_lon[1], parameters.subset_lat[0]]
    utm = get_utm_zone(tiff_paths[0])
    ul_utm = lonLat_to_utm(ul_lat[0], ul_lat[1], utm)
    lr_utm = lonLat_to_utm(lr_lat[0], lr_lat[1], utm)

    # Generate MintPy file structure with clipped Geotiffs
    for file in tiff_paths:
        destination = os.path.join(
            cwd, parameters.output, 'hyp3', os.path.basename(os.path.dirname(file)), os.path.basename(file))
        move_and_clip(file, destination, utm, ul_utm, lr_utm)

    # Generate the template file
    mintpy_path = os.path.join(cwd, parameters.output, 'mintpy')
    build_template(mintpy_path)


if __name__ == '__main__':
    main(sys.argv[1:])
