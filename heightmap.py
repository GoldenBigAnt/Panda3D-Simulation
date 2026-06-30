import random
import re
from enum import StrEnum, IntEnum
from itertools import cycle
from pathlib import Path

import pandas as pd
import numpy as np
import cv2
from panda3d.core import Point2

from constants import FolderPath


class Areas(IntEnum):

    LOWLAND = 50
    PLAIN = 90
    MOUNTAIN = 140
    SUBALPINE = 160
    ALPINE = 200


class Files(StrEnum):

    HEIGHTMAP = 'heightmap'
    TOP_RIGHT = 'top_right'
    TOP_LEFT = 'top_left'
    BOTTOM_LEFT = 'bottom_left'
    BOTTOM_RIGHT = 'bottom_right'

    @property
    def path(self):
        return f'{FolderPath.terrains}/{self.value}.png'

    @classmethod
    def get_tile_names(cls):
        return [mem for mem in cls if mem != cls.HEIGHTMAP]


class Tile:

    def __init__(self, path, center, quadrant, size):
        self.file = path
        self.center = center
        self.quadrant = quadrant
        self.size = size

    def get_nature_info(self):
        img = cv2.imread(self.file)

        for area in Areas:
            yield from self.generate(img, area)

    def generate(self, img, area):
        for x, y in set((x, y) for x, y, _ in zip(*np.where(img == area))):
            cx, cy = self.change_pixel_to_cartesian(x, y)
            yield cx, cy, area

    def count_pixels(self, start, end):
        img = cv2.imread(self.file)

        if start < 0:
            start = 0
        if end > 255:
            end = 255

        count = sum(np.count_nonzero(img == i) for i in range(start, end + 1))
        return count

    def change_pixel_to_cartesian(self, y, x):
        half = self.size / 2
        cx = x - half
        cy = -(y - half)
        cx += self.center.x
        cy += self.center.y
        return cx, cy


class HeightMap:

    def __init__(self):
        self.heightmap = Files.HEIGHTMAP.path
        self.tile_size = 256
        self.tiles = [tile for tile in self.get_tiles()]

        dirs = [ p for p in Path(FolderPath.terrains).glob("*") if p.is_dir() and re.fullmatch(r"\d+_\d+", p.name) ]
        random.shuffle(dirs)
        self.dirs = cycle(dirs)

    def get_tiles(self):
        half = self.tile_size / 2

        for file in Files.get_tile_names():
            match file:
                case Files.TOP_RIGHT:
                    pt = Point2(1, 1)
                    quadrant = 1
                case Files.TOP_LEFT:
                    pt = Point2(-1, 1)
                    quadrant = 2
                case Files.BOTTOM_LEFT:
                    pt = Point2(-1, -1)
                    quadrant = 3
                case Files.BOTTOM_RIGHT:
                    pt = Point2(1, -1)
                    quadrant = 4

            center = pt * half
            tile = Tile(file.path, center, quadrant, self.tile_size)
            yield tile

    def binarize(self):
        img_gray = cv2.cvtColor(cv2.imread(self.heightmap), cv2.COLOR_BGR2GRAY)
        _, img = cv2.threshold(img_gray, 0, 255, cv2.THRESH_OTSU)
        total = img.size
        white = cv2.countNonZero(img)
        black = (total - white)

        white_ratio = white / total
        black_ratio = black / total
        return white_ratio, black_ratio

    def create(self):
        dir = next(self.dirs)
        img = self.make_image(dir)
        cv2.imwrite(self.heightmap, img)
        h = w = self.tile_size + 1

        for tile in self.tiles:
            match Path(tile.file).stem:
                case Files.TOP_RIGHT:
                    cropped_img = img[:h, w - 1:w * 2 - 1]
                case Files.TOP_LEFT:
                    cropped_img = img[:h, :w]
                case Files.BOTTOM_LEFT:
                    cropped_img = img[h - 1:h * 2 - 1, :w]
                case Files.BOTTOM_RIGHT:
                    cropped_img = img[h - 1:h * 2 - 1, w - 1:w * 2 - 1]

            cv2.imwrite(tile.file, cropped_img)

    def make_image(self, dir):
        x, y = [int(s) for s in dir.name.split('_')]
        li = [[[0, 0], [1, 0]], [[0, 1], [1, 1]]]

        arr = np.concatenate(
            [np.concatenate([self.get_array(dir / f'{x + _x}_{y + _y}.txt') for _x, _y in sub], 1) for sub in li], 0
        )

        arr = arr.astype(np.float64)
        arr = np.interp(arr, (arr.min(), arr.max()), (0, self.tile_size * self.tile_size))
        arr = self.enlarge(arr)
        img = arr.astype(np.uint16)
        return img

    def get_array(self, path):
        expect_size = (self.tile_size, self.tile_size)

        df = pd.read_csv(path, header=None).replace('e', 0)
        if df.shape != expect_size:
            raise ValueError(f'Tile size is not {expect_size}')

        return df.values

    def enlarge(self, arr, edge=-1):
        bottom = arr[edge:, :]
        arr = np.concatenate([arr, bottom], 0)
        right = arr[:, edge:]
        arr = np.concatenate([arr, right], 1)
        return arr