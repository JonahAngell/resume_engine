"""Small in-process caches. The app runs as a single worker, so process memory is enough."""


class BoundedCache:
    """A dict that drops its oldest entry once it holds more than `maxsize` items."""

    def __init__(self, maxsize: int) -> None:
        self.maxsize = maxsize
        self._items: dict = {}

    def get(self, key, default=None):
        return self._items.get(key, default)

    def set(self, key, value) -> None:
        self._items[key] = value
        while len(self._items) > self.maxsize:
            self._items.pop(next(iter(self._items)))

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
