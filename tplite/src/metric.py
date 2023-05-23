import argparse
import logging
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    parser.add_argument("--tpl_dependency", type=valid_path, required=True,
                        help="path to the tpl dependency data")
    parser.add_argument("--ground_truth", type=valid_path, required=True,
                        help="path to the groudtruth data")
    return parser.parse_args()


def main():
    logger.info("[+] load the groundtruth data")
    ground_truth_set = set()
    df = pd.read_csv(args.ground_truth, sep=",", header=0)
    for data in df.itertuples():
        ground_truth_set.add((data[1], data[2]))

    logger.info("[+] load the tpl dependency data")
    tpl_dep_set = set()
    df = pd.read_csv(args.tpl_dependency, sep=",", header=0)
    for data in df.itertuples():
        ground_truth_set.add((data[1], data[2]))

    intersection = ground_truth_set & tpl_dep_set
    logger.info(f"[+] groundtruth data: {len(ground_truth_set)}")
    logger.info(f"[+] test data: {len(tpl_dep_set)}")
    logger.info(f"[+] intersection: {len(intersection)}")

    prec = len(intersection) / len(tpl_dep_set)
    recall = len(intersection) / len(ground_truth_set)
    logger.info(f"[+] precision: {prec}")
    logger.info(f"[+] recall: {recall}")
    logger.info(f"[+] f1: {2 * prec * recall / (prec + recall)}")


if __name__ == '__main__':
    args = parameter_parser()
    main()
