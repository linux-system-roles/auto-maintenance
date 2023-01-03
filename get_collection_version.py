#!/usr/bin/python3

import yaml


def get_collection_version():
    with open("galaxy.yml", "r") as gf:
        galaxy = yaml.safe_load(gf)
        return galaxy["version"]


if __name__ == "__main__":
    print(get_collection_version())
