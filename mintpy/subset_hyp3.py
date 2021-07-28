#!/usr/bin/env python3
############################################################
# Program is part of MintPy                                #
# Copyright (c) 2013, Zhang Yunjun, Heresh Fattahi         #
# Author: Rowan Biessel, June 2021                         #
############################################################

import os
import glob
import json
import shutil
from osgeo import gdal
from pyproj import Transformer
import argparse
import sys
from typing import Tuple
import numpy as np


def create_parser(iargs=None):
    parser = argparse.ArgumentParser(description='Subset a stack of HyP3 Interferograms and generate a template MintPy directory structure. On completion, run: smallBaselineApp.py template.txt',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('path', help='Path to interferograms')
    parser.add_argument('-l', '--lat', dest='subset_lat',
                        type=float, nargs=2, help='subset range in latitude, S N', required=False)
    parser.add_argument('-L', '--lon', dest='subset_lon',
                        type=float, nargs=2, help='subset range in longitude: W E', required=False)
    parser.add_argument('-w', '--WGS84', default=False, action='store_true',
                        help="Reproject files to a lat-lon coordinate system")

    parser.add_argument(
        '-o', '--output', dest='output', help='Path to build directory structure', required=True)
    params = parser.parse_args(args=iargs)
    return params


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
mintpy.load.incAngleFile     = {os.path.join(directory, '*/*lv_theta.tif')}
    """

    with open(os.path.join(mintpy_path, 'template.txt'), 'w') as f:
        f.write(template)


def get_utm_zone(path: str) -> str:
    """
        Extract the UTM zone from a geotiff given by the path.
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


def correct_inc(theta_map: str):

    ds = gdal.Open(theta_map)
    band = ds.GetRasterBand(1)
    theta = band.ReadAsArray()

    # Calculation
    theta = (np.pi/2 - theta)

    # Re-write data
    driver = gdal.GetDriverByName("GTiff")

    outdata = driver.Create(
        theta_map, theta.shape[1], theta.shape[0], 1, band.DataType)

    # sets same geotransform as input
    outdata.SetGeoTransform(ds.GetGeoTransform())
    outdata.SetProjection(ds.GetProjection())  # sets same projection as input
    outdata.GetRasterBand(1).WriteArray(theta)
    outdata.GetRasterBand(1).SetNoDataValue(0)
    outdata.FlushCache()  # saves to disk!!
    outdata = None
    band = None
    ds = None


def move_and_clip(path: str, destination: str, utm: str, ul_utm, lr_utm):
    """
        Given a hyp3 geotiff or metadata txt file, clip it by a bounding box into the correct bounding box,
        or simply move the file if it is just a text file.
    """
    if '.txt' in path:
        shutil.copyfile(path, destination)
    elif '.tif' in path:
        options = gdal.TranslateOptions(
            projWin=[ul_utm[0], ul_utm[1], lr_utm[0], lr_utm[1]], projWinSRS=f'EPSG:{utm}', noData=0, creationOptions=['COMPRESS=DEFLATE'])

        gdal.Translate(destination, path, options=options)


def to_WGS84(path: str):
    if '.tif' in path:
        gdal.Warp(path, path, dstSRS='EPSG:4326')


def get_paths(paths: list or str):
    """
        Get a list of paths to the desired geotiffs from a list of glob patterns.
    """
    if type(paths) is str:
        paths = [paths]

    tiff_paths = []
    for path in paths:
        tiff_paths += glob.glob(path)

    tiff_paths.sort()
    return tiff_paths


def get_res(path: str):
    data = gdal.Open(path)
    geoTransform = data.GetGeoTransform()
    return geoTransform[1], geoTransform[5]


def get_bounds(path: str):

    data = gdal.Open(path)
    geoTransform = data.GetGeoTransform()
    minx = geoTransform[0]
    maxy = geoTransform[3]
    maxx = minx + geoTransform[1] * data.RasterXSize
    miny = maxy + geoTransform[5] * data.RasterYSize
    return [minx, miny, maxx, maxy]


def get_min_bounds(paths):

    paths_unwrapped = get_paths(paths)
    bounds = np.zeros((len(paths_unwrapped), 4))
    for i in range(len(paths_unwrapped)):
        bounds[i] = get_bounds(paths_unwrapped[i])

    print(bounds)
    min_bounds = (np.max(bounds.T[0]), np.max(bounds.T[1]), np.min(
        bounds.T[2]), np.min(bounds.T[3]))

    # Return ul_utm, lr_utm (x, y)
    ul_utm = [min_bounds[0], min_bounds[3]]
    lr_utm = [min_bounds[1], min_bounds[2]]
    return (ul_utm, lr_utm)


def main(iargs=None):

    parameters = create_parser(iargs)
    tiff_dir = parameters.path
    cwd = os.getcwd()

    # Find HyP3 Data
    paths_cor = f"{tiff_dir}/**/*_corr.tif"
    paths_unw = f"{tiff_dir}/**/*_unw_phase.tif"
    paths_dem = f"{tiff_dir}/**/*_dem.tif"
    paths_inc = f"{tiff_dir}/**/*_lv_theta.tif"
    paths_meta = f"{tiff_dir}/**/*[!.md].txt"

    paths = [paths_cor, paths_unw, paths_dem, paths_inc, paths_meta]

    if os.path.exists(tiff_dir):
        tiff_paths = get_paths(paths)
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

    # Parse Bounding Box
    utm = get_utm_zone(get_paths(paths_unw)[0])

    if parameters.subset_lat is None or parameters.subset_lon is None:
        print('Generating bounding box based on stack minimum extent')
        ul_utm, lr_utm = get_min_bounds(paths_unw)

    else:
        ul_lat = [parameters.subset_lon[0], parameters.subset_lat[1]]
        lr_lat = [parameters.subset_lon[1], parameters.subset_lat[0]]
        ul_utm = lonLat_to_utm(ul_lat[0], ul_lat[1], utm)
        lr_utm = lonLat_to_utm(lr_lat[0], lr_lat[1], utm)

    print(ul_utm, lr_utm)
    # return
    # Generate MintPy file structure with clipped Geotiffs
    for file in tiff_paths:
        destination = os.path.join(
            cwd, parameters.output, 'hyp3', os.path.basename(os.path.dirname(file)), os.path.basename(file))

        move_and_clip(file, destination, utm, ul_utm,
                      lr_utm)

        if 'lv_theta' in destination:
            correct_inc(file)

        if parameters.WGS84:
            to_WGS84(destination)

    # Generate the template file
    mintpy_path = os.path.join(cwd, parameters.output, 'mintpy')
    build_template(mintpy_path)


if __name__ == '__main__':
    main(sys.argv[1:])
