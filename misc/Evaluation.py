import numpy as np
import matplotlib.pyplot as _plt
import sklearn.metrics as _metrics

from .plot_confusion_matrix import plot_confusion_matrix as _plot_confusion_matrix

class Evaluation:
    def __init__(self, history=None, history_series=('loss', 'acc',)):
        """Evaluation constructor
        
        Keyword Arguments:
            history: An optional history object from keras fit() that will be used to draw graphs.
            history_series: List of series names that are recorded in the keras history.
        """
        self.history = history
        self.history_series = history_series
        if history is not None:
            for metric in history_series:
                assert metric in self.history, "Specified series is not actually in the history"

    def evaluate(self, y_true, y_pred, classes, average=None, sample_weights=None, ignore_binary_average=True):
        """Creates a full evaluation
        
        Arguments:
            y_true {list} -- list of true labels
            y_pred {list} -- list of predicted labels
            classes {list} -- Dictionary of {class label:class names} or if a list of class names is provided, then the names will be assigned their index in the array as the label.
        
        Keyword Arguments:
            average {str} -- Type of average for scores. If None: 'binary' will be picked for binary, and 'macro' for non-binary inputs. ('binary', 'micro', 'macro') (default: {None})
            sample_weights {list} -- Optional list of weights for each sample of y_true/y_pred (default: {None})
            ignore_binary_average {bool} -- If true, then the average metrics will not be shown in the case of a binary classification (default: {True})
        """
        assert average in ('micro', 'macro', 'binary', None)
        assert isinstance(y_true, np.ndarray), "y_true must be an numpy array."
        assert isinstance(y_pred, np.ndarray), "y_pred must be an numpy array."
        if isinstance(classes, list):
            classes = dict(zip(range(len(classes)), classes))
        if average is None:
            average = 'binary' if len(classes) == 2 else 'macro'
        self.classes = classes
        self.average = average
        self.evaluation = {
            'scores': {
                'metrics': ['accuracy', 'f1', 'recall', 'precision'],
                'labels': ['average (%s)' % average] + list(classes.values()),
                'score_matrix': np.array([
                    [_metrics.accuracy_score(y_true, y_pred),
                     _metrics.f1_score(y_true, y_pred, average=average),
                     _metrics.recall_score(y_true, y_pred, average=average),
                     _metrics.precision_score(y_true, y_pred, average=average)],
                ] + [
                    [metric_func(y_true == label, y_pred == label)
                    for metric_func
                    in (_metrics.accuracy_score,
                        _metrics.f1_score,
                        _metrics.recall_score,
                        _metrics.precision_score)]
                    for label in classes]),
                'orientation': 'labels-first'
            },
            'confusion_matrix': _metrics.confusion_matrix(y_true, y_pred, sample_weight=sample_weights)
        }
        if ignore_binary_average:
            self.evaluation['scores']['labels'] = self.evaluation['scores']['labels'][1:]
            self.evaluation['scores']['score_matrix'] = self.evaluation['scores']['score_matrix'][1:]
        return self
    
    def plot(self, transpose_scores=True):
        """Plots the evaluation
        
        Keyword Arguments:
            transpose_scores {bool} -- Wether bar graphs should be transposed. (default: {True})
        """
        # plot loss and other series
        if self.history is not None:            
            _plt.figure()
            for i, series in enumerate(self.history_series):
                # plot series
                _plt.subplot(len(self.history_series), 1, i+1)
                _plt.plot(self.history[series], '-x')
                legend = ['Train']
                if 'val_%s' % series in self.history:
                    _plt.plot(self.history['val_%s' % series], '-o')
                    legend.append('Validation')
                _plt.xticks(range(len(self.history[series])))
                _plt.xlabel("Epoch")
                _plt.ylabel('Accuracy' if series == 'acc' else series.capitalize())
                _plt.locator_params(axis='y', nbins=4)
                _plt.locator_params(axis='x', nbins=10)
                _plt.legend(legend)
            _plt.show()

        # plot confusion matrix
        _plot_confusion_matrix(cm=self.evaluation['confusion_matrix'], classes=list(self.classes.values()))

        # plot metrics
        _plt.figure()
        ax = _plt.subplot(111)

        series_labels = self.evaluation['scores']['labels']
        x_ticks = self.evaluation['scores']['metrics']
        score_matrix = self.evaluation['scores']['score_matrix']

        if transpose_scores:
            series_labels, x_ticks = x_ticks, series_labels
            score_matrix = score_matrix.T

        N = len(series_labels)
        width = 1. / N
        indices = np.arange(len(x_ticks))*2
        
        rects_for_legend = []
        for i, scores in enumerate(score_matrix):
            rects = ax.bar(indices + i*width, scores, width=width)
            rects_for_legend.append(rects[0])

        ax.set_title('Scores')
        ax.set_ylabel('Score')
        ax.locator_params(axis='y', nbins=5)
        ax.set_xticklabels(x_ticks)
        ax.set_xticks(indices + width*1.5) # *1.5 because there are 4 metrics and I want to position it in the center
        ax.legend(rects_for_legend, series_labels, loc='lower center', ncol=N)
        _plt.show()
