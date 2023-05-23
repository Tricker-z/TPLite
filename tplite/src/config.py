
THRESHOLD = 0.01  # identify reuse relation

CENTRALITY_THRE = 1.5

IN_DEGREE_THRE = 5

BLACK_SET = {'src', 'external', 'third_party', '3rdparty', 'extern', 'common',
             'tests', 'thirdparty', 'modules', 'third-part', 'deps', 'source',
             'components', 'extra'}

EXTERN_FLAG = {'external', 'third_party', '3rdparty', 'extern', 'components', 'third-party',
               'thirdparty', 'deps'}

SPECIAL_CASE = {
    'sqlite' : '782f163e5a74474f99967ff440bdd4ad',
    'sqlite3': '782f163e5a74474f99967ff440bdd4ad',
    'catch'  : 'dc143ab5bedd496e8554538300fda899',
    'bzip2'  : 'c9c39614cb17478a99f05129608c23a5'
}
