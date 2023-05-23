#!/usr/bin/env python3
# coding=utf-8
import argparse
import re
import subprocess
from util import is_test_file, is_source_file, is_header_file, is_c_extension, parse_files_with_tag
import json
import logging
import os
import sys
import pandas as pd

from pathlib import Path

sys.path.append(os.getcwd())


current_path = os.getcwd()
clone_path = current_path + "/repos/"

logger = logging.getLogger('main')
func_dict = {}


def valid_path(path: str) -> Path:
    try:
        abspath = Path(path)
    except Exception as e:
        raise Exception(f"Invalid input path: {path}") from e
    if not abspath.exists():
        raise Exception(f"{abspath} not exist")
    return abspath.resolve()


def parameter_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tpls_url", type=valid_path,
                        default="./data/input/tpls_1k_url.csv")
    parser.add_argument("--output", type=valid_path,
                        default="./data/func_sigs/")
    return parser.parse_args()


def get_repo(url_file, save_dir, noheader=True):
    df = pd.read_csv(url_file, names=["tpl_id", "url"], header=0)
    os.chdir(clone_path)

    for tpl_id, url in zip(df["tpl_id"], df["url"]):
        save_path = os.path.join(save_dir, f"{tpl_id}.json")
        if os.path.exists(save_path):
            continue
        repo_name = url.split('/')[-1].replace(".git", "")
        logging.info("Parsing %s" % repo_name)
        clone_command = "git clone " + url
        clone_result = subprocess.check_output(
            clone_command, stderr=subprocess.STDOUT, shell=True
        ).decode()
        repo_path = clone_path + repo_name
        os.chdir(repo_path)

        tag_command = "git tag"
        tag_result = subprocess.check_output(
            tag_command, stderr=subprocess.STDOUT, shell=True
        ).decode()

        data_command = 'git log --tags --simplify-by-decoration --pretty="format:%ai %d"'
        data_result = subprocess.check_output(
            data_command, stderr=subprocess.STDOUT, shell=True
        ).decode()
        tag_time = {}
        for tag_info in data_result.split('\n'):
            m = re.match(r".*tag: (?P<tag_name>.*)[),]", tag_info)
            tag_time[
                m.groupdict()['tag_name'].split(',')[0]
            ] = " ".join(tag_info.split()[:2])
        print(tag_time)
        try:
            if tag_result != "":
                for tag in str(tag_result).split('\n'):
                    if tag == '':
                        continue
                    print("tag: ", tag)
                    checkout_command = "git checkout -f " + tag
                    subprocess.check_output(
                        checkout_command, stderr=subprocess.STDOUT, shell=True)
                    tasks, rel_paths = [], []
                    for root, _, files in os.walk(repo_path, topdown=False):
                        for name in files:
                            file_path = os.path.join(root, name)
                            file_path_rel = os.path.relpath(
                                file_path, repo_path)
                            if is_test_file(file_path_rel):
                                continue
                            if (
                                is_source_file(name) or
                                (not noheader and is_header_file(name))
                            ) and not is_test_file(name):
                                tasks.append((
                                    file_path,
                                    not is_c_extension(name),
                                    file_path_rel
                                ))
                                rel_paths.append(file_path_rel)
                    parse_files_with_tag(tasks, tag, tag_time[tag], func_dict)
            else:
                print("TODO - for repository with only master")
        except Exception as e:
            logger.fatal('[*] Error: %s' % str(e))
        with open(save_path, 'w') as fp:
            json.dump(func_dict, fp, indent=1)
    os.chdir(current_path)


def main():
    os.mkdir(clone_path)
    get_repo(
        args.tpls_url,
        args.output
    )


if __name__ == "__main__":
    args = parameter_parser()
    main()
