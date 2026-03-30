from abc import ABC, abstractmethod

from .utils import clone_shape, insert_shape, remove_shape, replace_shape


class Command(ABC):
    """Base command interface for undoable shape mutations."""

    @abstractmethod
    def execute(self):
        """Apply the command."""

    @abstractmethod
    def undo(self):
        """Revert the command."""


class AddShapeCommand(Command):
    """Insert one newly created shape into the model."""

    def __init__(self, controller, shape, idx=None):
        self.controller = controller
        self.shape = clone_shape(shape)
        self.idx = idx

    def execute(self):
        if self.idx is None:
            self.idx = len(self.controller.model.shapes)
        self.idx = self.controller._insert_shape_direct(
            self.idx,
            self.shape,
            select_new=True,
        )

    def undo(self):
        self.controller._remove_shape_direct(self.idx)


class DeleteShapeCommand(Command):
    """Remove one or more shapes and optionally reselect them on undo."""

    def __init__(self, controller, deleted_items, restore_selection=False):
        self.controller = controller
        self.deleted_items = [
            (idx, clone_shape(shape)) for idx, shape in deleted_items
        ]
        self.restore_selection = restore_selection

    def execute(self):
        for idx, _shape in sorted(self.deleted_items, key=lambda item: item[0], reverse=True):
            self.controller._remove_shape_direct(idx)
        self.controller.deselect()

    def undo(self):
        for idx, shape in sorted(self.deleted_items, key=lambda item: item[0]):
            self.controller._insert_shape_direct(idx, shape)
        if self.restore_selection and self.deleted_items:
            self.controller.select_shape(self.deleted_items[0][0])


class MoveShapeCommand(Command):
    """Commit one completed translation."""

    def __init__(self, controller, idx, old_shape, new_shape):
        self.controller = controller
        self.idx = idx
        self.old_shape = clone_shape(old_shape)
        self.new_shape = clone_shape(new_shape)

    def execute(self):
        self.controller._replace_shape_direct(self.idx, self.new_shape)

    def undo(self):
        self.controller._replace_shape_direct(self.idx, self.old_shape)


class ModifyPropertyCommand(Command):
    """Commit one shape property edit."""

    def __init__(self, controller, idx, old_shape, new_shape):
        self.controller = controller
        self.idx = idx
        self.old_shape = clone_shape(old_shape)
        self.new_shape = clone_shape(new_shape)

    def execute(self):
        self.controller._replace_shape_direct(self.idx, self.new_shape)

    def undo(self):
        self.controller._replace_shape_direct(self.idx, self.old_shape)


class CommandHistory:
    """Tracks executed commands and supports undo/redo."""

    def __init__(self, controller):
        self.controller = controller
        self.undo_stack = []
        self.redo_stack = []

    @property
    def can_undo(self):
        return bool(self.undo_stack)

    @property
    def can_redo(self):
        return bool(self.redo_stack)

    def execute(self, command):
        command.execute()
        self.undo_stack.append(command)
        self.redo_stack.clear()
        self.controller._sync_history_state()

    def undo(self):
        if not self.undo_stack:
            return False
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        self.controller._sync_history_state()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        command = self.redo_stack.pop()
        command.execute()
        self.undo_stack.append(command)
        self.controller._sync_history_state()
        return True
