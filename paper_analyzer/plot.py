import matplotlib
import pandas as pd

matplotlib.use('Qt5Agg')
from matplotlib import pyplot

TEST_RESULTS_DIR = 'test_results'


# def algs_comparison_plot(test_run_name):
#     filename = TEST_RESULTS_DIR + '/' + test_run_name + '_performance.csv'
#     df = pd.read_csv(filename, skip_footer=1)
#     out_filename = TEST_RESULTS_DIR + '/' + test_run_name
#     pub_names = []
#     art_names = []
#     for name in df:
#         if 'art' in name:
#             art_names.append(name)
#         elif 'pub' in name:
#             pub_names.append(name)
#     pyplot.figure()
#     df[pub_names].plot(style=['.-'] * len(pub_names))
#     pyplot.xlabel('Word limit')
#     pyplot.ylabel('Algorithm execution time [s]')
#     pyplot.title('Suggest publications algorithm execution times')
#     pyplot.grid(True)
#     pyplot.legend(loc=2)
#     pyplot.savefig(out_filename + '_publication_performance.png')
#     pyplot.close()
#     pyplot.figure()
#     df[art_names].plot(style=['.-'] * len(pub_names))
#     pyplot.xlabel('Word limit')
#     pyplot.ylabel('Algorithm execution time [s]')
#     pyplot.title('Suggest articles algorithm execution times')
#     pyplot.grid(True)
#     pyplot.legend(loc=2)
#     pyplot.savefig(out_filename + '_article_performance.png')
#     pyplot.close()
#
#
# def effectiveness_test(test_run_name):
#     filename = TEST_RESULTS_DIR + '/' + test_run_name + '_effectiveness.csv'
#     df = pd.read_csv(filename)
#     out_filename = TEST_RESULTS_DIR + '/' + test_run_name
#     pyplot.figure()
#     # df.plot()
#     names = [name for name in df]
#     del names[3]  # don't need nmdcg
#     df = df[names]
#     df.plot(x=0, secondary_y=[names[2]], style=['.-'] * 2)
#     pyplot.xlabel('Word limit')
#     pyplot.ylabel('Modified discounted cumulated gain')
#     pyplot.title('Suggest article algorithm effectiveness')
#     pyplot.grid(True)
#     pyplot.savefig(out_filename + '_effectiveness.png')
#     pyplot.close()


def effectiveness_comparison_plot(*run_names):
    assert run_names is not None
    ax = None
    pyplot.figure()
    for name in run_names:
        filename = TEST_RESULTS_DIR + '/' + name + '_effectiveness.csv'
        df = pd.read_csv(filename)
        names = [name for name in df]
        del names[3]  # don't need nmdcg
        del names[1]  # don't need time
        df = df[names]
        ax = df.plot(ax=ax, x=0, style=['.-'] * 2)
    pyplot.xlabel('Maksymalna liczba słów kluczowych')
    pyplot.ylabel('mDCG')
    pyplot.grid(True)
    pyplot.savefig('mdcg.png')
    pyplot.close()


def time_comparison_plot(*run_names):
    assert run_names is not None
    ax = None
    pyplot.figure()
    for name in run_names:
        filename = TEST_RESULTS_DIR + '/' + name + '_effectiveness.csv'
        df = pd.read_csv(filename)
        names = [name for name in df]
        del names[3]  # don't need nmdcg
        del names[2]  # don't need mdcg
        df = df[names]
        ax = df.plot(ax=ax, x=0, style=['.-'] * 2)
    pyplot.xlabel('Maksymalna liczba słów kluczowych')
    pyplot.ylabel('Czas wykonywania')
    pyplot.grid(True)
    pyplot.savefig('time.png')
    pyplot.close()


def comparison_plot(*run_names):
    effectiveness_comparison_plot(*run_names)
    time_comparison_plot(*run_names)
