"""TUI for the BOOKS.md table.

Groups titles by the tag column. You can add a category, then insert or
delete book rows. Book suggestions come from the files in the folders.
It does not move files on disk.

    python books_tui.py
    python books_tui.py path\\to\\BOOKS.md
"""

import os
import shutil
import sys
from pathlib import Path


def trunc(text, width):
    if width <= 0:
        return ''
    if len(text) <= width:
        return text
    if width == 1:
        return text[:1]
    return text[:width - 1] + '\u2026'


def header_line(left, right, width):
    if len(left) + 1 + len(right) <= width:
        return left + ' ' * (width - len(left) - len(right)) + right
    return trunc(left, width)


def fit_pair(name, count, width):
    count = str(count)
    if width <= 0:
        return ''
    if len(count) >= width:
        return trunc(count, width)
    room = width - len(count) - 1
    shown = trunc(name, room) if len(name) > room else name
    return shown + ' ' * (width - len(shown) - len(count)) + count


def norm(text):
    return text.casefold().replace('\u2019', "'").replace('\u2018', "'")


def filter_names(items, query):
    folded = norm(query)
    if not folded:
        return list(items)
    return [item for item in items if folded in norm(item)]


def suggest_titles(titles, query):
    folded_query = norm(query.strip())
    if not folded_query:
        return []
    starts = []
    contains = []
    for title in titles:
        folded = norm(title)
        if folded.startswith(folded_query):
            starts.append(title)
        elif folded_query in folded:
            contains.append(title)
    starts.sort(key=str.casefold)
    contains.sort(key=str.casefold)
    return starts + contains


def load_library(root):
    import filenamer
    grouped = {}
    for display, _path, tag in filenamer.crawl_files(os.fspath(root)):
        folders = grouped.setdefault(display, [])
        if tag not in folders:
            folders.append(tag)
    for folders in grouped.values():
        folders.sort(key=str.casefold)
    return grouped


def parse_row(line):
    if not line.startswith('|'):
        return None
    parts = line.split('|')
    if len(parts) != 4:
        return None
    book = parts[1].strip()
    tag = parts[2].strip()
    if not book or not tag or book == 'Book' or book.startswith('---'):
        return None
    return book, tag


def parse(data):
    newline = '\r\n' if b'\r\n' in data else '\n'
    lines = data.decode('utf-8').splitlines()
    header = []
    rows = []
    for line in lines:
        row = parse_row(line)
        if row is None:
            if rows:
                raise ValueError(f'unexpected line after the table: {line!r}')
            header.append(line)
            continue
        rows.append(row)
    if not header:
        raise ValueError('BOOKS.md has no table header')
    return header, rows, newline


def serialize(header, rows, newline):
    lines = list(header) + [f'| {book} | {tag} |' for book, tag in rows]
    return (newline.join(lines) + newline).encode('utf-8')


def add_row(rows, book, tag):
    book = book.strip()
    tag = tag.strip()
    if not book or not tag:
        return False, 'type a title'
    if '|' in book or '|' in tag:
        return False, 'a title cannot contain |'
    key = (book, tag)
    if key in rows:
        return False, f'already in {tag}'
    folded = norm(book)
    for existing, existing_tag in rows:
        if existing_tag == tag and existing != book and norm(existing) == folded:
            return False, f'already in {tag} as "{existing}"'
    last_less = None
    for index, row in enumerate(rows):
        if row < key:
            last_less = index
    rows.insert(0 if last_less is None else last_less + 1, key)
    return True, f'added "{book}"'


def remove_row(rows, book, tag):
    try:
        rows.remove((book, tag))
    except ValueError:
        return False
    return True


def enable_vt():
    if os.name != 'nt':
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.SetConsoleOutputCP(65001)
    kernel.SetConsoleCP(65001)
    handle = kernel.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel.SetConsoleMode(handle, mode.value | 0x0004)
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass


WIN_SPECIAL = {
    'H': 'up',
    'P': 'down',
    'K': 'left',
    'M': 'right',
    'G': 'home',
    'O': 'end',
    'I': 'pgup',
    'Q': 'pgdn',
    'S': 'delete',
}


def read_key():
    if os.name == 'nt':
        return read_key_win()
    return read_key_posix()


def read_key_win():
    import msvcrt
    ch = msvcrt.getwch()
    if ch in ('\x00', '\xe0'):
        return WIN_SPECIAL.get(msvcrt.getwch(), '')
    if ch in ('\r', '\n'):
        return 'enter'
    if ch == '\x1b':
        return 'esc'
    if ch in ('\x08', '\x7f'):
        return 'backspace'
    if ch == '\t':
        return 'tab'
    if ch == '\x03':
        return 'ctrl-c'
    return ch


def read_key_posix():
    import select
    ch = sys.stdin.read(1)
    if ch == '\x1b':
        seq = ''
        while select.select([sys.stdin], [], [], 0.02)[0]:
            seq += sys.stdin.read(1)
            if len(seq) >= 3:
                break
        return {
            '[A': 'up',
            '[B': 'down',
            '[C': 'right',
            '[D': 'left',
            '[H': 'home',
            '[F': 'end',
            '[5~': 'pgup',
            '[6~': 'pgdn',
            '[3~': 'delete',
        }.get(seq, 'esc')
    if ch in ('\r', '\n'):
        return 'enter'
    if ch in ('\x7f', '\x08'):
        return 'backspace'
    if ch == '\t':
        return 'tab'
    if ch == '\x03':
        return 'ctrl-c'
    return ch


class RawTerminal:
    def __enter__(self):
        self.old = None
        if os.name == 'nt':
            return self
        import termios
        import tty
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.old is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


def style_line(index, line, height):
    if index == 0:
        return f'\033[1m{line}\033[0m'
    if index == height - 1:
        return f'\033[2m{line}\033[0m'
    if line.startswith('>'):
        return f'\033[7m{line}\033[0m'
    if line and set(line) <= set('-'):
        return f'\033[2m{line}\033[0m'
    return line


def paint(lines):
    height = len(lines)
    out = ['\033[?25l']
    for index, line in enumerate(lines):
        out.append(f'\033[{index + 1};1H{style_line(index, line, height)}\033[0m\033[K')
    sys.stdout.write(''.join(out))
    sys.stdout.flush()


class App:
    def __init__(self, path, library_root=None):
        self.path = Path(path)
        data = self.path.read_bytes()
        self.header, self.rows, self.newline = parse(data)
        self.mode = 'tags'
        self.tag = None
        self.cursor = 0
        self.scroll = 0
        self.selected = 'reading_now' if any(tag == 'reading_now' for _, tag in self.rows) else None
        self.query = ''
        self.filtering = False
        self.status = ''
        self.pending = None
        self.memory = {}
        root = Path(library_root) if library_root else self.path.parent
        self.library = load_library(root)

    def tag_counts(self):
        counts = {}
        for _, tag in self.rows:
            counts[tag] = counts.get(tag, 0) + 1
        return counts

    def current_items(self):
        showing = 'books' if self.mode == 'confirm' else self.mode
        if showing == 'tags':
            names = sorted(self.tag_counts(), key=str.casefold)
            if self.filtering:
                return filter_names(names, self.query)
            return names
        if showing == 'books':
            books = sorted(
                (book for book, tag in self.rows if tag == self.tag),
                key=str.casefold,
            )
            if self.filtering:
                return filter_names(books, self.query)
            return books
        return self.add_suggestions()

    def add_suggestions(self):
        taken = {norm(book) for book, tag in self.rows if tag == self.tag}
        titles = [title for title in self.library if norm(title) not in taken]
        return suggest_titles(titles, self.query)

    def find_tag(self, name):
        folded = norm(name)
        for _book, tag in self.rows:
            if norm(tag) == folded:
                return tag
        return None

    def clamp(self):
        items = self.current_items()
        if not items:
            self.cursor = 0
            self.scroll = 0
            self.selected = None
            return items
        if self.selected in items:
            self.cursor = items.index(self.selected)
        else:
            self.cursor = min(self.cursor, len(items) - 1)
            self.selected = items[self.cursor]
        return items

    def on_query_changed(self):
        items = self.current_items()
        if self.selected in items:
            self.cursor = items.index(self.selected)
            return
        self.cursor = 0
        self.scroll = 0
        self.selected = items[0] if items else None

    def list_height(self, height):
        chrome = 5 if self.mode == 'add' else 4
        return max(1, height - chrome)

    def finish_new_tag(self):
        name = self.query.strip()
        if not name:
            self.status = 'type a category name'
            return
        if '|' in name:
            self.status = 'a category cannot contain |'
            return
        existing = self.find_tag(name)
        self.query = ''
        self.status = ''
        if existing:
            self.open_tag(existing)
            return
        self.open_tag(name)
        self.mode = 'add'
        self.query = ''
        self.cursor = 0
        self.scroll = 0
        self.selected = None
        self.status = 'add a book to keep this category'

    def move(self, key, height):
        items = self.clamp()
        if not items:
            return
        page = self.list_height(height)
        index = self.cursor
        if key == 'up':
            index -= 1
        elif key == 'down':
            index += 1
        elif key == 'pgup':
            index -= page
        elif key == 'pgdn':
            index += page
        elif key == 'home':
            index = 0
        elif key == 'end':
            index = len(items) - 1
        self.cursor = max(0, min(len(items) - 1, index))
        self.selected = items[self.cursor]

    def save(self):
        data = serialize(self.header, self.rows, self.newline)
        tmp = self.path.with_name(self.path.name + f'.{os.getpid()}.tmp')
        try:
            tmp.write_bytes(data)
            os.replace(tmp, self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def add_current(self, title):
        ok, message = add_row(self.rows, title, self.tag)
        self.status = message
        if not ok:
            return
        self.save()
        self.query = ''
        self.cursor = 0
        self.scroll = 0
        self.selected = None

    def remove_current(self, title):
        if not remove_row(self.rows, title, self.tag):
            self.status = 'not in this tag'
            return
        self.save()
        self.status = f'removed "{title}"'
        if self.memory.get(self.tag) == title:
            self.memory.pop(self.tag, None)

    def open_tag(self, tag):
        self.tag = tag
        self.mode = 'books'
        self.filtering = False
        self.query = ''
        self.scroll = 0
        self.status = ''
        books = self.current_items()
        remembered = self.memory.get(tag)
        if remembered in books:
            self.selected = remembered
            self.cursor = books.index(remembered)
        else:
            self.cursor = 0
            self.selected = books[0] if books else None

    def back_to_tags(self):
        if self.tag and self.selected:
            self.memory[self.tag] = self.selected
        self.mode = 'tags'
        self.filtering = False
        self.query = ''
        self.scroll = 0
        self.status = ''
        self.selected = self.tag

    def handle(self, key, height):
        if key == 'ctrl-c':
            return True
        if self.mode == 'confirm':
            if key in ('y', 'Y'):
                self.remove_current(self.pending)
            else:
                self.status = ''
            self.mode = 'books'
            self.pending = None
            return False
        if self.mode == 'newtag':
            return self.handle_newtag(key, height)
        if self.mode == 'add':
            return self.handle_add(key, height)
        if self.filtering:
            return self.handle_filter(key, height)
        return self.handle_list(key, height)

    def handle_add(self, key, height):
        if key == 'esc':
            self.query = ''
            self.scroll = 0
            kept = any(tag == self.tag for _book, tag in self.rows)
            if not kept:
                self.back_to_tags()
                return False
            self.mode = 'books'
            self.status = ''
            self.selected = self.memory.get(self.tag)
            return False
        if key == 'backspace':
            self.query = self.query[:-1]
            self.status = ''
            self.on_query_changed()
            return False
        if key == 'tab':
            self.add_current(self.query)
            return False
        if key == 'enter':
            items = self.current_items()
            if items:
                self.clamp()
                self.add_current(items[self.cursor])
            else:
                self.add_current(self.query)
            return False
        if key in ('up', 'down', 'pgup', 'pgdn', 'home', 'end'):
            self.move(key, height)
            self.status = ''
            return False
        if len(key) == 1 and key.isprintable():
            self.query += key
            self.status = ''
            self.on_query_changed()
        return False

    def handle_newtag(self, key, height):
        if key == 'esc':
            self.mode = 'tags'
            self.query = ''
            self.status = ''
            return False
        if key == 'backspace':
            self.query = self.query[:-1]
            self.status = ''
            return False
        if key == 'enter':
            self.finish_new_tag()
            return False
        if len(key) == 1 and key.isprintable():
            self.query += key
            self.status = ''
        return False

    def handle_filter(self, key, height):
        if key == 'esc':
            self.filtering = False
            self.query = ''
            return False
        if key == 'enter':
            self.filtering = False
            self.query = ''
            return False
        if key == 'backspace':
            self.query = self.query[:-1]
            if not self.query:
                self.filtering = False
            self.on_query_changed()
            return False
        if key in ('up', 'down', 'pgup', 'pgdn', 'home', 'end'):
            self.move(key, height)
            return False
        if len(key) == 1 and key.isprintable():
            self.query += key
            self.on_query_changed()
        return False

    def handle_list(self, key, height):
        if key == 'q':
            return True
        if key == '/':
            self.filtering = True
            self.query = ''
            self.status = ''
            return False
        if key in ('up', 'down', 'pgup', 'pgdn', 'home', 'end', 'j', 'k', 'g', 'G'):
            mapped = {'j': 'down', 'k': 'up', 'g': 'home', 'G': 'end'}.get(key, key)
            self.move(mapped, height)
            self.status = ''
            return False
        if self.mode == 'tags' and key in ('n', 'N'):
            self.mode = 'newtag'
            self.query = ''
            self.status = ''
            return False
        if self.mode == 'tags' and key in ('enter', 'right'):
            items = self.clamp()
            if items:
                self.open_tag(items[self.cursor])
            return False
        if self.mode == 'books' and key in ('b', 'left', 'esc', 'backspace'):
            self.back_to_tags()
            return False
        if self.mode == 'books' and key == 'a':
            self.memory[self.tag] = self.selected
            self.mode = 'add'
            self.query = ''
            self.cursor = 0
            self.scroll = 0
            self.selected = None
            self.status = ''
            return False
        if self.mode == 'books' and key in ('d', 'delete'):
            items = self.clamp()
            if not items:
                self.status = 'nothing to remove'
                return False
            self.pending = items[self.cursor]
            self.mode = 'confirm'
            self.status = f'remove "{self.pending}" from {self.tag}? y/n'
        return False

    def build(self, width, height):
        width = max(10, width)
        height = max(6, height)
        if self.mode == 'add':
            return self.build_add(width, height)
        if self.mode == 'newtag':
            return self.build_newtag(width, height)
        return self.build_list(width, height)

    def window(self, items, width, list_height, placeholder='(empty)'):
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + list_height:
            self.scroll = self.cursor - list_height + 1
        self.scroll = max(0, self.scroll)
        rows = []
        if not items:
            rows.append(trunc('  ' + placeholder, width))
        else:
            for offset, item in enumerate(items[self.scroll:self.scroll + list_height]):
                absolute = self.scroll + offset
                prefix = '> ' if absolute == self.cursor else '  '
                rows.append(trunc(prefix + item, width))
        while len(rows) < list_height:
            rows.append('')
        return rows[:list_height]

    def build_list(self, width, height):
        items = self.clamp()
        showing = 'books' if self.mode == 'confirm' else self.mode
        if showing == 'tags':
            counts = self.tag_counts()
            labels = [fit_pair(tag, counts[tag], width - 2) for tag in items]
            left = self.path.name
        else:
            labels = items
            left = self.tag or ''
        if self.filtering:
            left = f'{left}  /{self.query}'
        right = f'{self.cursor + 1}/{len(items)}' if items else '0'
        lines = [header_line(left, right, width), '-' * width]
        lines.extend(self.window(labels, width, self.list_height(height)))
        if self.mode == 'confirm':
            help_text = 'y remove    any other key cancels'
        elif self.filtering:
            help_text = 'type to filter    esc clear    arrows move'
        elif showing == 'tags':
            help_text = 'arrows move    n new    enter open    / filter    q quit'
        else:
            help_text = 'arrows move    a add    d remove    b back    / filter    q quit'
        lines.append(trunc(self.status, width))
        lines.append(trunc(help_text, width))
        return lines

    def build_add(self, width, height):
        items = self.clamp()
        right = f'{self.cursor + 1}/{len(items)}' if items else 'new'
        lines = [
            header_line(f'add to {self.tag}', right, width),
            '-' * width,
            trunc('title: ' + self.query + '_', width),
        ]
        labels = []
        for title in items:
            folders = ', '.join(self.library.get(title, []))
            labels.append(fit_pair(title, folders, width - 2) if folders else title)
        if self.query.strip():
            placeholder = 'no matches in the folders'
        else:
            placeholder = 'type to search books in the folders'
        lines.extend(self.window(labels, width, self.list_height(height), placeholder))
        hint = self.status
        if not hint and items and self.selected:
            folders = self.library.get(self.selected, [])
            if folders:
                hint = 'in ' + ', '.join(folders)
        elif not hint and self.query.strip() and not items:
            hint = 'no folder match — enter adds this title anyway'
        lines.append(trunc(hint, width))
        lines.append(trunc('enter add selected    tab add typed text    esc back', width))
        return lines

    def build_newtag(self, width, height):
        lines = [
            header_line('new category', '', width),
            '-' * width,
            trunc('name: ' + self.query + '_', width),
        ]
        while len(lines) < height - 2:
            lines.append('')
        note = self.status
        if not note and self.query.strip():
            existing = self.find_tag(self.query.strip())
            if existing:
                note = f'opens {existing}'
        lines.append(trunc(note, width))
        lines.append(trunc('enter create    esc back', width))
        return lines

    def run(self):
        sys.stdout.write('\033[?1049h\033[H\033[?25l')
        sys.stdout.flush()
        try:
            with RawTerminal():
                while True:
                    size = shutil.get_terminal_size(fallback=(80, 24))
                    width = max(20, size.columns - 1)
                    height = max(6, size.lines)
                    paint(self.build(width, height))
                    if self.handle(read_key(), height):
                        return
        finally:
            sys.stdout.write('\033[?25h\033[0m\033[?1049l')
            sys.stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ('-h', '--help'):
        print('usage: python books_tui.py [BOOKS.md]')
        print('Group the Book/Tag table by tag, then insert or delete rows.')
        return 0
    path = Path(argv[0]) if argv else Path(__file__).with_name('BOOKS.md')
    if not path.is_file():
        print(f'no such file: {path}', file=sys.stderr)
        return 1
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('run this in a terminal: python books_tui.py', file=sys.stderr)
        return 1
    try:
        app = App(path)
    except (OSError, UnicodeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    enable_vt()
    try:
        app.run()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
