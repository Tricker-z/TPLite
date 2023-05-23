import argparse
import base64
import json
import logging
import os
import pickle
import pandas as pd
import time
import config
import networkx as nx

from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path, PurePath
from tqdm import tqdm

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
    parser.add_argument("--tpl_sigs", type=valid_path, required=True,
                        help="path to the directory of tpl signatures")
    parser.add_argument("--tpl_name", type=valid_path, required=True,
                        help="data path to the tpl name")
    parser.add_argument("--store_path", type=str, default="./output/",
                        help="save path to the results")
    parser.add_argument("--cpu", type=int, default=1)
    return parser.parse_args()


def obtain_tpl_sigs():
    '''Construct the tpl signatures'''
    if tpl_sigs_path.exists():
        logger.info("[+] load the tpl signatures")
        with open(tpl_sigs_path, 'rb') as fp:
            tpl_sigs = pickle.load(fp)
    else:
        logger.info("[+] construct the tpl signatures")
        tpl_sigs = dict()
        for tpl_sig in tqdm(args.tpl_sigs.glob("*"), total=tpl_num):
            tpl_sigs[tpl_sig.name] = json.load(tpl_sig.open())
        # dump the tpl signatures
        with open(tpl_sigs_path, 'wb') as fp:
            pickle.dump(tpl_sigs, fp)
    return tpl_sigs


def obtain_func_info():
    '''Construct the function data'''
    if func_info_path.exists():
        logger.info("[+] load the info of functions")
        with open(func_info_path, 'rb') as fp:
            func_info_all = pickle.load(fp)
    else:
        logger.info("[+] construct the info of functions")
        func_info_all = defaultdict(dict)
        for tpl_id, tpl_sig in tqdm(tpl_sigs.items(), total=len(tpl_sigs)):
            for func_hash, func_infos in tpl_sig.items():
                func_src_code = func_infos[0]
                func_tags: dict = func_infos[1]
                func_tag_infos = []
                for tag_name, func_tag_info in func_tags.items():
                    # (func tag time, func file path)
                    commit_time = time.strptime(
                        func_tag_info[0],
                        "%Y-%m-%d %H:%M:%S"
                    )
                    func_file_path = func_tag_info[1]
                    func_tag_infos.append((
                        commit_time,
                        func_file_path
                    ))
                func_tag_infos.sort(key=lambda x: x[0])
                func_info_all[func_hash][tpl_id] = func_tag_infos[0]
        with open(func_info_path, 'wb') as fp:
            pickle.dump(func_info_all, fp)
    return func_info_all


def obtain_func_origin():
    '''Construct the origin tpl of functions'''
    if func_origin_path.exists():
        logger.info("[+] load the origin tpl of functions")
        with open(func_origin_path, 'rb') as fp:
            func_origin = pickle.load(fp)
    else:
        logger.info("[+] construct the origin tpl of functions")
        # parse the origin tpl
        func_origin = dict()
        for func_id, func_info in tqdm(func_info_all.items(), total=len(func_info_all)):
            if len(func_info) <= 1:
                continue
            tpl_time = list()
            seg_count = defaultdict(int)
            tpl_name_id = defaultdict(list)
            for tpl_id, info in func_info.items():
                extern_flag = False
                seg_set = set()
                tpl_name = tpl2name[tpl_id]
                func_path = PurePath(info[1].lower())
                commit_time = info[0]
                for seg in func_path.parent.parts + (func_path.stem,):
                    if seg in config.EXTERN_FLAG:
                        extern_flag = True
                    if seg in config.BLACK_SET or seg == tpl_name:
                        continue
                    seg_set.add(seg)
                for seg in seg_set:
                    seg_count[seg] += 1
                if not extern_flag:
                    tpl_info = (tpl_id, commit_time)
                    tpl_name_id[tpl_name].append(tpl_info)
                    tpl_time.append(tpl_info)
            # check the function path
            if len(seg_count):
                tpl_candidate = list()
                lower_count = 1 if len(func_info) <= 3 else 2
                seg_sort = sorted(seg_count.items(),
                                  reverse=True, key=lambda x: x[1])
                for seg, count in seg_sort:
                    if count < lower_count:
                        break
                    if seg in config.SPECIAL_CASE:
                        func_origin[func_id] = (config.SPECIAL_CASE[seg], 0)
                        break
                    if seg in tpl_name_id:
                        tpl_candidate.extend(tpl_name_id[seg])
                if func_id not in func_origin and len(tpl_candidate):
                    tpl_candidate.sort(key=lambda x: x[1])
                    func_origin[func_id] = (tpl_candidate[0][0], 0)

            if func_id not in func_origin and len(tpl_time):
                # check function birth time
                tpl_time.sort(key=lambda x: x[1])
                func_origin[func_id] = tpl_time[0]

        with open(func_origin_path, 'wb') as fp:
            pickle.dump(func_origin, fp)

    return func_origin


def resolve_source_relation(tpl_id):
    '''Identify reused functions'''
    res = dict()
    tpl_intersection = defaultdict(set)
    tpl_sig_s = tpl_sigs[tpl_id]
    for func_hash, func_info in tpl_sig_s.items():
        origin_time = func_info[1]
        if func_hash not in func_origin.keys():
            continue
        tpl_id_x, origin_time_x = func_origin[func_hash]
        if tpl_id_x == tpl_id:
            continue
        if origin_time_x == 0 or origin_time_x < origin_time:
            tpl_intersection[tpl_id_x].add(func_hash)
    res[tpl_id] = tpl_intersection
    return res


def main():
    global tpl_num, tpl2name
    global tpl_sigs, tpl_sigs_path
    global func_info_all, func_info_path
    global func_origin, func_origin_path

    tpl_list = os.listdir(args.tpl_sigs)
    tpl_num = len(tpl_list)
    store_path = Path(args.store_path)
    if not store_path.exists():
        store_path.mkdir(parents=True)

    # load the tpl name
    tpl2name = dict()
    df = pd.read_csv(args.tpl_name, sep=',', header=0)
    for data in df.itertuples():
        tpl2name[data[1]] = data[2].lower()

    tpl_sigs_path = store_path.joinpath("tpl_sigs.pkl")
    tpl_sigs = obtain_tpl_sigs()

    func_info_path = store_path.joinpath("func_info_all.pkl")
    func_info_all = obtain_func_info()

    func_origin_path = store_path.joinpath("func_origin.pkl")
    func_origin = obtain_func_origin()

    logger.info("[+] resolve the source relation")
    pool = Pool(args.cpu)
    tpl_intersection_all = dict()
    with tqdm(total=tpl_num) as pbar:
        for res in pool.imap_unordered(resolve_source_relation, tpl_list):
            tpl_intersection_all.update(res)
            pbar.update()
    pool.close()
    pool.join()

    logger.info("[+] dump the intersection results")
    with open(store_path.joinpath("tpl_inter.pkl"), 'wb') as fp:
        pickle.dump(tpl_intersection_all, fp)

    # count all reused functions for each tpl
    tpl_reuse_set = defaultdict(set)
    for tpl_id_s, tpl_intersection in tpl_intersection_all.items():
        for reuse_list in tpl_intersection.values():
            tpl_reuse_set[tpl_id_s] |= set(reuse_list)

    recall_relation = set()
    tpl_reuse = defaultdict(list)
    for tpl_id_s, tpl_intersection in tpl_intersection_all.items():
        for tpl_id_x, reuse_list in tpl_intersection.items():
            # exclude the reused count
            func_num_x = len(tpl_sigs[tpl_id_x])
            reused_num_x = len(tpl_reuse_set[tpl_id_x])
            tpl_len_x = len(tpl_sigs[tpl_id_x]) - len(tpl_reuse_set[tpl_id_x])
            if tpl_len_x < 1:
                continue
            if len(reuse_list) / func_num_x >= config.THRESHOLD * func_num_x / reused_num_x:
                recall_relation.add((tpl_id_s, tpl_id_x))
                tpl_reuse[tpl_id_s].append(tpl_id_x)

    # handle the bidirection false
    remove_set = set()
    for tpl_id_s, tpl_id_x in recall_relation:
        if (tpl_id_x, tpl_id_s) not in recall_relation:
            continue
        reuse_list_s = tpl_intersection_all[tpl_id_s][tpl_id_x]
        reuse_list_x = tpl_intersection_all[tpl_id_x][tpl_id_s]
        if len(reuse_list_s) <= len(reuse_list_x):
            remove_set.add((tpl_id_s, tpl_id_x))
        else:
            remove_set.add((tpl_id_x, tpl_id_s))
    recall_relation = recall_relation - remove_set

    # eliminate the cycle
    def splite_cycle(input_list):
        res = list()
        start_id = input_list[0]
        for i in range(1, len(input_list)):
            res.append((start_id, input_list[i]))
            start_id = input_list[i]
        res.append((start_id, input_list[0]))
        return res

    timeout = 300
    start_time = time.time()
    remove_set = set()
    graph = nx.DiGraph(list(recall_relation))
    while time.time() - start_time < timeout:
        cycles = nx.simple_cycles(graph)
        cycle_count = len(list(cycles))
        if cycle_count == 0:
            break
        cycle_edge_count = defaultdict(int)
        for cycle in nx.simple_cycles(graph):
            for edge in splite_cycle(cycle):
                cycle_edge_count[edge] += 1
        edge_count_sort = sorted(
            cycle_edge_count.items(),
            key=lambda x: x[1],
            reverse=True
        )
        for edge, _ in edge_count_sort:
            graph.remove_edge(*edge)
            remove_set.add(edge)
            logger.info(
                f"[+] Total cycles: {cycle_count}, remove edge: {edge}")
            break

    # pagerank & in-degree
    dep_graph = nx.DiGraph()
    for tpl_id_s, tpl_id_x in recall_relation:
        reuse_num = len(tpl_intersection_all[tpl_id_s][tpl_id_x])
        func_num_x = len(tpl_sigs[tpl_id_x])
        dep_graph.add_edge(tpl_id_s, tpl_id_x, weight=reuse_num / func_num_x)

    logger.info(f"[+] dependency graph has {len(dep_graph.nodes)} nodes and "
                f"{len(dep_graph.edges)} edges")

    def in_degree_centrality(graph):
        s = 1.0 / (len(graph) - 1)
        centrality = {n: d * s for n, d in graph.in_degree(weight='weight')}
        return centrality

    in_degrees = in_degree_centrality(dep_graph)
    page_ranks = nx.pagerank(dep_graph, alpha=0.85, weight='weight')

    remove_set = set()
    for tpl_id_s, tpl_id_x in recall_relation:
        if (
            in_degrees[tpl_id_s] > config.IN_DEGREE_THRE and
            page_ranks[tpl_id_x] /
                in_degrees[tpl_id_x] > config.CENTRALITY_THRE
        ):
            remove_set.add((tpl_id_s, tpl_id_x))
    recall_relation = recall_relation - remove_set

    save_path = store_path.joinpath("tpl_dep.csv")
    with open(save_path, "w") as fp:
        fp.write("origin_tpl_uuid,reuse_tpl_uuid\n")
        for tpl_id_s, tpl_id_x in recall_relation:
            fp.write(f"{tpl_id_s},{tpl_id_x}\n")

    logger.info("[*] finish the recall relation")


if __name__ == '__main__':
    args = parameter_parser()
    main()
