import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix
import itertools

__all__ = ['plot_confusion_matrix']

def plot_confusion_matrix(y_true=None, y_pred=None, classes=None, normalize=True, title='Confusion matrix', automatically_close_figure=True, display_values=True, cmap='Blues', cm=None):
    """Plots a confusion matrix.

    The confusion matrix will be computed from y_true and y_pred or
    it can be given precomputed as the cm argument.
    y_true and y_pred will be ignored if the cm argument is not None.
    
    Modified from http://scikit-learn.org/stable/auto_examples/model_selection/plot_confusion_matrix.html#sphx-glr-auto-examples-model-selection-plot-confusion-matrix-py

    Keyword Arguments:
        y_true {list} -- Ground true (default: {None})
        y_pred {list} -- Predictions (default: {None})
        cm {matrix} -- Precalculated confusion matrix (default: {None})
        classes {list} -- List of names for the classes (default: {None})
        normalize {bool} -- Shows relative values instead of absolute (default: {True})
        title {str} -- Title of the graph (default: {'Confusion matrix'})
        automatically_close_figure {bool} -- Closes old figures before creating the plot (default: {True})
        display_values {bool} -- Draws matrix values in the graph (Disable if number of classes is high for visibility) (default: {True})
        cmap {str} -- Colormap to use (reference: pyplot colormaps) (default: {'Blues'})
    """
    if cm is None:
        cm = confusion_matrix(y_true, y_pred)
    title = title
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    if automatically_close_figure:
        plt.close()
    plt.imshow(cm, interpolation='nearest', cmap=plt.get_cmap(cmap))
    plt.title(title)
    #plt.colorbar()
    
    if classes is not None:
        tick_marks = np.arange(len(classes))
        plt.xticks(tick_marks, classes, rotation=45)
        plt.yticks(tick_marks, classes)

    if display_values:
        fmt = '.2f' if normalize else 'd'
        thresh = cm.max() / 2.
        for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
            plt.text(j, i, format(cm[i, j], fmt),
                    horizontalalignment="center",
                    color="white" if cm[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.show()
