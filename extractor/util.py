import re
import os
import tlsh
import logging
from hashlib import sha256
from tqdm import tqdm
from tree_sitter import Language, Parser

logger = logging.getLogger('main')

Language.build_library(
    'build/my-languages.so',
    [
        'vendor/tree-sitter-cpp',
        'vendor/tree-sitter-c'
    ]
)

'''
In general, these paths won't contain codes that will be compiled into the binary.
But don't filter the library that is designed for testing or documenting
"3rdparty", "3rd_party", "third_party", "thirdparty" can be filtered in the future
'''
TEST_NAMES = ["test", "example", "examples", "demo",
              "simd", "docs", "doc", "documents", "document"]
SRC_EXTENSIONS = [".cc", ".c", ".cpp", ".cxx", ".c++", ".cp", ".cci"]
HEADER_EXTENSIONS = [".h", ".hpp"]


def time_format(sec):
    hours = sec // 3600
    sec = sec - (hours * 3600)
    minutes = sec // 60
    seconds = sec - (minutes * 60)
    return '{:02}h {:02}m {:02}s'.format(int(hours), int(minutes), int(seconds))


def is_test_file(arg):
    paths = arg.lower().split('/')
    for name in TEST_NAMES:
        if name in paths:
            return True
    return False


def is_c_extension(arg):
    tmp = arg.lower()
    # .h file maybe c or cpp, use cpp parser to parse it
    return tmp.endswith('.c')


def is_header_file(arg):
    tmp = arg.lower()
    for ext in HEADER_EXTENSIONS:
        if tmp.endswith(ext):
            return True
    return False


def is_source_file(arg):
    tmp = arg.lower()
    for ext in SRC_EXTENSIONS:
        if tmp.endswith(ext):
            return True
    return False


def replace_macro(file_cont, preproc_info, invalid_interval):  # this is a temporary solution
    ok_chars = ["(", ")", " ", "\n", "\t", ",", "{", "}", "=", ";", "\"", "'", "\\", "[",
                "]"]  # chars that can near a strings
    ok_chars = list(map(ord, ok_chars))
    spaces = ['\t', ' ']
    spaces = list(map(ord, spaces))
    bad_heads = [b'#define', b'# define', b'#ifdef',
                 b'# ifdef', b'#ifndef', b'# ifndef']
    macro_strs = []
    for macro_name_str in preproc_info:
        macro_value_str = preproc_info[macro_name_str]
        macro_name = macro_name_str.encode('utf-8', errors='ignore')
        if type(macro_value_str) == str:
            macro_value = macro_value_str.encode('utf-8', errors='ignore')
            start_offset = 0
            found_idx = file_cont.find(macro_name, start_offset)
            while found_idx != -1:
                if (found_idx != 0 and file_cont[found_idx - 1] not in ok_chars) or (
                        found_idx + len(macro_name) != len(file_cont) and file_cont[
                            found_idx + len(macro_name)] not in ok_chars) or found_idx in invalid_interval:
                    start_offset = found_idx + 1
                    found_idx = file_cont.find(macro_name, start_offset)
                    continue
                    # do not replace if macro_name is after a #define
                idx = found_idx - 1
                while idx > 0 and file_cont[idx] in spaces:
                    idx -= 1
                drop = False
                for bad_head in bad_heads:
                    if idx >= len(bad_head) - 1 and file_cont[idx + 1 - len(bad_head): idx + 1] == bad_head:
                        drop = True
                        break
                if drop:
                    start_offset = found_idx + 1
                    found_idx = file_cont.find(macro_name, start_offset)
                    continue
                file_cont = file_cont[:found_idx] + macro_value + \
                    file_cont[found_idx + len(macro_name):]
                macro_strs.append(macro_value_str)
                start_offset = found_idx + 1 + \
                    len(macro_value) - len(macro_name)
                invalid_interval = list(
                    map(lambda a: a + len(macro_value) - len(macro_name) if a > found_idx else a,
                        invalid_interval)
                )
                found_idx = file_cont.find(macro_name, start_offset)
    return file_cont, list(set(macro_strs))


def get_code_line_after_clean(code):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ""
        else:
            return s

    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    code = re.sub(pattern, replacer, code)
    code = "".join([c for c in code.splitlines(True) if c.strip()])
    code = code.strip()
    return code, code.count("\n")


def normalize(code):
    '''Normalizing the function code.'''
    return re.sub(r"[\n\r\t\{\}\s]", "", code)


def computeTlsh(string):
    '''LSH in centris'''
    string = str.encode(string)
    hs = tlsh.forcehash(string)
    return hs


def is_similar(func_hash, func_hash_compare, cut_off=30):
    distance = int(tlsh.diffxlen(func_hash, func_hash_compare))
    return distance <= cut_off and distance > 0


def parse_files_with_tag(tasks, tag, time, func_dict):
    json_cache = None
    ret = []
    for location, iscpp, rel_path in tqdm(tasks, total=len(tasks)):
        logger.debug('Parsing file: %s' % location)
        file_cont = bytes(open(location, 'rb').read())
        file_hash = sha256(file_cont).hexdigest()
        if json_cache is not None and file_hash in json_cache:
            logger.debug('Cache hit %s' % location)
            ret.append(json_cache[file_hash])
        else:
            try:
                file_info = get_file_info(
                    file_cont,
                    iscpp
                )
                functions = file_info['functions']
                for function in functions:
                    clean_src = normalize(
                        get_code_line_after_clean(function['src'])[0]
                    ).encode('utf-8')
                    func_hash = sha256(clean_src).hexdigest()
                    if func_hash not in func_dict:
                        func_dict[func_hash] = [function['src'], dict()]
                    tag_dict = func_dict[func_hash][1]
                    tag_dict[tag] = [time, rel_path]
            except Exception as e:
                logger.fatal('[*] Error: %s' % str(e))
                ret.append({'status': 0, 'sha256': file_hash})
    return ret


def get_preproc_info(lang, node, file_cont):
    preproc_info = {}
    # step 1: parse stringize
    query_macro_func = lang.query("""(preproc_function_def) @macro_func""")
    query_macro_params = lang.query('''(preproc_params) @macro_args''')
    query_identifier = lang.query('''(identifier) @identifier''')
    query_macro_cont = lang.query('''(preproc_arg) @macro_cont''')
    captures = query_macro_func.captures(node)
    for c in captures:
        captures_params = query_macro_params.captures(c[0])
        captures_cont = query_macro_cont.captures(c[0])
        captures_name = query_identifier.captures(c[0])
        if (captures_params == [] or captures_cont == [] or captures_name == []):
            logging.warning(
                'preproc_function_def [%s] invalid' % file_cont[c[0].start_byte: c[0].end_byte])
            continue
        params = query_identifier.captures(captures_params[0][0])
        if len(params) == 0:
            continue  # no param or parse error
        func_cont = file_cont[captures_cont[0]
                              [0].start_byte: captures_cont[0][0].end_byte]
        macro_name = file_cont[captures_name[0]
                               [0].start_byte: captures_name[0][0].end_byte]
        for i, param in enumerate(params):
            param_str = file_cont[param[0].start_byte: param[0].end_byte]
            if (b'#' + param_str) in func_cont and (
                    b'##' + param_str) not in func_cont:  # FIXME: ##x and ##x all exists
                preproc_info[macro_name.decode('utf-8', errors='ignore')] = i
    # step 2: parse macro defined strings
    query = lang.query(
        """(preproc_def name:(identifier) @name value:(preproc_arg) @value)""")
    captures = query.captures(node)
    def_name = ""
    for c in captures:
        if c[1] == "name":
            def_name = file_cont[c[0].start_byte: c[0].end_byte].decode(
                'utf-8', errors='ignore')
        elif c[1] == "value":
            cont = file_cont[c[0].start_byte: c[0].end_byte].decode(
                'utf-8', errors='ignore').strip()
            if len(cont) > 0 and cont[0] == '"' and cont[-1] == '"':
                preproc_info[def_name] = cont
    return preproc_info


def get_func_info(lang, node, file_cont):
    func_name_blst = ["if"]
    funcs = []
    query_def = lang.query("""(function_definition) @func""")
    query_dec = lang.query("""(function_declarator) @func_dec""")
    query_parameter_list = lang.query("""(parameter_list) @param_list""")

    captures_def = query_def.captures(node)
    for c in captures_def:
        # locate the `function_declarator` node
        captures_decl = query_dec.captures(c[0])
        if len(captures_decl) == 0:
            logging.warning('function [%s] has no declarator' %
                            file_cont[c[0].start_byte: c[0].end_byte])
            continue
        node_func_decl = captures_decl[0][0]

        # locate the `parameter_list` node
        captures_parameter_list = query_parameter_list.captures(node_func_decl)
        if len(captures_parameter_list) == 0:
            logging.warning('function [%s] has no parameter' %
                            file_cont[c[0].start_byte: c[0].end_byte])
            continue
        node_parameter_list = captures_parameter_list[0][0]

        # locate the function name
        node_func_name = node_parameter_list.prev_sibling
        # skip the `comment` nodes
        while node_func_name is not None:
            if node_func_name.type != 'comment':
                break
            node_func_name = node_func_name.prev_sibling

        if node_func_name is None:
            logging.warning(
                'function [%s] has no name' %
                file_cont[c[0].start_byte: c[0].end_byte]
            )
            continue
        identifier = node_func_name
        st, ed = identifier.start_byte, identifier.end_byte
        fname = file_cont[st:ed].decode('utf-8', errors='ignore')
        if fname in func_name_blst:
            continue

        src = file_cont[c[0].start_byte: c[0].end_byte]
        start_line_number = file_cont[:c[0].start_byte].decode(
            'utf-8', errors='ignore'
        ).count('\n') + 1
        hsh = sha256(src).hexdigest()
        to_append = {
            "name": fname,
            "src": src.decode('utf-8', errors='ignore'),
            "sha256": hsh,
            "stln": start_line_number
        }
        funcs.append(to_append)
    return funcs


def filter_huge_const_arr(file_cont):
    if b'# E-mail..................: [Ciph3r_blackhat@yahoo.com]' in file_cont:
        return b''
    if len(file_cont) > 20000 and re.search(b'([0-9a-fA-FxX\s\n]+,){10000,}', file_cont):
        logger.fatal('[*] Huge const array found and replace it!')
        file_cont = re.sub(b'([0-9a-fA-FxX\s\n]+,){10000,}', b'', file_cont)
        return file_cont
    return file_cont


def get_file_info(
    file_cont,
    iscpp=False,
    do_preproc=False,
    preproc_info=None,
    so_path=None
):
    if so_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        c_language = Language('%s/build/my-languages.so' % base_dir, 'c')
        cpp_language = Language('%s/build/my-languages.so' % base_dir, 'cpp')
    else:
        c_language = Language(so_path, 'c')
        cpp_language = Language(so_path, 'cpp')
    parser_c = Parser()
    parser_c.set_language(c_language)
    parser_cpp = Parser()
    parser_cpp.set_language(cpp_language)
    file_cont = filter_huge_const_arr(file_cont)

    tree_c = parser_c.parse(file_cont)
    tree_cpp = parser_cpp.parse(file_cont)

    # parse with c or cpp parser
    if iscpp:
        lang = cpp_language
        tree = tree_cpp
    else:
        lang = c_language
        tree = tree_c
    if do_preproc:
        return get_preproc_info(lang, tree.root_node, file_cont)

    # replace macro with strings and reparse with tree_sitter
    if preproc_info is not None and preproc_info != {}:
        query = lang.query("""(string_literal) @str""")
        captures = query.captures(tree.root_node)
        invalid_interval = set()
        for c in captures:  # TODO: can use interval tree here
            for i in range(c[0].start_byte, c[0].end_byte):
                invalid_interval.add(i)
        file_cont, _ = replace_macro(
            file_cont, preproc_info, invalid_interval
        )

        tree_c = parser_c.parse(file_cont)
        tree_cpp = parser_cpp.parse(file_cont)
        if iscpp:
            tree = tree_cpp
        else:
            tree = tree_c

    funcs = get_func_info(lang, tree.root_node, file_cont)
    ret = {
        "functions": funcs
    }

    return ret
