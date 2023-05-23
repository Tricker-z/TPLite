# TPLite
TPLite: TPL dependency scanner with origin detection and centrality analysis



##  Environment

* python \>= 3.8

* tree-sitter >= 0.20.1
* networkx >= 3.0



##  Usage

### Build with local CLI

```shell
$ git submodule update --init --recursive

$ python -m venv .env
$ source .env/bin/activate
$ pip install -r requirements.txt
```



### Quick Start

1. Extract the source function code with [tree-sitter](https://github.com/tree-sitter/tree-sitter) and generate the signatures (`extractor/extract_func.py`)

```shell
$ python extractor/extract_func.py        \
		--tpls_url data/input/tpls_1k_url.csv \
		--output data/func_sigs/
```

* *--tpls_url:* path of the csv file of all tpl urls with the format -  `tpl_uuid,repo_url`
* *--output:* output directory of the tpl signature

**Output format:** tpl signature with tpl_uuid as the file name in json

```json
{
 "func_sha256": [
  "func_src_code",
  {
   "tag_name_1": [
    "tag_commit_time_1",
    "tag_func_file_path_1"
   ],
   "tag_name_2": [
    "tag_commit_time_2",
    "tag_func_file_path_2"
   ]
  }
 ], 
}
```



2. Generate the tpl dependencies with TPLite (`tplite/src/resolve_dep.py`)

```shell
$ python tplite/src/resolve_dep.py      \
		--tpl_sigs data/func_sigs/          \
		--tpl_name data/input/tpls_name.csv \
		--store_path output/                \
		--cpu 30
```

* *--tpl_sigs:* tpl signatures (output of step-1)
* *--tpl_name:* path of the csv file of all tpl names with the format - `tpl_uuid,tpl_name`
* *--store_path:* output directory including the tpl dependencies (tpl_dep.csv) and other meta data

