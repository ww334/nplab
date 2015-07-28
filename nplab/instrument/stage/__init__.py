"""
Base class and interface for Stages.
"""

__author__ = 'alansanders, richardbowman'

from traits.api import HasTraits, Tuple, Button, Enum, Any, List, Str, Instance, Float, Dict, Array
from traitsui.api import View, Item, ButtonEditor, HGroup, VGroup, Spring, Group, VGrid
from pyface.api import ImageResource
import numpy as np
from collections import OrderedDict
import itertools
from nplab.instrument import Instrument
import time
import threading
from nplab.utils.gui import *
from PyQt4 import uic
from nplab.ui.ui_tools import UiTools
import nplab.ui
import inspect
from functools import partial
from nplab.utils.formatting import engineering_format


class Stage(Instrument):
    def __init__(self):
        self.axis_names = ('x', 'y', 'z')

    def move(self, pos, axis=None, relative=False):
        raise NotImplementedError("You must override move() in a Stage subclass")

    def move_rel(self, position, axis=None):
        """Make a relative move, see move() with relative=True."""
        self.move(position, axis=None, relative=True)

    def move_axis(self, pos, axis=None, relative=False):
        """Move along one axis."""
        if axis not in self.axis_names: raise ValueError(
            "{0} is not a valid axis, must be one of {1}".format(axis, self.axis_names))

        full_position = np.zeros((len(self.axis_names))) if relative else self.position
        full_position[self.axis_names.index(axis)] = pos
        self.move(full_position, relative=relative)

    def get_position(self, axis=None):
        raise NotImplementedError("You must override get_position in a Stage subclass.")

    def select_axis(self, iterable, axis=None):
        """Pick an element from a tuple, indexed by axis name."""
        assert axis in self.axis_names, ValueError("{0} is not a valid axis name.".format(axis))
        return iterable[self.axis_names.index(axis)]

    position = property(fget=get_position, doc="Current position of the stage")

    def is_moving(self, axes=None):
        """Returns True if any of the specified axes are in motion."""
        raise NotImplementedError("The is_moving method must be subclassed and implemented before it's any use!")

    def wait_until_stopped(self, axes=None):
        """Block until the stage is no longer moving."""
        while self.is_moving(axes=axes):
            time.sleep(0.01)

    def get_qt_ui(self):
        return StageUI(self)

    # TODO: stored dictionary of 'bookmarked' locations for fast travel


controls_base, controls_widget = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'stage.ui'))


class StageUI(UiTools, controls_base, controls_widget):
    update_ui = QtCore.pyqtSignal([int], [str])

    def __init__(self, stage, parent=None):
        assert isinstance(stage, Stage), "instrument must be a Stage"
        super(StageUI, self).__init__()
        self.stage = stage
        self.setupUi(self)
        self.step_size_values = step_size_dict(1e-9, 1e-3)
        self.step_size = [self.step_size_values[self.step_size_values.keys()[0]] for axis in stage.axis_names]
        self.create_axes_layout()
        self.update_ui[int].connect(self.update_positions)
        self.update_ui[str].connect(self.update_positions)
        self.update_pos_button.clicked.connect(partial(self.update_positions, None))

    def move_axis_absolute(self, position, axis):
        self.stage.move(position, axis=axis, relative=False)
        if type(axis) == str:
            self.update_ui[str].emit(axis)
        elif type(axis) == int:
            self.update_ui[int].emit(axis)

    def move_axis_relative(self, index, axis, dir=1):
        self.stage.move(dir * self.step_size[index], axis=axis, relative=True)
        if type(axis) == str:
            #    axis = QtCore.QString(axis)
            self.update_ui[str].emit(axis)
        elif type(axis) == int:
            self.update_ui[int].emit(axis)

    def zero_all_axes(self, axes):
        for axis in axes:
            self.move_axis_absolute(0, axis)

    def create_axes_layout(self, stack_multiple_stages='horizontal'):
        path = os.path.dirname(os.path.realpath(nplab.ui.__file__))
        icon_size = QtCore.QSize(12, 12)
        self.positions = []
        self.set_positions = []
        self.set_position_buttons = []
        for i, ax in enumerate(self.stage.axis_names):
            col = 4 * (i / 3)
            position = QtGui.QLineEdit('', self)
            position.setReadOnly(True)
            self.positions.append(position)
            set_position = QtGui.QLineEdit('0', self)
            self.set_positions.append(set_position)
            set_position_button = QtGui.QPushButton('', self)
            set_position_button.setIcon(QtGui.QIcon(os.path.join(path, 'go.png')))
            set_position_button.setIconSize(icon_size)
            set_position_button.resize(icon_size)
            set_position_button.clicked.connect(self.button_pressed)
            self.set_position_buttons.append(set_position_button)
            self.info_layout.addWidget(QtGui.QLabel(str(ax), self), i % 3, col)
            self.info_layout.addWidget(position, i % 3, col + 1)
            self.info_layout.addWidget(set_position, i % 3, col + 2)
            self.info_layout.addWidget(set_position_button, i % 3, col + 3)

            if i % 3 == 0:
                group = QtGui.QGroupBox('axes {0}'.format(1 + (i / 3)), self)
                layout = QtGui.QGridLayout()
                layout.setSpacing(6)
                group.setLayout(layout)
                self.axes_layout.addWidget(group, 0, i / 3)
                zero_button = QtGui.QPushButton('', self)
                zero_button.setIcon(QtGui.QIcon(os.path.join(path, 'zero.png')))
                zero_button.setIconSize(icon_size)
                zero_button.resize(icon_size)
                n = len(self.stage.axis_names) - i if len(self.stage.axis_names) - i < 3 else 3
                axes_set = self.stage.axis_names[i:i + n]
                zero_button.clicked.connect(partial(self.zero_all_axes, axes_set))
                layout.addWidget(zero_button, 1, 1)

            step_size_select = QtGui.QComboBox(self)
            step_size_select.addItems(self.step_size_values.keys())
            step_size_select.activated[str].connect(partial(self.on_activated, i))
            layout.addWidget(QtGui.QLabel(str(ax), self), i % 3, 5)
            layout.addWidget(step_size_select, i % 3, 6)
            if i % 3 == 0:
                layout.addItem(QtGui.QSpacerItem(12, 0), 0, 4)

            plus_button = QtGui.QPushButton('', self)
            plus_button.clicked.connect(partial(self.move_axis_relative, i, ax, 1))
            minus_button = QtGui.QPushButton('', self)
            minus_button.clicked.connect(partial(self.move_axis_relative, i, ax, -1))
            if i % 3 == 0:
                plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'right.png')))
                minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'left.png')))
                layout.addWidget(minus_button, 1, 0)
                layout.addWidget(plus_button, 1, 2)
            elif i % 3 == 1:
                plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'up.png')))
                minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'down.png')))
                layout.addWidget(plus_button, 0, 1)
                layout.addWidget(minus_button, 2, 1)
            elif i % 3 == 2:
                plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'up.png')))
                minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'down.png')))
                layout.addWidget(plus_button, 0, 3)
                layout.addWidget(minus_button, 2, 3)
            plus_button.setIconSize(icon_size)
            plus_button.resize(icon_size)
            minus_button.setIconSize(icon_size)
            minus_button.resize(icon_size)

    def button_pressed(self, *args, **kwargs):
        sender = self.sender()
        if sender in self.set_position_buttons:
            index = self.set_position_buttons.index(sender)
            axis = self.stage.axis_names[index]
            position = float(self.set_positions[index].text())
            self.move_axis_absolute(position, axis)

    def on_activated(self, index, value):
        # print self.sender(), index, value
        self.step_size[index] = self.step_size_values[value]

    @QtCore.pyqtSlot(int)
    # @QtCore.pyqtSlot('QString')
    @QtCore.pyqtSlot(str)
    def update_positions(self, axis=None):
        if axis is None:
            for axis in self.stage.axis_names:
                self.update_positions(axis=axis)
        else:
            i = self.stage.axis_names.index(axis)
            p = engineering_format(self.stage.position[i], base_unit='m', digits_of_precision=3)
            self.positions[i].setText(p)


def step_size_dict(smallest, largest, mantissas=[1, 2, 5]):
    """Return a dictionary with nicely-formatted distances as keys and metres as values."""
    log_range = np.arange(np.floor(np.log10(smallest)), np.floor(np.log10(largest)) + 1)
    steps = [m * 10 ** e for e in log_range for m in mantissas if smallest <= m * 10 ** e <= largest]
    return OrderedDict((engineering_format(s, 'm'), s) for s in steps)


# class Stage(HasTraits):
#    """Base class for controlling translation stages.
#
#    This class defines an interface for translation stages, it is designed to
#    be subclassed when a new stage is added.  The basic interface is very
#    simple: the property "position" encapsulates most of a stage's
#    functionality.  Setting it moves the stage and getting it returns the
#    current position: in both cases its value should be convertable to a numpy
#    array (i.e. a list or tuple of numbers is OK, or just a single number if
#    appropriate).
#
#    More detailed control (for example non-blocking motion) can be achieved
#    with the functions:
#    * get_position(): return the current position (as a np.array)
#    * move(pos, relative=False, blocking=True): move the stage
#    * move_rel(pos, blocking=True): as move() but with relative=True
#    * is_moving: whether the stage is moving (property)
#    * wait_until_stopped(): block until the stage stops moving
#    * stop(): stop the current motion (may be unsupported)
#
#    Subclassing nplab.stage.Stage
#    -----------------------------
#    The only essential commands to subclass are get_position() and _move(). The
#    rest will be supplied by the parent class, to give the functionality above.
#    _move() has the same signature as move, and is called internally by move().
#    This allows the stage class to emulate blocking/non-blocking moves.
#
#    NB if a non-blocking move is requested of a stage that doesn't support it,
#    a blocking move can be done in a background thread and is_moving should
#    return whether that thread is alive, wait_until_stopped() is a join().
#    """
#    axis_names = ["X","Y","Z"]
#    default_axes_for_move = ['X','Y','Z']
#    default_axes_for_controls = [('X','X'),'Z']
#    emulate_blocking_moves = False
#    emulate_nonblocking_moves = False
#    emulate_multi_axis_moves = False
#    last_position = Dict(Str,Float)
#    axes = List(Instance())
#
#    def get_position(self):
#        """Return the current position of the stage."""
#        raise NotImplementedError("The 'get_position' method has not been overridden.")
#        return np.zeros(len(axis_names))
#    def move_rel(self, pos, **kwargs):
#        """Make a relative move: see move(relative=True)."""
#        self.move(pos, relative=True, **kwargs)
#    def move(self, pos, axis=None, relative=False, blocking=True, axes=None, **kwargs):
#        """Move the stage to the specified position.
#
#        Arguments:
#        * pos: the position to move to, or the displacement to move by
#        * relative: whether pos is an absolute or relative move
#        * blocking: if True (default), block until the move is complete. If
#            False, return immediately.  Use is_moving() to determine when it
#            stops, or wait_until_stopped().
#        * axes: the axes to move.
#        TODO if pos is a dict, allow it to specify axes with keys
#        """
#        if hasattr(pos, "__len__"):
#            if axes is None:
#                assert len(pos)<len(self.default_axes_for_move), "More coordinates were passed to move than axis names."
#                axes = self.default_axes_for_move[0:len(pos)] #pick axes starting from the first one - allows missing Z coordinates, for example
#            else:
#                assert len(pos) == len(axes), "The number of items in the pos and axes arguments must match."
#            if self.emulate_multi_axis_moves: #break multi-axis moves into multiple single-axis moves
#                for p, a in zip(pos, axes):
#                    self.move(p, axis=a, relative=relative, blocking=blocking, **kwargs) #TODO: handle blocking nicely.
#        else:
#            if axis is None:
#                axis=self.default_axes_for_move[0] #default to moving the first axis
#
#        if blocking and self.emulate_blocking_moves:
#            self._move(pos, relative=relative, blocking=False, axes=axes, **kwargs)
#            try:
#                self.wait_until_stopped()
#            except NotImplementedError as e:
#                raise NotImplementedError("nplab.stage.Stage was instructed to emulate blocking moves, but wait_until_stopped returned an error.  Perhaps this is because is_moving has not been subclassed? The original error was "+e.message)
#        if not blocking and self.emulate_nonblocking_moves:
#            raise NotImplementedError("We can't yet emulate nonblocking moves")
#        self._move(pos, relative=relative, blocking=blocking, axes=axes)
#    def _move(self, position=None, relative=False, blocking=True, *args, **kwargs):
#        """This should be overridden to have the same method signature as move.
#        If some features are not supported (e.g. blocking) then it should be OK
#        to raise NotImplementedError.  If you ask for it with the emulate_*
#        attributes, many missing features can be emulated.
#        """
#        raise NotImplementedError("You must subclass _move to implement it for your own stage")
#    def is_moving(self, axes=None):
#        """Returns True if any of the specified axes are in motion."""
#        raise NotImplementedError("The is_moving method must be subclassed and implemented before it's any use!")
#    def wait_until_stopped(self, axes=None):
#        """Block until the stage is no longer moving."""
#        while(self.is_moving(axes=axes)):
#            time.sleep(0.1)
#        return True
##    def __init__(self):


class DummyStage(Stage):
    """A stub stage for testing purposes, prints moves to the console."""

    def __init__(self):
        super(DummyStage, self).__init__()
        self.axis_names = ('x1', 'y1', 'z1', 'x2', 'y2', 'z2')
        self._position = np.zeros((len(self.axis_names)), dtype=np.float64)

    def move(self, position, axis=None, relative=False):
        i = self.axis_names.index(axis)
        if relative:
            self._position[i] += position
        else:
            self._position[i] = position
            # print "stage now at", self._position

    def move_rel(self, position, axis=None):
        self.move(position, relative=True)

    def get_position(self, axis=None):
        if axis is not None:
            return self.select_axis(self.get_position(), axis)
        else:
            return self._position

    position = property(get_position)


if __name__ == '__main__':
    import sys
    from nplab.utils.gui import get_qt_app

    app = get_qt_app()
    ui = DummyStage().get_qt_ui()
    ui.show()
    sys.exit(app.exec_())
