from PySide6.QtCore import QObject, Signal


class AccountState(QObject):
    """Central UI state for the currently active Google account."""

    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self._account_id = None

    @property
    def account_id(self):
        return self._account_id

    def set_account(self, account_id):
        account_id = int(account_id) if account_id is not None else None
        if self._account_id == account_id:
            return
        self._account_id = account_id
        self.changed.emit(account_id)

    def clear(self):
        self.set_account(None)
