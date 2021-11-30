#!/usr/bin/env python3
############################################################
# Program is part of MintPy                                #
# Copyright (c) 2013, Zhang Yunjun, Heresh Fattahi         #
# Author: Rowan Biessel, July 2021                         #
############################################################

from datetime import date, datetime
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
import requests
import json
import datetime
import urllib.request


def create_parser(iargs=None):
    parser = argparse.ArgumentParser(description='Download stack of SARVIEWS interferograms',
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument(
        '-o', '--output', dest='output', help='Path to build directory structure', required=True)

    parser.add_argument(
        '-p', '--path', dest='path', help='Granule Path to filter by', required=True)

    parser.add_argument(
        '-f', '--frame', dest='frame', help='Granule frame to filter by', required=True)

    parser.add_argument('-s', '--start', dest='start',
                        help='start Date', required=True)

    parser.add_argument('-e', '--end', dest='end',
                        help='start Date', required=True)

    parser.add_argument('-i', '--id', dest='id',
                        help='SARVIEWS Event ID', required=True)

    params = parser.parse_args(args=iargs)
    return params


def get_sarviews_event(id: str):
    """
        Query the SARVIEWS API to return info for a specific event.
        id - the sarviews event ID: https://sarviews-hazards.alaska.edu/Event/{id}
    """
    query = f'https://gm3385dq6j.execute-api.us-west-2.amazonaws.com/events/{id}'

    url = f'{query}'
    response = requests.get(url)
    data = json.loads(response.content)
    return data


def main(iargs=None):

    params = create_parser(iargs)
    event_data = get_sarviews_event(params.id)

    products = event_data['products']
    print(products[0])

    # paths = set([product['granules'][0]['path'] for product in products])
    # frames = set([product['granules'][0]['frame'] for product in products])

    print(len(products))

    # Filter by Path
    products = [product for product in products if str(
        product['granules'][0]['path']) == str(params.path)]

    # Filter by Frame
    products = [product for product in products if str(
        product['granules'][0]['frame']) == str(params.frame)]

    # Filter by InSAR
    products = [product for product in products if str(
        product['job_type']) == 'INSAR_GAMMA']

    if params.start:
        startDate = datetime.datetime.strptime(
            params.start, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)

        products = [product for product in products if
                    datetime.datetime.fromisoformat(product['granules'][0]['acquisition_date']) > startDate]

    if params.end:
        endDate = datetime.datetime.strptime(
            params.end, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)

        products = [product for product in products if
                    datetime.datetime.fromisoformat(product['granules'][0]['acquisition_date']) < endDate]

    print(f'{len(products)} products available after filtering by path frame')

    for product in products:
        url = product['files']['product_url']
        print(f'Downloading {url}')

        cwd = os.getcwd()
        name = os.path.basename(url)
        dest = os.path.join(cwd, params.output, name)

        urllib.request.urlretrieve(url, dest)


if __name__ == '__main__':
    main(sys.argv[1:])
